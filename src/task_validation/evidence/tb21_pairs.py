"""Natural counterfactual: Terminal-Bench 2.0 vs 2.1 maintained tasks.

Runs official Harbor oracle/nop on PRE (TB 2.0) and POST (TB 2.1).
No LLM. No synthetic tasks. Never fabricates a reward.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from task_validation.ingest.harbor_task import _parse_toml_lite, _read
from task_validation.ingest.tb_maintenance import TB21_CHANGED

IGNORE_REL = frozenset({".gitignore", "README.md"})
CLASS_ORDER = ("test_fix", "solution_fix", "misspec", "docker_env", "resource_timeout")
EXPERIMENT_CLASSES = ("test_fix", "solution_fix", "resource_timeout")
TRIAL_CAP_SEC = 40 * 60
ORACLE2_UNDER_SEC = 5 * 60
BUILD_HEAVY_SEC = 20 * 60
BUDGET_SEC = 6 * 60 * 60
MEMORY_SKIP_MB = 16 * 1024
STDOUT_TAIL_LINES = 40
STDERR_TAIL_CHARS = 2000

INFRA_MARKERS = (
    "failed to pull",
    "pull access denied",
    "error pulling",
    "build failed",
    "failed to solve",
    "failed to build",
    "cannot connect to the docker daemon",
    "error during connect",
    "no space left on device",
    "docker: ",
    "failed to fetch",
    "manifest unknown",
    "not found: manifest",
    "denied: requested access",
)

DEFAULT_PRE = Path("/home/evan/Documents/tb2-pre")
DEFAULT_POST = Path("/home/evan/Documents/terminal-bench-2-1/tasks")
DEFAULT_GOLD = Path("data/gold/tb21_maintenance.jsonl")
DEFAULT_JOBS = Path("/tmp/tv-tb21/jobs")
DEFAULT_OUT = Path("data/gold/tb21_pairs.jsonl")
DEFAULT_SUMMARY = Path("data/gold/tb21_pairs.summary.json")


def load_maintained_ids(path: Path | None = None) -> list[str]:
    if path is None or not path.is_file():
        return list(TB21_CHANGED)
    out: list[str] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            tid = rec.get("task_id")
            if tid:
                out.append(str(tid))
    return out or list(TB21_CHANGED)


def file_map(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in {".git", "__pycache__", ".pytest_cache"} for part in p.parts):
            continue
        rel = p.relative_to(root).as_posix()
        try:
            out[rel] = p.read_bytes()
        except OSError:
            out[rel] = b""
    return out


def files_differ(pre: Path, post: Path, *, ignore: frozenset[str] = IGNORE_REL) -> list[str]:
    a = file_map(pre)
    b = file_map(post)
    changed = []
    for rel in sorted(set(a) | set(b)):
        if rel in ignore or Path(rel).name in ignore:
            continue
        if a.get(rel) != b.get(rel):
            changed.append(rel)
    return changed


def parse_fields(task_dir: Path) -> dict[str, str]:
    return _parse_toml_lite(_read(task_dir / "task.toml") or "")


def _num(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw).strip().strip('"').strip("'"))
    except ValueError:
        return None


def parse_memory_mb(fields: dict[str, str]) -> int | None:
    raw = fields.get("environment.memory_mb")
    n = _num(raw)
    if n is not None:
        return int(n)
    raw = (fields.get("environment.memory") or "").strip().strip('"').strip("'")
    if not raw:
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([gGmMkK]i?b?)?$", raw)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "m").lower()
    if unit.startswith("g"):
        return int(val * 1024)
    if unit.startswith("k"):
        return int(val / 1024.0)
    return int(val)


def parse_gpus(fields: dict[str, str]) -> int:
    n = _num(fields.get("environment.gpus"))
    return int(n) if n is not None else 0


def parse_cpus(fields: dict[str, str]) -> float | None:
    return _num(fields.get("environment.cpus"))


def resource_values_changed(pre_fields: dict[str, str], post_fields: dict[str, str]) -> bool:
    pre_mem = parse_memory_mb(pre_fields)
    post_mem = parse_memory_mb(post_fields)
    if pre_mem is not None and post_mem is not None and pre_mem != post_mem:
        return True
    pre_cpus = parse_cpus(pre_fields)
    post_cpus = parse_cpus(post_fields)
    if pre_cpus is not None and post_cpus is not None and pre_cpus != post_cpus:
        return True
    for key in ("environment.build_timeout_sec", "verifier.timeout_sec", "agent.timeout_sec"):
        a, b = _num(pre_fields.get(key)), _num(post_fields.get(key))
        if a is not None and b is not None and a != b:
            return True
    return False


def classes_from_paths(changed: list[str]) -> set[str]:
    classes: set[str] = set()
    for rel in changed:
        if rel == "instruction.md":
            classes.add("misspec")
        elif rel.startswith("tests/"):
            classes.add("test_fix")
        elif rel.startswith("solution/"):
            classes.add("solution_fix")
        elif rel == "environment/Dockerfile" or rel.startswith("environment/"):
            classes.add("docker_env")
    return classes


def classify_task(pre: Path, post: Path) -> dict:
    changed = files_differ(pre, post)
    classes = classes_from_paths(changed)
    toml_changed = "task.toml" in changed
    if toml_changed:
        if not classes:
            classes.add("resource_timeout")
        elif pre.is_dir() and post.is_dir() and resource_values_changed(parse_fields(pre), parse_fields(post)):
            classes.add("resource_timeout")
    ordered = [c for c in CLASS_ORDER if c in classes]
    primary = next((c for c in EXPERIMENT_CLASSES if c in classes), None)
    if primary is None:
        primary = ordered[0] if ordered else "none"
    return {
        "files_differ": changed,
        "change_classes": ordered,
        "change_class": primary,
        "n_files_differ": len(changed),
        "no_change": not changed,
        "resource_only": ordered == ["resource_timeout"],
    }


def sort_key(classification: dict) -> tuple[int, str]:
    classes = set(classification.get("change_classes") or [])
    if "test_fix" in classes or "solution_fix" in classes:
        rank = 0
    elif "misspec" in classes:
        rank = 1
    elif "docker_env" in classes:
        rank = 2
    elif "resource_timeout" in classes:
        rank = 3
    else:
        rank = 4
    return (rank, str(classification.get("task_id") or ""))


def heavy_skip_reason(task_dir: Path) -> str | None:
    if not task_dir.is_dir():
        return None
    fields = parse_fields(task_dir)
    gpus = parse_gpus(fields)
    if gpus > 0:
        return f"gpu={gpus}"
    mem = parse_memory_mb(fields)
    if mem is not None and mem > MEMORY_SKIP_MB:
        return f"memory_mb={mem}>16384"
    return None


def intended_for_probe(probe: str) -> str:
    return "reject" if probe.startswith("nop") else "accept"


def accepted_from_reward(reward: float | None) -> bool | None:
    if reward is None:
        return None
    return reward == 1.0


def build_trial_row(
    *,
    task_id: str,
    version: str,
    commit: str,
    probe: str,
    reward: float | None,
    status: str,
    elapsed_sec: float,
    test_stdout_tail: str,
    change_class: str,
    change_classes: list[str],
    files_differ_list: list[str],
    intended: str | None = None,
    stderr_tail: str = "",
    skip_reason: str | None = None,
    job_name: str | None = None,
    path: str | None = None,
) -> dict:
    if status == "timeout":
        reward = None
    return {
        "task_id": task_id,
        "version": version,
        "commit": commit,
        "probe": probe,
        "intended": intended if intended is not None else intended_for_probe(probe),
        "reward": reward,
        "accepted": accepted_from_reward(reward),
        "status": status,
        "elapsed_sec": float(elapsed_sec),
        "test_stdout_tail": test_stdout_tail,
        "change_class": change_class,
        "change_classes": list(change_classes),
        "files_differ": list(files_differ_list),
        "stderr_tail": stderr_tail,
        "skip_reason": skip_reason,
        "job_name": job_name,
        "path": path,
    }


def _mean_or_first(xs: list[float]) -> float | None:
    return xs[0] if xs else None


def _bool_or_none(flags: list[bool]) -> bool | None:
    if not flags:
        return None
    return any(flags)


def _defect(fr: bool | None, fa: bool | None) -> bool:
    return fr is True or fa is True


def per_task_outcome(rows: list[dict], classification: dict) -> dict:
    by_ver_probe: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        key = (row["version"], row["probe"])
        by_ver_probe.setdefault(key, []).append(row)

    def rewards(version: str, probe: str) -> list[float | None]:
        out = []
        for row in by_ver_probe.get((version, probe), []):
            if row.get("status") == "timeout":
                out.append(None)
            else:
                out.append(row.get("reward"))
        for row in by_ver_probe.get((version, probe + "_2"), []):
            if row.get("status") == "timeout":
                out.append(None)
            else:
                out.append(row.get("reward"))
        return out

    def executed_accept(version: str, family: str) -> list[bool]:
        flags = []
        for probe in (family, family + "_2"):
            for row in by_ver_probe.get((version, probe), []):
                if row.get("status") != "executed" or row.get("reward") is None:
                    continue
                flags.append(bool(row.get("accepted")))
        return flags

    def statuses(version: str) -> list[str]:
        return [row.get("status") or "" for row in rows if row.get("version") == version]

    oracle_pre = executed_accept("pre", "oracle")
    oracle_post = executed_accept("post", "oracle")
    nop_pre = executed_accept("pre", "nop")
    nop_post = executed_accept("post", "nop")

    fr_pre = None if not oracle_pre else (not all(oracle_pre))
    fr_post = None if not oracle_post else (not all(oracle_post))
    fa_pre = None if not nop_pre else any(nop_pre)
    fa_post = None if not nop_post else any(nop_post)

    resource_only = bool(classification.get("resource_only"))
    pre_oracle_pass = oracle_pre and all(oracle_pre)
    reproducible = True
    separated = False
    if resource_only and pre_oracle_pass:
        reproducible = False
        separated = False
    else:
        pre_def = _defect(fr_pre, fa_pre)
        post_clean = (fr_post is False) and (fa_post is False)
        separated = bool(pre_def and post_clean)

    all_status = [row.get("status") for row in rows]
    return {
        "files_differ": classification.get("files_differ") or [],
        "change_classes": classification.get("change_classes") or [],
        "change_class": classification.get("change_class") or "none",
        "resource_only": resource_only,
        "no_change": bool(classification.get("no_change")),
        "pre": {
            "oracle": _mean_or_first([r for r in rewards("pre", "oracle") if r is not None]),
            "nop": _mean_or_first([r for r in rewards("pre", "nop") if r is not None]),
            "oracle_rewards": rewards("pre", "oracle"),
            "nop_rewards": rewards("pre", "nop"),
        },
        "post": {
            "oracle": _mean_or_first([r for r in rewards("post", "oracle") if r is not None]),
            "nop": _mean_or_first([r for r in rewards("post", "nop") if r is not None]),
            "oracle_rewards": rewards("post", "oracle"),
            "nop_rewards": rewards("post", "nop"),
        },
        "false_reject_pre": fr_pre,
        "false_reject_post": fr_post,
        "false_accept_pre": fa_pre,
        "false_accept_post": fa_post,
        "separated": separated,
        "counterfactual_reproducible": reproducible,
        "pre_oracle_pass": pre_oracle_pass,
        "statuses": all_status,
        "skipped_heavy": any(s == "skipped_heavy" for s in all_status),
        "infra": any(s == "infra" for s in all_status),
        "timeout": any(s == "timeout" for s in all_status),
        "diffable": (
            not classification.get("no_change")
            and bool(oracle_pre)
            and bool(oracle_post)
            and bool(nop_pre)
            and bool(nop_post)
        ),
        "pre_status": statuses("pre"),
        "post_status": statuses("post"),
    }


def summarize_rows(
    rows: list[dict],
    classifications: dict[str, dict],
    *,
    wall_clock_total: float,
    skipped: list[dict] | None = None,
) -> dict:
    by_task: dict[str, list[dict]] = {}
    for row in rows:
        by_task.setdefault(row["task_id"], []).append(row)
    tasks: dict[str, dict] = {}
    for tid, cls in classifications.items():
        tasks[tid] = per_task_outcome(by_task.get(tid, []), cls)

    n_separated = sum(1 for t in tasks.values() if t.get("separated"))
    n_no_change = sum(1 for t in tasks.values() if t.get("no_change"))
    n_infra = sum(1 for t in tasks.values() if t.get("infra"))
    n_pairs_diffable = sum(1 for t in tasks.values() if t.get("diffable"))
    n_resource_not_reproducible = sum(
        1
        for t in tasks.values()
        if t.get("resource_only") and t.get("pre_oracle_pass") and not t.get("counterfactual_reproducible")
    )
    n_skipped_heavy = sum(1 for t in tasks.values() if t.get("skipped_heavy"))
    n_timeout = sum(1 for t in tasks.values() if t.get("timeout"))
    return {
        "n_tasks": len(tasks),
        "n_trials": len(rows),
        "n_pairs_diffable": n_pairs_diffable,
        "n_separated": n_separated,
        "n_no_change": n_no_change,
        "n_infra": n_infra,
        "n_timeout": n_timeout,
        "n_skipped_heavy": n_skipped_heavy,
        "n_resource_not_reproducible": n_resource_not_reproducible,
        "wall_clock_total": float(wall_clock_total),
        "tasks": tasks,
        "skipped": skipped or [],
        "note": (
            "separated means pre shows false-reject or false-accept and post does not. "
            "resource_only tasks whose pre oracle passes on this machine are not "
            "counted as separated and are not counted as no-defect."
        ),
    }


def tail_lines(text: str, n: int = STDOUT_TAIL_LINES) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:])


def read_tail_file(path: Path | None, n: int = STDOUT_TAIL_LINES) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        return tail_lines(path.read_text(encoding="utf-8", errors="replace"), n)
    except OSError:
        return ""


def _looks_infra(stderr: str, stdout: str = "") -> bool:
    blob = f"{stderr}\n{stdout}".lower()
    return any(m in blob for m in INFRA_MARKERS)


def _latest_path(jobs_out: Path, job_name: str, rel: str) -> Path | None:
    matches = list(jobs_out.glob(f"{job_name}/*/{rel}"))
    if not matches:
        matches = list(jobs_out.glob(f"*/{rel}"))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def read_reward(jobs_out: Path, job_name: str) -> float | None:
    path = _latest_path(jobs_out, job_name, "verifier/reward.txt")
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        return float(text.split()[0])
    except (OSError, ValueError):
        return None


def read_test_stdout(jobs_out: Path, job_name: str) -> str:
    path = _latest_path(jobs_out, job_name, "verifier/test-stdout.txt")
    return read_tail_file(path, STDOUT_TAIL_LINES)


def _kill_pg(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            return
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _job_log_text(jobs_out: Path, job_name: str) -> str:
    p = jobs_out / job_name / "job.log"
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8", errors="replace")[-8000:]
        except OSError:
            return ""
    return ""


def _still_building(jobs_out: Path, job_name: str) -> bool:
    text = _job_log_text(jobs_out, job_name).lower()
    if not text:
        return False
    buildish = any(
        s in text
        for s in (
            "building",
            "docker build",
            "exporting to image",
            "pulling fs layer",
            "pulling from",
            "load build definition",
        )
    )
    agent_started = "agent" in text and ("started" in text or "running oracle" in text or "running nop" in text)
    return buildish and not agent_started


def run_harbor_capped(
    task_dir: Path,
    agent: str,
    jobs_out: Path,
    name: str,
    *,
    cap_sec: int = TRIAL_CAP_SEC,
    build_heavy_sec: int = BUILD_HEAVY_SEC,
) -> dict:
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
        "1",
        "--job-name",
        name,
        "-o",
        str(jobs_out),
    ]
    t0 = time.monotonic()
    timed_out = False
    build_heavy = False
    stdout = ""
    stderr = ""
    rc: int | None = None
    stdout_path = jobs_out / f"{name}.stdout.log"
    stderr_path = jobs_out / f"{name}.stderr.log"
    so = stdout_path.open("w", encoding="utf-8")
    se = stderr_path.open("w", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=so,
            stderr=se,
            text=True,
            start_new_session=True,
        )
        try:
            while True:
                elapsed = time.monotonic() - t0
                remaining = cap_sec - elapsed
                if remaining <= 0:
                    timed_out = True
                    _kill_pg(proc)
                    break
                if (
                    elapsed >= build_heavy_sec
                    and read_reward(jobs_out, name) is None
                    and _still_building(jobs_out, name)
                ):
                    build_heavy = True
                    _kill_pg(proc)
                    break
                rc = proc.poll()
                if rc is not None:
                    break
                time.sleep(min(5.0, max(0.5, remaining)))
        except Exception as exc:
            stderr = f"{type(exc).__name__}: {exc}"
            _kill_pg(proc)
        elapsed = time.monotonic() - t0
        if proc.poll() is None:
            _kill_pg(proc)
        rc = proc.poll()
    finally:
        so.close()
        se.close()
    try:
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = (stderr + "\n" + stderr_path.read_text(encoding="utf-8", errors="replace")).strip()
    except OSError:
        pass
    reward = read_reward(jobs_out, name)
    test_stdout_tail = read_test_stdout(jobs_out, name)
    err_tail = (stderr or "")[-STDERR_TAIL_CHARS:]
    if not err_tail:
        err_tail = _job_log_text(jobs_out, name)[-STDERR_TAIL_CHARS:]
    if reward is not None:
        status = "executed"
    elif build_heavy:
        status = "skipped_heavy"
        reward = None
    elif timed_out:
        status = "timeout"
        reward = None
    else:
        status = "infra"
        reward = None
        if not _looks_infra(err_tail, stdout or "") and rc == 0:
            status = "infra"
    return {
        "cmd": cmd,
        "returncode": rc,
        "elapsed_sec": elapsed,
        "reward": reward,
        "status": status,
        "stderr_tail": err_tail,
        "test_stdout_tail": test_stdout_tail,
        "skip_reason": "environment_build_exceeded_20min" if build_heavy else None,
    }


def git_head(path: Path) -> str:
    repo = path if (path / ".git").exists() else path
    if not (repo / ".git").exists():
        repo = path.parent
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
            timeout=15,
        )
        return out.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def trial_key(row: dict) -> tuple[str, str, str]:
    return (row["task_id"], row["version"], row["probe"])


def load_existing_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_json(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def classify_all(ids: list[str], pre_root: Path, post_root: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for tid in ids:
        rec = classify_task(pre_root / tid, post_root / tid)
        rec["task_id"] = tid
        rec["pre_path"] = str(pre_root / tid)
        rec["post_path"] = str(post_root / tid)
        rec["pre_exists"] = (pre_root / tid).is_dir()
        rec["post_exists"] = (post_root / tid).is_dir()
        out[tid] = rec
    return out


def ordered_task_ids(classifications: dict[str, dict]) -> list[str]:
    items = list(classifications.values())
    items.sort(key=sort_key)
    return [c["task_id"] for c in items]


def skip_row(
    *,
    task_id: str,
    version: str,
    commit: str,
    probe: str,
    status: str,
    reason: str,
    classification: dict,
    path: str | None,
) -> dict:
    return build_trial_row(
        task_id=task_id,
        version=version,
        commit=commit,
        probe=probe,
        reward=None,
        status=status,
        elapsed_sec=0.0,
        test_stdout_tail="",
        change_class=classification.get("change_class") or "none",
        change_classes=classification.get("change_classes") or [],
        files_differ_list=classification.get("files_differ") or [],
        skip_reason=reason,
        path=path,
    )


def run_experiment(
    *,
    pre_root: Path,
    post_root: Path,
    gold: Path,
    jobs_dir: Path,
    out_path: Path,
    summary_path: Path,
    budget_sec: float = BUDGET_SEC,
    trial_cap_sec: int = TRIAL_CAP_SEC,
    oracle2_under_sec: float = ORACLE2_UNDER_SEC,
    classify_only: bool = False,
    resume: bool = True,
) -> dict:
    ids = load_maintained_ids(gold)
    classifications = classify_all(ids, pre_root, post_root)
    pre_commit = git_head(pre_root)
    post_commit = git_head(post_root)
    commits = {"pre": pre_commit, "post": post_commit}
    t_start = time.monotonic()
    skipped: list[dict] = []

    if classify_only:
        summary = summarize_rows([], classifications, wall_clock_total=0.0, skipped=skipped)
        summary["classifications"] = classifications
        summary["commits"] = commits
        summary["ordered_ids"] = ordered_task_ids(classifications)
        write_json(summary_path, summary)
        return summary

    existing = load_existing_rows(out_path) if resume else []
    done = {trial_key(r) for r in existing}
    rows = list(existing)
    versions = (
        ("pre", pre_root, commits["pre"]),
        ("post", post_root, commits["post"]),
    )

    def persist(row: dict) -> None:
        rows.append(row)
        done.add(trial_key(row))
        append_jsonl(out_path, row)

    def remaining() -> float:
        return budget_sec - (time.monotonic() - t_start)

    def dump_summary() -> dict:
        wall = time.monotonic() - t_start
        summary = summarize_rows(rows, classifications, wall_clock_total=wall, skipped=skipped)
        summary["classifications"] = {k: {kk: vv for kk, vv in v.items() if kk != "task_id"} for k, v in classifications.items()}
        summary["commits"] = commits
        summary["ordered_ids"] = ordered_task_ids(classifications)
        write_json(summary_path, summary)
        return summary

    for tid in ordered_task_ids(classifications):
        cls = classifications[tid]
        if remaining() <= 0:
            for version, root, commit in versions:
                for probe in ("oracle", "nop"):
                    key = (tid, version, probe)
                    if key in done:
                        continue
                    persist(
                        skip_row(
                            task_id=tid,
                            version=version,
                            commit=commit,
                            probe=probe,
                            status="skipped_budget",
                            reason="wall_clock>6h",
                            classification=cls,
                            path=str(root / tid),
                        )
                    )
            skipped.append({"task_id": tid, "reason": "wall_clock>6h", "status": "skipped_budget"})
            continue

        heavy = None
        for version, root, _commit in versions:
            reason = heavy_skip_reason(root / tid)
            if reason:
                heavy = f"{version}:{reason}"
                break
        if heavy:
            for version, root, commit in versions:
                for probe in ("oracle", "nop"):
                    if (tid, version, probe) in done:
                        continue
                    persist(
                        skip_row(
                            task_id=tid,
                            version=version,
                            commit=commit,
                            probe=probe,
                            status="skipped_heavy",
                            reason=heavy,
                            classification=cls,
                            path=str(root / tid),
                        )
                    )
            skipped.append({"task_id": tid, "reason": heavy, "status": "skipped_heavy"})
            dump_summary()
            continue

        for version, root, commit in versions:
            task_dir = root / tid
            if remaining() <= 0:
                for probe in ("oracle", "nop"):
                    if (tid, version, probe) in done:
                        continue
                    persist(
                        skip_row(
                            task_id=tid,
                            version=version,
                            commit=commit,
                            probe=probe,
                            status="skipped_budget",
                            reason="wall_clock>6h",
                            classification=cls,
                            path=str(task_dir),
                        )
                    )
                skipped.append({"task_id": tid, "version": version, "reason": "wall_clock>6h", "status": "skipped_budget"})
                break
            if not task_dir.is_dir():
                for probe in ("oracle", "nop"):
                    if (tid, version, probe) in done:
                        continue
                    persist(
                        skip_row(
                            task_id=tid,
                            version=version,
                            commit=commit,
                            probe=probe,
                            status="infra",
                            reason="missing_task_dir",
                            classification=cls,
                            path=str(task_dir),
                        )
                    )
                skipped.append({"task_id": tid, "version": version, "reason": "missing_task_dir", "status": "infra"})
                continue

            probes = ["oracle", "nop"]
            first_oracle_elapsed = None
            abort_version = None
            for probe in probes:
                if remaining() <= 0:
                    if (tid, version, probe) not in done:
                        persist(
                            skip_row(
                                task_id=tid,
                                version=version,
                                commit=commit,
                                probe=probe,
                                status="skipped_budget",
                                reason="wall_clock>6h",
                                classification=cls,
                                path=str(task_dir),
                            )
                        )
                    continue
                if abort_version:
                    if (tid, version, probe) not in done:
                        persist(
                            skip_row(
                                task_id=tid,
                                version=version,
                                commit=commit,
                                probe=probe,
                                status=abort_version[0],
                                reason=abort_version[1],
                                classification=cls,
                                path=str(task_dir),
                            )
                        )
                    continue
                if (tid, version, probe) in done:
                    if probe == "oracle":
                        prev = next(
                            (r for r in rows if trial_key(r) == (tid, version, "oracle")),
                            None,
                        )
                        if prev is not None:
                            first_oracle_elapsed = float(prev.get("elapsed_sec") or 0)
                    continue
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                job_name = f"{tid}-{version}-{probe}-{stamp}"
                print(f"[tb21_pairs] {tid} {version} {probe} -> {job_name}", flush=True)
                run = run_harbor_capped(
                    task_dir,
                    "nop" if probe.startswith("nop") else "oracle",
                    jobs_dir,
                    job_name,
                    cap_sec=trial_cap_sec,
                )
                row = build_trial_row(
                    task_id=tid,
                    version=version,
                    commit=commit,
                    probe=probe,
                    reward=run["reward"],
                    status=run["status"],
                    elapsed_sec=run["elapsed_sec"],
                    test_stdout_tail=run["test_stdout_tail"],
                    change_class=cls.get("change_class") or "none",
                    change_classes=cls.get("change_classes") or [],
                    files_differ_list=cls.get("files_differ") or [],
                    stderr_tail=run["stderr_tail"],
                    skip_reason=run.get("skip_reason"),
                    job_name=job_name,
                    path=str(task_dir),
                )
                persist(row)
                print(
                    f"[tb21_pairs] {tid} {version} {probe} status={row['status']} "
                    f"reward={row['reward']} elapsed={row['elapsed_sec']:.1f}s",
                    flush=True,
                )
                if probe == "oracle":
                    first_oracle_elapsed = float(run["elapsed_sec"])
                    if (
                        run["status"] == "executed"
                        and first_oracle_elapsed < oracle2_under_sec
                        and (tid, version, "oracle_2") not in done
                        and remaining() > 0
                    ):
                        probes.append("oracle_2")
                if run["status"] == "skipped_heavy":
                    abort_version = ("skipped_heavy", run.get("skip_reason") or "environment_build_exceeded_20min")
                    skipped.append(
                        {"task_id": tid, "version": version, "reason": abort_version[1], "status": "skipped_heavy"}
                    )
                elif run["status"] == "infra":
                    abort_version = ("infra", (run.get("stderr_tail") or "")[-400:] or "infra")
                    skipped.append({"task_id": tid, "version": version, "reason": "infra", "status": "infra"})
            dump_summary()

    summary = dump_summary()
    print(json.dumps({k: summary[k] for k in summary if k not in {"tasks", "classifications"}}, indent=2), flush=True)
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TB 2.0 vs 2.1 natural-counterfactual Harbor pairs")
    p.add_argument("--pre", type=Path, default=DEFAULT_PRE)
    p.add_argument("--post", type=Path, default=DEFAULT_POST)
    p.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    p.add_argument("--jobs-dir", type=Path, default=DEFAULT_JOBS)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    p.add_argument("--budget-sec", type=float, default=BUDGET_SEC)
    p.add_argument("--trial-cap-sec", type=int, default=TRIAL_CAP_SEC)
    p.add_argument("--oracle2-under-sec", type=float, default=ORACLE2_UNDER_SEC)
    p.add_argument("--classify-only", action="store_true")
    p.add_argument("--no-resume", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_experiment(
        pre_root=args.pre,
        post_root=args.post,
        gold=args.gold,
        jobs_dir=args.jobs_dir,
        out_path=args.out,
        summary_path=args.summary,
        budget_sec=args.budget_sec,
        trial_cap_sec=args.trial_cap_sec,
        oracle2_under_sec=args.oracle2_under_sec,
        classify_only=args.classify_only,
        resume=not args.no_resume,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
