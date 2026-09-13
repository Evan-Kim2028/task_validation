"""LLM-judge verifier interrogation for Harbor-Index tasks (doc 44).

A task is judge-verified when its verifier files declare JUDGE_MODELS /
JUDGE_REPEATS. The runner supplies the judge env the task declares via
`harbor run --verifier-env` and never substitutes a different judge.

Each judge task gets k fresh-container verifier runs on the reference
output (--agent oracle) and k on the nop output (--agent nop). Per-run
reward, judge agreement, judge model id and version, and the verifier's
own detail JSON are recorded. Judge nondeterminism is a verifier
property: all k verdicts are kept, never averaged into a majority.

No judge call happens unless the required env is present. Tasks missing
keys get missing_judge_env rows; nothing is fabricated.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from task_validation.evidence.harbor_index_control import (
    catalog_task,
    discover_index_tasks,
    order_catalog,
    source_benchmark,
    summary_path_for,
)
from task_validation.evidence.tb21_pairs import (
    STDERR_TAIL_CHARS,
    STDOUT_TAIL_LINES,
    _job_log_text,
    _kill_pg,
    _looks_infra,
    _still_building,
    append_jsonl,
    load_existing_rows,
    read_reward,
    read_test_stdout,
    tail_lines,
    write_json,
)

BUDGET_SEC = 4 * 60 * 60
TRIAL_CAP_SEC = 30 * 60
BUILD_HEAVY_SEC = 30 * 60 + 3600
K_DEFAULT = 3
DEFAULT_DATASET = Path("/home/evan/Documents/harbor-index-dataset/harbor-index-1.0")
DEFAULT_JOBS = Path("/tmp/tv-hindex/judge-jobs")
DEFAULT_OUT = Path("data/gold/harbor_index_judge.jsonl")
DEFAULT_STRATA = Path("data/gold/harbor_index_strata.json")
DEFAULT_CONTROL = Path("data/gold/harbor_index_control.jsonl")

JUDGE_MARKERS = ("JUDGE_MODELS", "JUDGE_REPEATS")
REQUIRED_JUDGE_ENV = ("JUDGE_MODELS", "JUDGE_REPEATS", "JUDGE_CONCURRENCY")
OPTIONAL_JUDGE_ENV = ("JUDGE_PROVIDER",)
PROVIDER_KEYS = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "deepseek": ("DEEPSEEK_API_KEY",),
}
PROVIDER_BASE_ENV = {
    "openai": "OPENAI_BASE_URL",
    "anthropic": "ANTHROPIC_BASE_URL",
    "deepseek": "DEEPSEEK_API_BASE",
}
JUDGE_DETAIL_GLOB = "*.json"
_DEFAULT_MODEL_RE = re.compile(
    r"""os\.environ\[["']JUDGE_MODELS["']\]\s*=\s*["']([^"']+)["']"""
)


def iter_verifier_files(task_dir: Path) -> list[Path]:
    files: list[Path] = []
    tests = task_dir / "tests"
    if tests.is_dir():
        files.extend(sorted(p for p in tests.rglob("*") if p.is_file()))
    toml = task_dir / "task.toml"
    if toml.is_file():
        files.append(toml)
    return files


def detect_judge(task_dir: Path) -> dict:
    """Static check: does the verifier declare JUDGE_MODELS/JUDGE_REPEATS?"""
    hits = []
    for p in iter_verifier_files(task_dir):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = [m for m in JUDGE_MARKERS if m in text]
        if found:
            hits.append({"file": str(p.relative_to(task_dir)), "markers": found})
    return {"is_judge": bool(hits), "evidence": hits}


def task_default_models(task_dir: Path) -> list[str]:
    """JUDGE_MODELS defaults baked into verifier code, if any."""
    models: list[str] = []
    for p in iter_verifier_files(task_dir):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _DEFAULT_MODEL_RE.finditer(text):
            models.extend(parse_judge_models(m.group(1)))
    return sorted(set(models))


def parse_judge_models(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(m).strip() for m in parsed if str(m).strip()]
    except json.JSONDecodeError:
        pass
    return [m.strip() for m in raw.split(",") if m.strip()]


def provider_for_model(model: str) -> str:
    """Same rule as the tasks' tests/native_judge.py:judge_provider_for_model."""
    low = model.lower()
    if "deepseek" in low:
        return "deepseek"
    if "claude" in low:
        return "anthropic"
    if "gemini" in low:
        return "gemini"
    return "openai"


def required_env(task_dir: Path, models: list[str], environ: dict | None = None) -> dict:
    """Env the official verifier needs for the given judge models."""
    judge_vars = [v for v in REQUIRED_JUDGE_ENV if v != "JUDGE_MODELS" or not task_default_models(task_dir)]
    forced = ((environ or {}).get("JUDGE_PROVIDER") or "").strip().lower()
    providers = {forced} if forced else {provider_for_model(m) for m in models}
    return {
        "judge": judge_vars,
        "provider_any_of": {p: list(PROVIDER_KEYS[p]) for p in sorted(providers) if p in PROVIDER_KEYS},
    }


def missing_env(required: dict, environ: dict) -> list[str]:
    missing = [v for v in required["judge"] if not (environ.get(v) or "").strip()]
    for keys in required["provider_any_of"].values():
        if not any((environ.get(k) or "").strip() for k in keys):
            missing.append("/".join(keys))
    return missing


def judge_passthrough_env(environ: dict, models: list[str]) -> dict[str, str]:
    """Env handed to the verifier via --verifier-env. Only declared names."""
    out: dict[str, str] = {}
    for name in tuple(REQUIRED_JUDGE_ENV) + OPTIONAL_JUDGE_ENV:
        val = (environ.get(name) or "").strip()
        if val:
            out[name] = val
    forced = (environ.get("JUDGE_PROVIDER") or "").strip().lower()
    providers = {forced} if forced else {provider_for_model(m) for m in models}
    for provider in providers:
        if provider not in PROVIDER_KEYS:
            continue
        for key in PROVIDER_KEYS[provider]:
            val = (environ.get(key) or "").strip()
            if val:
                out[key] = val
        base = PROVIDER_BASE_ENV.get(provider)
        if base:
            val = (environ.get(base) or "").strip()
            if val:
                out[base] = val
    return out


def run_harbor_judge(
    task_dir: Path,
    agent: str,
    jobs_out: Path,
    name: str,
    *,
    verifier_env: dict[str, str],
    cap_sec: int = TRIAL_CAP_SEC,
    build_heavy_sec: int = BUILD_HEAVY_SEC,
    harbor_extra_args: list[str] | None = None,
) -> dict:
    """run_harbor_capped plus --verifier-env and judge detail download."""
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
    for key in sorted(verifier_env):
        cmd += ["--ve", f"{key}={verifier_env[key]}"]
    cmd += ["--verifier-include-logs", JUDGE_DETAIL_GLOB]
    if harbor_extra_args:
        cmd += list(harbor_extra_args)
    t0 = time.monotonic()
    timed_out = False
    build_heavy = False
    stderr = ""
    stdout = ""
    elapsed = 0.0
    rc: int | None = None
    proc: subprocess.Popen | None = None
    stdout_path = jobs_out / f"{name}.stdout.log"
    stderr_path = jobs_out / f"{name}.stderr.log"
    with stdout_path.open("w", encoding="utf-8") as so, stderr_path.open("w", encoding="utf-8") as se:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=so,
                stderr=se,
                text=True,
                start_new_session=True,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            stderr = f"{type(exc).__name__}: {exc}"
            proc = None
        while proc is not None:
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
        elapsed = time.monotonic() - t0
        if proc is not None:
            if proc.poll() is None:
                _kill_pg(proc)
            rc = proc.poll()
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
        "skip_reason": "environment_build_exceeded" if build_heavy else None,
    }


def read_judge_details(jobs_out: Path, job_name: str) -> dict:
    """Verifier JSON the task's judge wrote to /logs/verifier."""
    out: dict[str, object] = {}
    for vdir in jobs_out.glob(f"{job_name}/*/verifier"):
        for p in sorted(vdir.glob(JUDGE_DETAIL_GLOB)):
            try:
                out[p.name] = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                out[p.name] = None
    return out


def judge_subruns(details: dict) -> list[dict]:
    """Per-(model, repeat) judge calls inside one verifier run, if logged."""
    runs: list[dict] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            r = node.get("runs")
            if isinstance(r, list):
                for item in r:
                    if isinstance(item, dict) and ("model" in item or "reward" in item):
                        runs.append(item)
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(details)
    return runs


def build_run_row(
    *,
    task_id: str,
    src: str,
    probe: str,
    rep: int,
    reward: float | None,
    status: str,
    elapsed_sec: float,
    judge_models: list[str],
    judge_providers: list[str],
    details: dict | None,
    memory_mb: int | None,
    test_stdout_tail: str,
    stderr_tail: str = "",
    job_name: str | None = None,
    path: str | None = None,
    missing: list[str] | None = None,
) -> dict:
    if status != "executed":
        reward = None
    row = {
        "task_id": task_id,
        "source_benchmark": src,
        "probe": probe,
        "rep": int(rep),
        "intended": "reject" if probe == "nop" else "accept",
        "reward": reward,
        "accepted": (reward == 1.0) if reward is not None else None,
        "status": status,
        "elapsed_sec": float(elapsed_sec),
        "judge_models": list(judge_models),
        "judge_providers": list(judge_providers),
        "judge_runs": judge_subruns(details or {}),
        "detail_files": sorted((details or {}).keys()),
        "memory_mb": memory_mb,
        "test_stdout_tail": test_stdout_tail,
        "stderr_tail": stderr_tail,
        "job_name": job_name,
        "path": path,
    }
    if missing:
        row["missing_env"] = list(missing)
    return row


def run_key(row: dict) -> tuple[str, str, int]:
    return (row["task_id"], row["probe"], int(row.get("rep") or 0))


def agreement_block(trials: list[dict]) -> dict:
    """Doc-44 judge_agreement: every verdict, reference and nop separate."""
    out: dict[str, dict] = {}
    for probe, key in (("oracle", "reference"), ("nop", "nop")):
        runs = [t for t in trials if t.get("probe") == probe]
        executed = [t for t in runs if t.get("status") == "executed" and t.get("reward") is not None]
        accepts = [bool(t["accepted"]) for t in executed]
        entry = {
            "runs": len(runs),
            "executed": len(executed),
            "rewards": [t.get("reward") for t in runs],
            "verdicts": accepts,
        }
        if probe == "oracle":
            entry["accepts"] = sum(accepts)
        else:
            entry["rejects"] = sum(1 for a in accepts if not a)
        out[key] = entry
    return out


def summarize_rows(rows: list[dict], *, wall_clock_total: float, n_judge_tasks: int) -> dict:
    by_task: dict[str, list[dict]] = {}
    for row in rows:
        by_task.setdefault(row["task_id"], []).append(row)
    tasks: dict[str, dict] = {}
    for tid, trials in sorted(by_task.items()):
        models: set[str] = set()
        providers: set[str] = set()
        for t in trials:
            models.update(t.get("judge_models") or [])
            providers.update(t.get("judge_providers") or [])
        missing = next((t.get("missing_env") for t in trials if t.get("missing_env")), None)
        tasks[tid] = {
            "judge_agreement": agreement_block(trials),
            "judge_models": sorted(models),
            "judge_providers": sorted(providers),
            "statuses": sorted({str(t.get("status") or "") for t in trials}),
            "missing_env": missing,
        }
    n_ran = sum(
        1 for t in tasks.values() if "executed" in t["statuses"]
    )
    return {
        "n_judge_tasks": n_judge_tasks,
        "n_tasks_with_rows": len(tasks),
        "n_tasks_ran": n_ran,
        "n_runs": len(rows),
        "tasks": tasks,
        "wall_clock_total": float(wall_clock_total),
        "note": (
            "judge agreement keeps all k verdicts per output; a judge that "
            "flips on identical output is a verifier property (doc 44)"
        ),
    }


def audit_task(task_dir: Path, environ: dict) -> dict:
    """What this task's verifier requires, and what the env is missing."""
    env_models = parse_judge_models(environ.get("JUDGE_MODELS", ""))
    defaults = task_default_models(task_dir)
    models = env_models or defaults
    req = required_env(task_dir, models, environ)
    missing = missing_env(req, environ)
    forced = (environ.get("JUDGE_PROVIDER") or "").strip().lower()
    providers = {forced} if forced else {provider_for_model(m) for m in models}
    return {
        "task_id": task_dir.name,
        "judge_models": models,
        "judge_models_source": "JUDGE_MODELS" if env_models else ("task_default" if defaults else "none"),
        "judge_providers": sorted(providers),
        "required_env": req["judge"],
        "required_provider_keys": req["provider_any_of"],
        "missing_env": missing,
        "runnable": not missing,
    }


def build_strata(dataset: Path, control_path: Path | None = DEFAULT_CONTROL) -> dict:
    """Map every Harbor-Index task id to its verifier stratum (doc 44)."""
    dataset = Path(dataset)
    control: dict[str, dict] = {}
    if control_path is not None and Path(control_path).is_file():
        for row in load_existing_rows(Path(control_path)):
            slot = control.setdefault(str(row["task_id"]), {})
            probe = row.get("probe")
            if probe in ("oracle", "nop"):
                slot[f"{probe}_status"] = row.get("status")
                slot[f"{probe}_reward"] = row.get("reward")
    tasks: dict[str, dict] = {}
    counts = {"execution": 0, "judge": 0, "none": 0}
    ids_by_stratum: dict[str, list[str]] = {"execution": [], "judge": [], "none": []}
    for task_dir in discover_index_tasks(dataset):
        det = detect_judge(task_dir)
        has_ref = (task_dir / "solution").is_dir()
        if det["is_judge"]:
            stratum = "judge"
        elif not has_ref:
            stratum = "none"
        else:
            stratum = "execution"
        counts[stratum] += 1
        ids_by_stratum[stratum].append(task_dir.name)
        tasks[task_dir.name] = {
            "stratum": stratum,
            "source_benchmark": source_benchmark(task_dir.name),
            "has_reference": has_ref,
            "judge_evidence": [h["file"] for h in det["evidence"]],
            "control": control.get(task_dir.name) or None,
        }
    return {
        "dataset": str(dataset),
        "n_tasks": len(tasks),
        "strata_counts": counts,
        "ids_by_stratum": {k: sorted(v) for k, v in ids_by_stratum.items()},
        "tasks": tasks,
        "note": (
            "stratum is the verifier kind (doc 44): judge = verifier files "
            "declare JUDGE_MODELS/JUDGE_REPEATS; none = no reference shipped; "
            "execution otherwise. Doc 28 counts 15 judge outcomes: the 16th, "
            "hle-shock-wave-density-profile, went infra in the control run but "
            "is judge-configured and stays in the judge stratum."
        ),
        "source": [
            str(control_path) if control_path else None,
            "data/gold/harbor_index_control.summary.json",
        ],
    }


def run_experiment(
    *,
    dataset: Path,
    jobs_dir: Path,
    out_path: Path,
    summary_path: Path | None = None,
    k: int = K_DEFAULT,
    budget_sec: float = BUDGET_SEC,
    trial_cap_sec: int = TRIAL_CAP_SEC,
    task_filter: list[str] | None = None,
    environ: dict | None = None,
    resume: bool = True,
) -> dict:
    dataset = Path(dataset).resolve()
    jobs_dir = Path(jobs_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(out_path)
    if summary_path is None:
        summary_path = summary_path_for(out_path)
    environ = dict(os.environ if environ is None else environ)

    catalog = []
    for task_dir in discover_index_tasks(dataset):
        if not detect_judge(task_dir)["is_judge"]:
            continue
        meta = catalog_task(task_dir)
        if task_filter and meta["task_id"] not in task_filter:
            continue
        meta["audit"] = audit_task(task_dir, environ)
        catalog.append(meta)
    catalog = order_catalog(catalog)

    t_start = time.monotonic()
    existing = load_existing_rows(out_path) if resume else []
    done = {run_key(r) for r in existing}
    rows = list(existing)

    def persist(row: dict) -> None:
        rows.append(row)
        done.add(run_key(row))
        append_jsonl(out_path, row)

    def remaining() -> float:
        return budget_sec - (time.monotonic() - t_start)

    def dump_summary() -> dict:
        summary = summarize_rows(
            rows,
            wall_clock_total=time.monotonic() - t_start,
            n_judge_tasks=len(catalog),
        )
        summary["dataset"] = str(dataset)
        summary["k"] = k
        write_json(summary_path, summary)
        return summary

    print(
        f"[judge_verifier] judge_tasks={len(catalog)} k={k} "
        f"resume_rows={len(existing)} budget_sec={budget_sec}",
        flush=True,
    )

    for meta in catalog:
        tid = meta["task_id"]
        audit = meta["audit"]
        task_dir = Path(meta["path"])
        missing = audit["missing_env"]
        if missing:
            for probe in ("oracle", "nop"):
                for rep in range(k):
                    if (tid, probe, rep) in done:
                        continue
                    persist(
                        build_run_row(
                            task_id=tid,
                            src=meta["source_benchmark"],
                            probe=probe,
                            rep=rep,
                            reward=None,
                            status="missing_judge_env",
                            elapsed_sec=0.0,
                            judge_models=audit["judge_models"],
                            judge_providers=audit["judge_providers"],
                            details=None,
                            memory_mb=meta["memory_mb"],
                            test_stdout_tail="",
                            path=str(task_dir),
                            missing=missing,
                        )
                    )
            print(f"[judge_verifier] {tid} missing_judge_env: {', '.join(missing)}", flush=True)
            dump_summary()
            continue

        verifier_env = judge_passthrough_env(environ, audit["judge_models"])
        for probe in ("oracle", "nop"):
            agent = "oracle" if probe == "oracle" else "nop"
            for rep in range(k):
                if (tid, probe, rep) in done:
                    continue
                if remaining() <= 0:
                    persist(
                        build_run_row(
                            task_id=tid,
                            src=meta["source_benchmark"],
                            probe=probe,
                            rep=rep,
                            reward=None,
                            status="not_run",
                            elapsed_sec=0.0,
                            judge_models=audit["judge_models"],
                            judge_providers=audit["judge_providers"],
                            details=None,
                            memory_mb=meta["memory_mb"],
                            test_stdout_tail="",
                            path=str(task_dir),
                        )
                    )
                    continue
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                job_name = f"{tid}-{probe}-{rep}-{stamp}"
                print(f"[judge_verifier] {tid} {probe} rep={rep} -> {job_name}", flush=True)
                run = run_harbor_judge(
                    task_dir,
                    agent,
                    jobs_dir,
                    job_name,
                    verifier_env=verifier_env,
                    cap_sec=int(trial_cap_sec),
                )
                details = read_judge_details(jobs_dir, job_name)
                persist(
                    build_run_row(
                        task_id=tid,
                        src=meta["source_benchmark"],
                        probe=probe,
                        rep=rep,
                        reward=run["reward"],
                        status=run["status"],
                        elapsed_sec=run["elapsed_sec"],
                        judge_models=audit["judge_models"],
                        judge_providers=audit["judge_providers"],
                        details=details,
                        memory_mb=meta["memory_mb"],
                        test_stdout_tail=tail_lines(run.get("test_stdout_tail") or "", STDOUT_TAIL_LINES),
                        stderr_tail=run.get("stderr_tail") or "",
                        job_name=job_name,
                        path=str(task_dir),
                    )
                )
                print(
                    f"[judge_verifier] {tid} {probe} rep={rep} "
                    f"status={run['status']} reward={run['reward']} "
                    f"elapsed={run['elapsed_sec']:.1f}s remaining={remaining():.0f}s",
                    flush=True,
                )
            dump_summary()

    summary = dump_summary()
    public = {k_: summary[k_] for k_ in summary if k_ != "tasks"}
    public["per_task"] = {
        tid: {
            "judge_models": t["judge_models"],
            "missing_env": t["missing_env"],
            "statuses": t["statuses"],
            "judge_agreement": t["judge_agreement"],
        }
        for tid, t in (summary.get("tasks") or {}).items()
    }
    print(json.dumps(public, indent=2, default=str), flush=True)
    return summary


def list_judge_tasks(dataset: Path, environ: dict, *, control_path: Path | None = DEFAULT_CONTROL) -> dict:
    audits = [
        audit_task(task_dir, environ)
        for task_dir in discover_index_tasks(Path(dataset))
        if detect_judge(task_dir)["is_judge"]
    ]
    audits.sort(key=lambda a: a["task_id"])
    strata = build_strata(Path(dataset), control_path)
    return {
        "n_judge_tasks": len(audits),
        "n_runnable": sum(1 for a in audits if a["runnable"]),
        "tasks": audits,
        "strata_counts": strata["strata_counts"],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    p.add_argument("--jobs", type=Path, default=DEFAULT_JOBS)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--summary", type=Path, default=None)
    p.add_argument("--control", type=Path, default=DEFAULT_CONTROL)
    p.add_argument("--strata-out", type=Path, default=None)
    p.add_argument("--task", default="", help="comma-separated task ids; default all judge tasks")
    p.add_argument("--k", type=int, default=K_DEFAULT)
    p.add_argument("--budget-sec", type=float, default=BUDGET_SEC)
    p.add_argument("--trial-cap-sec", type=int, default=TRIAL_CAP_SEC)
    p.add_argument("--list", action="store_true", help="enumerate judge tasks and audit env; never runs harbor")
    p.add_argument("--no-resume", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        report = list_judge_tasks(args.dataset, dict(os.environ), control_path=args.control)
        if args.strata_out is not None:
            strata = build_strata(args.dataset, args.control)
            write_json(Path(args.strata_out), strata)
            report["strata_out"] = str(args.strata_out)
            report["n_strata_tasks"] = strata["n_tasks"]
        print(json.dumps(report, indent=2))
        return 0
    if args.strata_out is not None:
        write_json(Path(args.strata_out), build_strata(args.dataset, args.control))
    task_filter = [t.strip() for t in args.task.split(",") if t.strip()] or None
    run_experiment(
        dataset=args.dataset,
        jobs_dir=args.jobs,
        out_path=args.out,
        summary_path=args.summary,
        k=args.k,
        budget_sec=args.budget_sec,
        trial_cap_sec=args.trial_cap_sec,
        task_filter=task_filter,
        resume=not args.no_resume,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
