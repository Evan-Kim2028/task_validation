"""Generator gate: SRS sample plus oracle/nop execution gate for a generated lot.

Implements doc 50 gate A on one generator's output: freeze a simple random
sample manifest, run the official verifier in fresh containers (oracle k=2,
nop k=2 by default), and emit a doc-32 certificate at the generator's full
population N. No LLM anywhere in the bound (doc 43). Every verdict carries
protocol verifier_invalid.fresh_environment.execution, grade A, adjudicator
machine, verifier_kind execution. Judge-configured and no-reference tasks are
detected, recorded as their own strata, and left unadjudicated in the
execution certificate (doc 44). Never fabricates a reward.

Scheduling: by default all of a task's trials dispatch at once at
--concurrency and each builds its own environment image, so two trials of
one task can run against different builds. --warmup instead runs the
first pending trial (the first oracle rep on a fresh task, or the first
nop rep when oracle trials do not run) alone to completion, so its
environment image build populates the docker layer cache before the
remaining trials fan out against the same image. All-at-once dispatch
means the trials of one task all build the same image concurrently, the
cache serves none of them, and they contend for disk:
in the SETA gate run (concurrency 3) the quickest executed trial per task
medians 51 s (n=164) while the other three median 107 s (n=492). Under
--warmup a warmup trial that comes back infra is recorded and the rest of
the task's trials are skipped for the pass as not_run rows; they are not
retried inside the runner. The two schedulings measure different
constructs -- concurrent conflates verifier and build nondeterminism,
warmup isolates the verifier -- so the choice is recorded on the
certificate as "scheduling" and is not interchangeable across runs
(doc 53). Probes, statuses, resume keys, row schema, prune cadence and
the certificate path are unchanged either way, and no verdict rule is
affected.

Probe selection: --probes takes a comma-separated subset of oracle,nop and
defaults to both, which is the two-sided gate. With oracle absent the run
is one-sided (doc 44): every task is recorded in the none stratum with
one_sided true, a nop acceptance is the only invalid finding, and a nop
rejection leaves the task unadjudicated rather than clean. The run's
certificate is a one-sided bound over the accepts-an-empty-solution defect
class only.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import subprocess
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from task_validation.evidence.judge_verifier import detect_judge
from task_validation.evidence.tb21_pairs import (
    STDERR_TAIL_CHARS,
    STDOUT_TAIL_LINES,
    _job_log_text,
    _kill_pg,
    _latest_path,
    _looks_infra,
    _still_building,
    append_jsonl,
    load_existing_rows,
    read_test_stdout,
    tail_lines,
    write_json,
)
from task_validation.sampling.certificate import build_certificate
from task_validation.sampling.designs import _rng

PROTOCOL = "verifier_invalid.fresh_environment.execution"
GRADE = "A"
ADJUDICATOR = "machine"
VERIFIER_KIND = "execution"
DESIGN = "SRS without replacement"

K_DEFAULT = 2
CONCURRENCY_DEFAULT = 4
TRIAL_CAP_SEC = 60 * 60
BUDGET_SEC = 24 * 60 * 60
PRUNE_EVERY = 20
TIMEOUT_MULT = 1.0
VERIFIER_TIMEOUT_MULT = 2.0
BUILD_TIMEOUT_MULT = 2.0

TERMINAL_STATUSES = frozenset(
    {"executed", "infra", "timeout", "no_reference", "judge_stratum"}
)
REDO_STATUSES = frozenset({"infra", "timeout"})
PROBE_NAMES = ("oracle", "nop")

_DEFAULT_OUT = Path("data/gold")


def default_manifest_path(name: str) -> Path:
    return _DEFAULT_OUT / f"gen_gate_{name}_manifest.json"


def default_out_path(name: str) -> Path:
    return _DEFAULT_OUT / f"gen_gate_{name}.jsonl"


def default_extract_dir(root: Path, name: str) -> Path:
    return Path(root).resolve().parent / f"{Path(root).name}-gate-extract" / name


def default_jobs_dir(name: str) -> Path:
    return Path(f"/tmp/tv-gen-gate-{name}/jobs")


def default_seed(name: str) -> str:
    return f"gen-gate-{name}-v0"


def _progress(msg: str) -> None:
    print(f"[generator_gate] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Sampling: enumerate Harbor task dirs on disk and inside tars.
# ---------------------------------------------------------------------------


def _norm_member(name: str) -> str:
    return posixpath.normpath(name).lstrip("./")


def _tar_task_prefixes(tar_path: Path) -> list[str]:
    """Task-dir prefixes inside one tar: members that hold task.toml.

    Reads member names only; nothing is extracted.
    """
    prefixes: set[str] = set()
    with tarfile.open(tar_path, "r:*") as tf:
        for member in tf:
            name = _norm_member(member.name)
            if not member.isfile():
                continue
            if name == "task.toml" or not name.endswith("/task.toml"):
                continue
            prefixes.add(name[: -len("/task.toml")])
    return sorted(prefixes)


def enumerate_tasks(root: Path, *, exclude: Path | None = None) -> list[dict]:
    """All Harbor task dirs under root, on disk or inside *.tar files.

    Returns sorted entries: {task_id, kind: dir|tar, ...}. task_id is the
    task dir's path relative to root (dirs) or the member dir inside the tar
    (tars), posix-normalized. Duplicate ids across sources raise: an id must
    name exactly one task.
    """
    root = Path(root).resolve()
    excluded = Path(exclude).resolve() if exclude else None
    entries: list[dict] = []

    for toml in sorted(root.rglob("task.toml")):
        task_dir = toml.parent
        if excluded and (task_dir == excluded or excluded in task_dir.parents):
            continue
        if any(p in {".git", "jobs", "vendor", "__pycache__"} for p in task_dir.parts):
            continue
        rel = task_dir.relative_to(root).as_posix()
        entries.append({"task_id": rel, "kind": "dir", "path": str(task_dir)})

    for tar_path in sorted(root.rglob("*.tar")):
        if excluded and (tar_path == excluded or excluded in tar_path.parents):
            continue
        for prefix in _tar_task_prefixes(tar_path):
            entries.append(
                {
                    "task_id": prefix,
                    "kind": "tar",
                    "tar": str(tar_path),
                    "member": prefix,
                }
            )

    seen: dict[str, dict] = {}
    for e in entries:
        prev = seen.get(e["task_id"])
        if prev is not None:
            raise ValueError(
                f"task_id {e['task_id']!r} is ambiguous: "
                f"{prev.get('path') or prev.get('tar')} and "
                f"{e.get('path') or e.get('tar')}"
            )
        seen[e["task_id"]] = e
    return sorted(entries, key=lambda e: e["task_id"])


def draw_sample_ids(ids: list[str], n: int, seed: str) -> list[str]:
    """SRS without replacement, ids returned in draw order.

    random.Random.sample makes the n-draw a prefix of any larger draw on the
    same seed and population, so a manifest can grow n -> n' with the same
    seed and keep the first n tasks.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if n > len(ids):
        raise ValueError(f"n={n} exceeds enumerated population {len(ids)}")
    return _rng(seed).sample(sorted(ids), n)


def _iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        if any(part in {".git", "__pycache__", ".pytest_cache"} for part in p.parts):
            continue
        yield p


def dir_sha256(root: Path) -> str:
    """Deterministic digest over relative paths and file bytes."""
    h = hashlib.sha256()
    root = Path(root)
    for p in _iter_files(root):
        rel = p.relative_to(root).as_posix()
        if p.is_dir():
            h.update(b"D\0" + rel.encode() + b"\n")
            continue
        try:
            data = p.read_bytes()
        except OSError:
            data = b""
        h.update(b"F\0" + rel.encode() + b"\0")
        h.update(hashlib.sha256(data).hexdigest().encode() + b"\n")
    return h.hexdigest()


def materialize_task(entry: dict, extract_dir: Path) -> Path:
    """Local path to the task dir; extracts tar members on demand."""
    if entry["kind"] == "dir":
        return Path(entry["path"])
    member = entry["member"]
    dest = Path(extract_dir) / Path(entry["tar"]).stem / member
    if (dest / "task.toml").is_file():
        return dest
    # Extract under P so that P/member == dest even for nested members.
    depth = len(posixpath.normpath(member).split("/"))
    base = dest.parents[depth - 1]
    base.mkdir(parents=True, exist_ok=True)
    prefix = member + "/"
    with tarfile.open(entry["tar"], "r:*") as tf:
        for m in tf:
            name = _norm_member(m.name)
            if name != member and not name.startswith(prefix):
                continue
            tf.extract(m, path=base, filter="data")
    return dest


def task_entry_meta(entry: dict, task_dir: Path) -> dict:
    meta = {
        "path": str(task_dir.resolve()),
        "sha256": dir_sha256(task_dir),
        "source": entry["kind"],
        "has_reference": (task_dir / "solution").is_dir(),
    }
    if entry["kind"] == "tar":
        meta["tar"] = str(entry["tar"])
        meta["member"] = entry["member"]
    return meta


def sample_generator(
    *,
    name: str,
    root: Path,
    n: int,
    seed: str,
    out_path: Path,
    extract_dir: Path,
) -> dict:
    """Freeze the manifest. Re-running with the same seed and a larger n
    grows the sample: the frozen ids must be a prefix of the new draw."""
    root = Path(root).resolve()
    out_path = Path(out_path)
    extract_dir = Path(extract_dir)
    entries = enumerate_tasks(root, exclude=extract_dir)
    all_ids = [e["task_id"] for e in entries]
    if n > len(all_ids):
        raise ValueError(f"n={n} exceeds enumerated population {len(all_ids)}")
    by_id = {e["task_id"]: e for e in entries}
    draw = draw_sample_ids(all_ids, n, seed)

    existing: dict | None = None
    if out_path.is_file():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        if str(existing.get("seed")) != str(seed):
            raise ValueError(
                f"manifest {out_path} is frozen under seed {existing.get('seed')!r}; "
                f"refusing to re-sample under {seed!r}"
            )
        old_ids = [str(x) for x in existing.get("ids") or []]
        if len(old_ids) > n:
            raise ValueError(
                f"manifest already frozen at n={len(old_ids)} > {n}; refusing to shrink"
            )
        if draw[: len(old_ids)] != old_ids:
            raise ValueError(
                "new draw does not extend the frozen sample as a prefix; "
                "the population changed or the seed is wrong"
            )
        if len(old_ids) == n:
            return existing

    tasks: dict[str, dict] = dict((existing or {}).get("tasks") or {})
    for tid in draw:
        if tid in tasks:
            continue
        task_dir = materialize_task(by_id[tid], extract_dir)
        tasks[tid] = task_entry_meta(by_id[tid], task_dir)
        _progress(f"materialized {tid} -> {tasks[tid]['path']}")

    manifest = {
        "design": DESIGN,
        "generator": name,
        "root": str(root),
        "extract_dir": str(extract_dir),
        "N": len(entries),
        "n": n,
        "seed": seed,
        "frozen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ids": draw,
        "tasks": tasks,
    }
    write_json(out_path, manifest)
    _progress(
        f"manifest {out_path}: N={len(entries)} n={n} seed={seed!r} "
        f"tasks_on_disk={len(tasks)}"
    )
    return manifest


# ---------------------------------------------------------------------------
# Trial execution: one `harbor run` per (task, probe, rep).
# ---------------------------------------------------------------------------


def slug_for(task_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", task_id).strip("-.") or "task"


def read_gate_reward(jobs_out: Path, job_name: str) -> float | None:
    """reward.txt first, then verifier/reward.json (doc 28 bix gap)."""
    path = _latest_path(jobs_out, job_name, "verifier/reward.txt")
    if path is not None:
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return float(text.split()[0])
        except (OSError, ValueError):
            pass
    path = _latest_path(jobs_out, job_name, "verifier/reward.json")
    if path is None:
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(obj, dict):
        obj = obj.get("reward")
    try:
        return float(obj)
    except (TypeError, ValueError):
        return None


def run_gate_trial(
    task_dir: Path,
    agent: str,
    jobs_out: Path,
    name: str,
    *,
    concurrency: int = CONCURRENCY_DEFAULT,
    timeout_mult: float = TIMEOUT_MULT,
    verifier_mult: float = VERIFIER_TIMEOUT_MULT,
    build_mult: float = BUILD_TIMEOUT_MULT,
    cap_sec: int = TRIAL_CAP_SEC,
    build_heavy_sec: int | None = None,
) -> dict:
    """harbor run -p <task> --agent <agent> -k 1 with timeout multipliers.

    The outer cap_sec kills the process group; the multipliers cap the
    verifier and the environment build inside harbor itself. A trial still
    building with no reward past build_heavy_sec is killed as infra; the
    default is cap_sec, i.e. builds may use the whole cap.
    """
    jobs_out = Path(jobs_out)
    jobs_out.mkdir(parents=True, exist_ok=True)
    cmd = [
        "harbor",
        "run",
        "-p",
        str(task_dir),
        "--agent",
        agent,
        "--env",
        "docker",
        "--yes",
        "-n",
        str(int(concurrency)),
        "-k",
        "1",
        "--job-name",
        name,
        "-o",
        str(jobs_out),
        "--timeout-multiplier",
        str(timeout_mult),
        "--verifier-timeout-multiplier",
        str(verifier_mult),
        "--environment-build-timeout-multiplier",
        str(build_mult),
    ]
    t0 = time.monotonic()
    timed_out = False
    build_heavy = False
    rc: int | None = None
    stdout_path = jobs_out / f"{name}.stdout.log"
    stderr_path = jobs_out / f"{name}.stderr.log"
    stderr = ""
    with stdout_path.open("w", encoding="utf-8") as so, stderr_path.open(
        "w", encoding="utf-8"
    ) as se:
        try:
            proc = subprocess.Popen(
                cmd, stdout=so, stderr=se, text=True, start_new_session=True
            )
        except Exception as exc:
            proc = None
            stderr = f"{type(exc).__name__}: {exc}"
        while proc is not None:
            elapsed = time.monotonic() - t0
            if elapsed >= cap_sec:
                timed_out = True
                _kill_pg(proc)
                break
            if (
                elapsed >= (build_heavy_sec if build_heavy_sec else cap_sec)
                and read_gate_reward(jobs_out, name) is None
                and _still_building(jobs_out, name)
            ):
                build_heavy = True
                _kill_pg(proc)
                break
            rc = proc.poll()
            if rc is not None:
                break
            time.sleep(min(5.0, max(0.5, cap_sec - elapsed)))
        elapsed = time.monotonic() - t0
        if proc is not None:
            if proc.poll() is None:
                _kill_pg(proc)
            rc = proc.poll()
    try:
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = (
            stderr + "\n" + stderr_path.read_text(encoding="utf-8", errors="replace")
        ).strip()
    except OSError:
        stdout = ""
    reward = read_gate_reward(jobs_out, name)
    test_stdout_tail = read_test_stdout(jobs_out, name)
    err_tail = (stderr or "")[-STDERR_TAIL_CHARS:]
    if not err_tail:
        err_tail = _job_log_text(jobs_out, name)[-STDERR_TAIL_CHARS:]
    if reward is not None:
        status = "executed"
    elif timed_out:
        status = "timeout"
    else:
        status = "infra"
    return {
        "cmd": cmd,
        "returncode": rc,
        "elapsed_sec": elapsed,
        "reward": reward,
        "status": status,
        "stderr_tail": err_tail,
        "test_stdout_tail": test_stdout_tail,
        "skip_reason": "environment_build_exceeded_cap" if build_heavy else None,
    }


# ---------------------------------------------------------------------------
# Docker hygiene.
# ---------------------------------------------------------------------------

_SIZE_UNITS = {
    "b": 1,
    "kb": 1e3,
    "mb": 1e6,
    "gb": 1e9,
    "tb": 1e12,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}


def parse_reclaimed_bytes(text: str) -> int:
    """Bytes from docker prune output ('Total reclaimed space: 1.5GB')."""
    total = 0.0
    found = False
    for m in re.finditer(
        r"Total(?:\s+reclaimed\s+space)?:\s*([0-9.]+)\s*([A-Za-z]+)", text or ""
    ):
        unit = m.group(2).lower()
        if unit not in _SIZE_UNITS:
            continue
        total += float(m.group(1)) * _SIZE_UNITS[unit]
        found = True
    return int(total) if found else 0


class DockerMaintenance:
    """Keeps the image store small during a gate run. Shells out to docker."""

    def rm_task_containers(self, task_dir: Path) -> list[str]:
        """docker rm -f any leftover containers for this task's trials."""
        slug = slug_for(Path(task_dir).name)
        try:
            out = subprocess.check_output(
                ["docker", "ps", "-a", "--format", "{{.Names}}"],
                text=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            return []
        victims = [
            name.strip()
            for name in out.splitlines()
            if name.strip().startswith(slug + "__")
        ]
        removed: list[str] = []
        for name in victims:
            try:
                subprocess.run(
                    ["docker", "rm", "-f", name],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                removed.append(name)
            except (subprocess.SubprocessError, OSError):
                continue
        return removed

    def prune(self) -> dict:
        """docker image, builder and network prune; bytes reclaimed and networks removed."""
        reclaimed = {"image_bytes": 0, "builder_bytes": 0}
        try:
            out = subprocess.run(
                ["docker", "image", "prune", "-af"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            reclaimed["image_bytes"] = parse_reclaimed_bytes(
                (out.stdout or "") + "\n" + (out.stderr or "")
            )
        except (subprocess.SubprocessError, OSError) as exc:
            reclaimed["image_error"] = f"{type(exc).__name__}: {exc}"
        try:
            out = subprocess.run(
                ["docker", "builder", "prune", "-af"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            reclaimed["builder_bytes"] = parse_reclaimed_bytes(
                (out.stdout or "") + "\n" + (out.stderr or "")
            )
        except (subprocess.SubprocessError, OSError) as exc:
            reclaimed["builder_error"] = f"{type(exc).__name__}: {exc}"
        # Stale per-trial compose networks exhaust the daemon address pool
        # ("all predefined address pools have been fully subnetted"), seen on
        # 2026-09-13 in both the judge-swap and lot-001 gate C runs.
        try:
            out = subprocess.run(
                ["docker", "network", "prune", "-f"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            reclaimed["networks_pruned"] = len(
                [l for l in (out.stdout or "").splitlines() if l.strip() and "Deleted" not in l]
            )
        except (subprocess.SubprocessError, OSError) as exc:
            reclaimed["network_error"] = f"{type(exc).__name__}: {exc}"
        return reclaimed


# ---------------------------------------------------------------------------
# Verdicts and the run loop.
# ---------------------------------------------------------------------------


def trial_key(row: dict) -> tuple[str, str, int]:
    return (str(row["task_id"]), str(row["probe"]), int(row.get("rep") or 0))


def build_trial_row(
    *,
    task_id: str,
    probe: str,
    rep: int,
    reward: float | None,
    status: str,
    elapsed_sec: float,
    test_stdout_tail: str = "",
    stderr_tail: str = "",
    skip_reason: str | None = None,
    job_name: str | None = None,
    path: str | None = None,
    sha256: str | None = None,
) -> dict:
    if status != "executed":
        reward = None
    accepted = (reward == 1.0) if reward is not None else None
    return {
        "task_id": task_id,
        "probe": probe,
        "rep": int(rep),
        "intended": "reject" if probe == "nop" else "accept",
        "reward": reward,
        "accepted": accepted,
        "status": status,
        "elapsed_sec": float(elapsed_sec),
        "label_protocol": PROTOCOL,
        "grade": GRADE,
        "verifier_kind": VERIFIER_KIND,
        "adjudicator": ADJUDICATOR,
        "test_stdout_tail": test_stdout_tail,
        "stderr_tail": stderr_tail,
        "skip_reason": skip_reason,
        "job_name": job_name,
        "path": path,
        "sha256": sha256,
    }


def latest_rows(rows: list[dict]) -> dict[tuple[str, str, int], dict]:
    """Last row per (task, probe, rep); earlier superseded rows are history."""
    out: dict[tuple[str, str, int], dict] = {}
    for row in rows:
        out[trial_key(row)] = row
    return out


def detect_verifier_kind(task_dir: Path, trials: list[dict]) -> str:
    statuses = {str(t.get("status") or "") for t in trials}
    if "judge_stratum" in statuses:
        return "judge"
    if "no_reference" in statuses:
        return "none"
    if task_dir.is_dir():
        if detect_judge(task_dir)["is_judge"]:
            return "judge"
        if not (task_dir / "solution").is_dir():
            return "none"
    return "execution"


def task_verdict(
    task_id: str,
    trials: list[dict],
    task_dir: Path,
    k: int,
    *,
    one_sided: bool = False,
) -> dict:
    """One doc-32 verdict row per manifest task.

    invalid = True when an executed oracle rep accepted False or an executed
    nop rep accepted True. invalid = False only when all 2k trials executed
    clean. Anything else (infra, timeout, not_run, missing) is None and the
    task stays unadjudicated: infra is excluded from the bound and counted.

    Under one_sided (oracle probe not scheduled) every non-judge task sits
    in the none stratum: invalid = True when an executed nop rep accepted
    True, else invalid stays None. A nop rejection is not evidence of
    validity, so one-sided verdicts never read clean (doc 44).
    """
    oracle = [t for t in trials if t.get("probe") == "oracle"]
    nop = [t for t in trials if t.get("probe") == "nop"]
    kind = detect_verifier_kind(task_dir, trials)
    if one_sided and kind != "judge":
        kind = "none"
    oracle_rewards = [t.get("reward") for t in oracle if t.get("status") == "executed"]
    nop_rewards = [t.get("reward") for t in nop if t.get("status") == "executed"]
    statuses = sorted({str(t.get("status") or "") for t in trials})

    oracle_failed = any(t.get("accepted") is False for t in oracle if t.get("status") == "executed")
    nop_passed = any(t.get("accepted") is True for t in nop if t.get("status") == "executed")
    all_executed = len(trials) == 2 * k and all(
        t.get("status") == "executed" for t in trials
    )
    deterministic = (
        len(set(oracle_rewards)) <= 1 and len(set(nop_rewards)) <= 1
        if oracle_rewards or nop_rewards
        else None
    )

    if kind != "execution" and not (one_sided and kind == "none"):
        invalid = None
        reason = f"verifier_kind {kind} is not execution"
    elif one_sided:
        if nop_passed:
            invalid = True
            reason = "nop accepted an empty solution at least once"
        elif nop_rewards:
            invalid = None
            reason = "one-sided: nop rejected; a reject is not evidence of validity (doc 44)"
        else:
            invalid = None
            reason = "one-sided: no executed nop trial: " + ",".join(statuses or ["none"])
    elif oracle_failed or nop_passed:
        invalid = True
        reason = "clean" if all_executed else "defect seen; some trials not executed"
    elif all_executed:
        invalid = False
        reason = "clean"
    else:
        invalid = None
        reason = "trials incomplete or infra: " + ",".join(statuses or ["none"])

    evidence = (
        f"oracle_rewards={oracle_rewards} nop_rewards={nop_rewards} "
        f"statuses={statuses} deterministic={deterministic}"
    )
    if oracle_failed:
        evidence += "; oracle failed own verifier at least once"
    if nop_passed:
        evidence += "; nop passed at least once"
    if one_sided:
        evidence += "; one-sided nop-only probe set"
    return {
        "unit_id": task_id,
        "invalid": invalid,
        "one_sided": bool(one_sided),
        "label_protocol": PROTOCOL,
        "grade": GRADE,
        "adjudicator": ADJUDICATOR,
        "verifier_kind": kind,
        "evidence": evidence,
        "verdict_reason": reason,
        "oracle_rewards": oracle_rewards,
        "nop_rewards": nop_rewards,
        "statuses": statuses,
        "deterministic": deterministic,
        "n_trials": len(trials),
    }


def verdicts_from_rows(manifest: dict, rows: list[dict]) -> list[dict]:
    planned = manifest.get("probes")
    if planned is None:
        # The frozen manifest does not record the probe set. Under the
        # two-sided gate every touched task writes at least one oracle row,
        # so a rows file with only nop rows can only come from --probes nop.
        probes_seen = {str(r.get("probe")) for r in rows if r.get("probe")}
        planned = ["nop"] if probes_seen == {"nop"} else list(PROBE_NAMES)
    one_sided = "oracle" not in planned
    by_task: dict[str, list[dict]] = {}
    for row in latest_rows(rows).values():
        by_task.setdefault(str(row["task_id"]), []).append(row)
    verdicts: list[dict] = []
    tasks_meta = manifest.get("tasks") or {}
    for tid in manifest["ids"]:
        tid = str(tid)
        meta = tasks_meta.get(tid) or {}
        task_dir = Path(meta.get("path") or "")
        verdicts.append(
            task_verdict(
                tid,
                by_task.get(tid, []),
                task_dir,
                int(manifest.get("k") or K_DEFAULT),
                one_sided=one_sided,
            )
        )
    return verdicts


def summary_path_for(out_path: Path) -> Path:
    name = out_path.name
    if name.endswith(".jsonl"):
        return out_path.with_name(name[: -len(".jsonl")] + ".summary.json")
    return out_path.with_suffix(out_path.suffix + ".summary.json")


def certificate_path_for(out_path: Path) -> Path:
    name = out_path.name
    if name.endswith(".jsonl"):
        return out_path.with_name(name[: -len(".jsonl")] + ".certificate.json")
    return out_path.with_suffix(out_path.suffix + ".certificate.json")


def verdicts_path_for(out_path: Path) -> Path:
    name = out_path.name
    if name.endswith(".jsonl"):
        return out_path.with_name(name[: -len(".jsonl")] + "_verdicts.jsonl")
    return out_path.with_suffix(out_path.suffix + ".verdicts.jsonl")


def summarize(manifest: dict, rows: list[dict], *, wall_clock_total: float, maintenance: list[dict]) -> dict:
    latest = latest_rows(rows)
    by_task: dict[str, list[dict]] = {}
    for row in latest.values():
        by_task.setdefault(str(row["task_id"]), []).append(row)
    verdicts = verdicts_from_rows(manifest, rows)
    tasks = {v["unit_id"]: v for v in verdicts}
    one_sided = "oracle" not in (manifest.get("probes") or PROBE_NAMES)
    counted_kinds = ("execution", "none") if one_sided else ("execution",)
    n_infra_tasks = sum(
        1
        for v in verdicts
        if v["invalid"] is None
        and v["verifier_kind"] in counted_kinds
        and any(s in {"infra", "timeout"} for s in v["statuses"])
    )
    return {
        "generator": manifest.get("generator"),
        "protocol": PROTOCOL,
        "grade": GRADE,
        "verifier_kind": VERIFIER_KIND,
        "adjudicator": ADJUDICATOR,
        "probes": manifest.get("probes") or list(PROBE_NAMES),
        "one_sided": "oracle" not in (manifest.get("probes") or PROBE_NAMES),
        "n": manifest.get("n"),
        "N": manifest.get("N"),
        "seed": manifest.get("seed"),
        "n_tasks": len(manifest.get("ids") or []),
        "n_rows": len(rows),
        "n_trials": len(latest),
        "n_executed": sum(1 for r in latest.values() if r.get("status") == "executed"),
        "n_infra_trials": sum(1 for r in latest.values() if r.get("status") == "infra"),
        "n_timeout_trials": sum(1 for r in latest.values() if r.get("status") == "timeout"),
        "n_no_reference": sum(
            1 for v in verdicts if v["verifier_kind"] == "none"
        ),
        "n_judge_stratum": sum(
            1 for v in verdicts if v["verifier_kind"] == "judge"
        ),
        "n_invalid": sum(1 for v in verdicts if v["invalid"] is True),
        "n_valid": sum(1 for v in verdicts if v["invalid"] is False),
        "n_unadjudicated_tasks": sum(1 for v in verdicts if v["invalid"] is None),
        "n_infra_tasks": n_infra_tasks,
        "wall_clock_total": float(wall_clock_total),
        "maintenance": maintenance,
        "tasks": tasks,
    }


def _parse_probes(probes) -> list[str]:
    """Comma string or iterable -> validated ordered subset of PROBE_NAMES."""
    if isinstance(probes, str):
        probes = probes.split(",")
    out = [str(p).strip() for p in probes if str(p).strip()]
    out = list(dict.fromkeys(out))
    bad = [p for p in out if p not in PROBE_NAMES]
    if not out or bad:
        raise ValueError(
            f"probes must be a non-empty subset of {PROBE_NAMES}; got {out or probes!r}"
        )
    return out


def run_gate(
    *,
    manifest_path: Path,
    out_path: Path,
    jobs_dir: Path,
    extract_dir: Path | None = None,
    concurrency: int = CONCURRENCY_DEFAULT,
    k: int = K_DEFAULT,
    probes=("oracle", "nop"),
    budget_sec: float = BUDGET_SEC,
    trial_cap_sec: int = TRIAL_CAP_SEC,
    timeout_mult: float = TIMEOUT_MULT,
    verifier_mult: float = VERIFIER_TIMEOUT_MULT,
    build_mult: float = BUILD_TIMEOUT_MULT,
    prune_every: int = PRUNE_EVERY,
    epsilon: float = 0.05,
    summary_path: Path | None = None,
    certificate_path: Path | None = None,
    verdicts_path: Path | None = None,
    resume: bool = True,
    redo_infra: bool = False,
    warmup: bool = False,
    trial_runner=None,
    maintenance: DockerMaintenance | None = None,
) -> dict:
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["k"] = k
    probe_list = _parse_probes(probes)
    one_sided = "oracle" not in probe_list
    manifest["probes"] = probe_list
    out_path = Path(out_path)
    jobs_dir = Path(jobs_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    if summary_path is None:
        summary_path = summary_path_for(out_path)
    if certificate_path is None:
        certificate_path = certificate_path_for(out_path)
    if verdicts_path is None:
        verdicts_path = verdicts_path_for(out_path)
    if extract_dir is None:
        extract_dir = Path(manifest.get("extract_dir") or default_extract_dir(manifest.get("root") or ".", manifest.get("generator") or "gen"))
    if maintenance is None:
        maintenance = DockerMaintenance()
    if trial_runner is None:

        def trial_runner(task_dir, agent, jobs_out, name):
            return run_gate_trial(
                task_dir,
                agent,
                jobs_out,
                name,
                concurrency=concurrency,
                timeout_mult=timeout_mult,
                verifier_mult=verifier_mult,
                build_mult=build_mult,
                cap_sec=trial_cap_sec,
            )

    t_start = time.monotonic()
    existing = load_existing_rows(out_path) if resume else []
    rows = list(existing)
    terminal = TERMINAL_STATUSES - REDO_STATUSES if redo_infra else TERMINAL_STATUSES
    done = {
        key
        for key, row in latest_rows(existing).items()
        if row.get("status") in terminal
    }
    maintenance_log: list[dict] = []
    tasks_meta = manifest.get("tasks") or {}

    def persist(row: dict) -> None:
        rows.append(row)
        done.add(trial_key(row))
        append_jsonl(out_path, row)

    def remaining() -> float:
        return budget_sec - (time.monotonic() - t_start)

    def dump_outputs() -> dict:
        summary = summarize(
            manifest,
            rows,
            wall_clock_total=time.monotonic() - t_start,
            maintenance=maintenance_log,
        )
        verdicts = verdicts_from_rows(manifest, rows)
        cert = build_certificate(
            manifest,
            verdicts,
            epsilon,
            PROTOCOL,
            ADJUDICATOR,
            verifier_kind="none" if one_sided else VERIFIER_KIND,
            one_sided=one_sided,
            scheduling="warmup" if warmup else "concurrent",
        )
        summary["certificate"] = {
            "path": str(certificate_path),
            "decision": cert.get("decision"),
            "complete": cert.get("complete"),
            "k_invalid": cert.get("k_invalid"),
            "p_hat": cert.get("p_hat"),
            "ucb95": cert.get("ucb95"),
            "method": cert.get("method"),
            "epsilon": cert.get("epsilon"),
            "n_unadjudicated": cert.get("n_unadjudicated"),
            "strata": cert.get("strata"),
        }
        write_json(certificate_path, cert)
        with Path(verdicts_path).open("w", encoding="utf-8") as fh:
            for v in verdicts:
                fh.write(json.dumps(v, ensure_ascii=False) + "\n")
        write_json(summary_path, summary)
        return summary

    def dispatch(tid: str, task_dir: Path, sha: str | None, batch: list[tuple[str, str, int]]) -> list[dict]:
        """Run one batch of (task, probe, rep) trials concurrently; persist rows."""
        batch_rows: list[dict] = []
        with ThreadPoolExecutor(max_workers=max(1, int(concurrency))) as pool:
            futures = {}
            for _tid, probe, rep in batch:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                job_name = f"{slug_for(tid)}-{probe}-r{rep}-{stamp}"
                agent = "nop" if probe == "nop" else "oracle"
                futures[
                    pool.submit(
                        trial_runner, task_dir, agent, jobs_dir, job_name
                    )
                ] = (tid, probe, rep, job_name)
            for fut in as_completed(futures):
                _tid, probe, rep, job_name = futures[fut]
                try:
                    run = fut.result()
                except Exception as exc:
                    run = {
                        "status": "infra",
                        "reward": None,
                        "elapsed_sec": 0.0,
                        "stderr_tail": f"{type(exc).__name__}: {exc}",
                        "test_stdout_tail": "",
                        "skip_reason": "runner_exception",
                    }
                status = run.get("status") or "infra"
                if status == "skipped_heavy":
                    status = "infra"
                row = build_trial_row(
                    task_id=tid,
                    probe=probe,
                    rep=rep,
                    reward=run.get("reward"),
                    status=status,
                    elapsed_sec=float(run.get("elapsed_sec") or 0.0),
                    test_stdout_tail=tail_lines(run.get("test_stdout_tail") or "", STDOUT_TAIL_LINES),
                    stderr_tail=(run.get("stderr_tail") or "")[-STDERR_TAIL_CHARS:],
                    skip_reason=run.get("skip_reason"),
                    job_name=job_name,
                    path=str(task_dir),
                    sha256=sha,
                )
                persist(row)
                batch_rows.append(row)
                _progress(
                    f"{tid} {probe} r{rep} status={row['status']} "
                    f"reward={row['reward']} elapsed={row['elapsed_sec']:.1f}s "
                    f"remaining={remaining():.0f}s"
                )
        return batch_rows

    ids = [str(x) for x in manifest["ids"]]
    planned = tuple((p, k) for p in probe_list)
    n_since_prune = 0

    _progress(
        f"tasks={len(ids)} k={k} probes={probe_list} concurrency={concurrency} "
        f"resume_rows={len(existing)} done={len(done)} budget_sec={budget_sec}"
    )

    for i, tid in enumerate(ids):
        meta = tasks_meta.get(tid) or {}
        task_dir = Path(meta.get("path") or "")
        if not task_dir.is_dir() and meta.get("source") == "tar":
            try:
                task_dir = materialize_task(
                    {"kind": "tar", "tar": meta.get("tar"), "member": meta.get("member")},
                    extract_dir,
                )
            except (OSError, tarfile.TarError, KeyError) as exc:
                _progress(f"{tid} re-extract failed: {type(exc).__name__}: {exc}")
        sha = meta.get("sha256")
        wanted = [(tid, probe, rep) for probe, kk in planned for rep in range(kk)]
        pending = [key for key in wanted if key not in done]

        if pending and not task_dir.is_dir():
            for _tid, probe, rep in pending:
                persist(
                    build_trial_row(
                        task_id=tid,
                        probe=probe,
                        rep=rep,
                        reward=None,
                        status="infra",
                        elapsed_sec=0.0,
                        skip_reason="missing_task_dir",
                        path=str(task_dir),
                        sha256=sha,
                    )
                )
            pending = []

        kind = detect_verifier_kind(task_dir, []) if task_dir.is_dir() else "execution"
        if pending and kind == "judge":
            for _tid, probe, rep in pending:
                persist(
                    build_trial_row(
                        task_id=tid,
                        probe=probe,
                        rep=rep,
                        reward=None,
                        status="judge_stratum",
                        elapsed_sec=0.0,
                        skip_reason="judge verifier needs JUDGE_MODELS env; own stratum (doc 44)",
                        path=str(task_dir),
                        sha256=sha,
                    )
                )
            pending = []
        elif pending and kind == "none":
            for _tid, probe, rep in pending:
                if probe != "oracle":
                    continue
                persist(
                    build_trial_row(
                        task_id=tid,
                        probe=probe,
                        rep=rep,
                        reward=None,
                        status="no_reference",
                        elapsed_sec=0.0,
                        skip_reason="no solution/ shipped (doc 44)",
                        path=str(task_dir),
                        sha256=sha,
                    )
                )
            pending = [k_ for k_ in pending if k_[1] != "oracle"]

        if pending and remaining() <= 0:
            for _tid, probe, rep in pending:
                persist(
                    build_trial_row(
                        task_id=tid,
                        probe=probe,
                        rep=rep,
                        reward=None,
                        status="not_run",
                        elapsed_sec=0.0,
                        skip_reason="budget_sec exhausted",
                        path=str(task_dir),
                        sha256=sha,
                    )
                )
            pending = []

        if pending and warmup:
            # Warm the image first: the first pending trial runs alone so
            # its build populates the docker layer cache, then the rest fan
            # out concurrently.
            warm_rows = dispatch(tid, task_dir, sha, pending[:1])
            pending = pending[1:]
            if warm_rows[0]["status"] == "infra":
                _progress(
                    f"{tid} warmup trial infra; recording {len(pending)} "
                    "remaining trials not_run"
                )
                for _tid, probe, rep in pending:
                    persist(
                        build_trial_row(
                            task_id=tid,
                            probe=probe,
                            rep=rep,
                            reward=None,
                            status="not_run",
                            elapsed_sec=0.0,
                            skip_reason="warmup trial infra; same failed build expected",
                            path=str(task_dir),
                            sha256=sha,
                        )
                    )
                pending = []

        if pending:
            dispatch(tid, task_dir, sha, pending)

        removed = maintenance.rm_task_containers(task_dir)
        if removed:
            _progress(f"{tid} docker rm {len(removed)} leftover containers")
        n_since_prune += 1
        if prune_every > 0 and n_since_prune >= prune_every:
            reclaimed = maintenance.prune()
            entry = {
                "event": "prune",
                "after_tasks": i + 1,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                **reclaimed,
            }
            maintenance_log.append(entry)
            _progress(
                f"prune after {i + 1} tasks: "
                f"images={reclaimed.get('image_bytes')}B "
                f"builder={reclaimed.get('builder_bytes')}B"
            )
            n_since_prune = 0
        dump_outputs()

    summary = dump_outputs()
    public = {k_: summary[k_] for k_ in summary if k_ != "tasks"}
    print(json.dumps(public, indent=2, default=str), flush=True)
    return summary
