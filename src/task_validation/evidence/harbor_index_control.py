"""Harbor-Index 1.0 external control: oracle/nop on the audited 82.

No LLM. No synthetic tasks. Never fabricates a reward.
Reuses tb21_pairs.run_harbor_capped for one docker job at a time.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from task_validation.evidence.tb21_pairs import (
    STDOUT_TAIL_LINES,
    append_jsonl,
    load_existing_rows,
    parse_memory_mb,
    run_harbor_capped,
    tail_lines,
    write_json,
)
from task_validation.ingest.harbor_task import _parse_toml_lite, _read

BUDGET_SEC = 8 * 60 * 60
TRIAL_CAP_SEC = 30 * 60
DEFAULT_DATASET = Path("/home/evan/Documents/harbor-index-dataset/harbor-index-1.0")
DEFAULT_JOBS = Path("/tmp/tv-hindex/jobs")
DEFAULT_OUT = Path("data/gold/harbor_index_control.jsonl")
DEFAULT_TB21 = Path("data/gold/tb21_pairs.summary.json")
EVAL_TASKS_PILOT = {
    "n_tasks": 16,
    "n_reference_fails": 2,
    "n_ab_false_accepts": 0,
    "source": "data/gold/harbor_outlier_diagnosis.json",
}

_FAILED_LINE = re.compile(
    r"^(?:FAILED|ERROR)\s+(\S+?)(?:\s+-|\s*$)",
)
_ERROR_COLLECTING = re.compile(r"^ERROR collecting\s+(\S+)")
_UNITTEST_FAIL = re.compile(r"^(?:FAIL|ERROR):\s+(\S+)")
_PYTEST_E = re.compile(r"^\s*E\s+\S")


def source_benchmark(task_id: str) -> str:
    slug = Path(str(task_id)).name
    if "-" not in slug:
        return slug
    return slug.split("-", 1)[0]


def _num(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw).strip().strip('"').strip("'"))
    except ValueError:
        return None


def task_memory_mb(fields: dict[str, str]) -> int | None:
    found: list[int] = []
    for key in ("environment.memory_mb", "verifier.environment.memory_mb"):
        n = _num(fields.get(key))
        if n is not None:
            found.append(int(n))
    env = parse_memory_mb(fields)
    if env is not None:
        found.append(int(env))
    ver_mem = fields.get("verifier.environment.memory")
    if ver_mem:
        parsed = parse_memory_mb({"environment.memory": ver_mem})
        if parsed is not None:
            found.append(int(parsed))
    return max(found) if found else None


def parse_fields(task_dir: Path) -> dict[str, str]:
    return _parse_toml_lite(_read(task_dir / "task.toml") or "")


def catalog_task(task_dir: Path) -> dict:
    fields = parse_fields(task_dir)
    tid = task_dir.name
    return {
        "task_id": tid,
        "path": task_dir,
        "source_benchmark": source_benchmark(tid),
        "has_reference": (task_dir / "solution").is_dir(),
        "memory_mb": task_memory_mb(fields),
    }


def discover_index_tasks(dataset: Path) -> list[Path]:
    return sorted(p.parent for p in dataset.glob("*/task.toml"))


def order_catalog(catalog: list[dict]) -> list[dict]:
    def key(row: dict) -> tuple[int, str]:
        mem = row.get("memory_mb")
        rank = int(mem) if mem is not None else 10**9
        return (rank, str(row.get("task_id") or ""))

    return sorted(catalog, key=key)


def intended_for_probe(probe: str) -> str:
    return "reject" if str(probe).startswith("nop") else "accept"


def accepted_from_reward(reward: float | None) -> bool | None:
    if reward is None:
        return None
    return reward == 1.0


def extract_failures(text: str) -> dict:
    failing: list[str] = []
    last_error = ""
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        m_col = _ERROR_COLLECTING.match(line)
        if m_col:
            name = m_col.group(1).rstrip(":")
            if name not in seen:
                seen.add(name)
                failing.append(name)
            continue
        m_fail = _FAILED_LINE.match(line)
        if m_fail:
            name = m_fail.group(1)
            if name not in seen:
                seen.add(name)
                failing.append(name)
            continue
        m_ut = _UNITTEST_FAIL.match(line)
        if m_ut:
            name = m_ut.group(1)
            if name not in seen:
                seen.add(name)
                failing.append(name)
        if _PYTEST_E.match(line):
            last_error = line.strip()
    return {"failing_tests": failing, "last_error_line": last_error}


def build_trial_row(
    *,
    task_id: str,
    source_benchmark: str,
    probe: str,
    reward: float | None,
    status: str,
    elapsed_sec: float,
    memory_mb: int | None,
    test_stdout_tail: str,
    intended: str | None = None,
    stderr_tail: str = "",
    job_name: str | None = None,
    path: str | None = None,
    failing_tests: list[str] | None = None,
    last_error_line: str | None = None,
) -> dict:
    if status != "executed":
        reward = None
    accepted = accepted_from_reward(reward)
    row = {
        "task_id": task_id,
        "source_benchmark": source_benchmark,
        "probe": probe,
        "intended": intended if intended is not None else intended_for_probe(probe),
        "reward": reward,
        "accepted": accepted,
        "status": status,
        "elapsed_sec": float(elapsed_sec),
        "memory_mb": memory_mb,
        "test_stdout_tail": test_stdout_tail,
        "stderr_tail": stderr_tail,
        "job_name": job_name,
        "path": path,
    }
    is_ref_fail = (
        row["intended"] == "accept"
        and status == "executed"
        and accepted is False
    )
    if is_ref_fail:
        extracted = extract_failures(test_stdout_tail)
        row["failing_tests"] = failing_tests if failing_tests is not None else extracted["failing_tests"]
        row["last_error_line"] = last_error_line if last_error_line is not None else extracted["last_error_line"]
    return row


def _mean(xs: list[float]) -> float | None:
    return (sum(xs) / len(xs)) if xs else None


def _source_slot() -> dict:
    return {
        "n_tasks": 0,
        "n_with_reference": 0,
        "n_run": 0,
        "n_oracle_executed": 0,
        "n_nop_executed": 0,
        "n_reference_fails": 0,
        "n_nop_passes": 0,
        "n_infra": 0,
        "n_timeout": 0,
        "n_no_reference": 0,
        "n_not_run": 0,
        "correct_accept": None,
        "incorrect_reject": None,
    }


def comparison_block(tb21_path: Path | None) -> dict:
    tb21 = None
    if tb21_path is not None and Path(tb21_path).is_file():
        try:
            data = json.loads(Path(tb21_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict):
            tasks = data.get("tasks") or {}
            n_tasks = int(data.get("n_tasks") or 0)
            n_trials = int(data.get("n_trials") or 0)
            n_fr = sum(1 for t in tasks.values() if isinstance(t, dict) and t.get("false_reject_pre") is True)
            n_fa = sum(1 for t in tasks.values() if isinstance(t, dict) and t.get("false_accept_pre") is True)
            tb21 = {
                "n_tasks": data.get("n_tasks"),
                "n_trials": data.get("n_trials"),
                "n_pairs_diffable": data.get("n_pairs_diffable"),
                "n_separated": data.get("n_separated"),
                "n_infra": data.get("n_infra"),
                "n_timeout": data.get("n_timeout"),
                "n_false_reject_pre": n_fr,
                "n_false_accept_pre": n_fa,
                "wall_clock_total": data.get("wall_clock_total"),
                "complete": n_trials >= max(1, n_tasks) * 2,
                "source": str(tb21_path),
            }
    return {"eval_tasks_pilot": dict(EVAL_TASKS_PILOT), "tb21_pairs": tb21}


def summarize_rows(
    rows: list[dict],
    *,
    wall_clock_total: float,
    n_tasks: int | None = None,
    n_with_reference: int | None = None,
    tb21_path: Path | None = DEFAULT_TB21,
    not_run: list[str] | None = None,
) -> dict:
    by_task: dict[str, list[dict]] = {}
    for row in rows:
        by_task.setdefault(row["task_id"], []).append(row)
    task_ids = list(by_task)
    if n_tasks is None:
        n_tasks = len(task_ids)
    if n_with_reference is None:
        n_with_reference = sum(
            1
            for tid, trials in by_task.items()
            if any(t.get("probe") == "oracle" and t.get("status") != "no_reference" for t in trials)
        )

    def statuses(trials: list[dict]) -> set[str]:
        return {str(t.get("status") or "") for t in trials}

    run_ids = [
        tid
        for tid, trials in by_task.items()
        if statuses(trials) & {"executed", "timeout", "infra"}
    ]
    not_run_ids = [
        tid
        for tid, trials in by_task.items()
        if statuses(trials) and statuses(trials) <= {"not_run"}
    ]
    if not_run is None:
        not_run = not_run_ids

    oracle_exec = [
        r
        for r in rows
        if r.get("probe") == "oracle" and r.get("status") == "executed" and r.get("reward") is not None
    ]
    nop_exec = [
        r
        for r in rows
        if r.get("probe") == "nop" and r.get("status") == "executed" and r.get("reward") is not None
    ]
    n_reference_fails = sum(1 for r in oracle_exec if r.get("accepted") is False)
    n_nop_passes = sum(1 for r in nop_exec if r.get("accepted") is True)
    n_infra = sum(1 for r in rows if r.get("status") == "infra")
    n_timeout = sum(1 for r in rows if r.get("status") == "timeout")
    n_no_reference = sum(1 for r in rows if r.get("status") == "no_reference")

    by_source: dict[str, dict] = {}
    oracle_bits: dict[str, list[float]] = {}
    nop_bits: dict[str, list[float]] = {}
    seen_source_tasks: dict[str, set[str]] = {}
    seen_source_ref: dict[str, set[str]] = {}
    seen_source_run: dict[str, set[str]] = {}
    seen_source_not: dict[str, set[str]] = {}
    for row in rows:
        src = row.get("source_benchmark") or source_benchmark(row["task_id"])
        slot = by_source.setdefault(src, _source_slot())
        tid = row["task_id"]
        seen_source_tasks.setdefault(src, set()).add(tid)
        if row.get("probe") == "oracle" and row.get("status") != "no_reference":
            seen_source_ref.setdefault(src, set()).add(tid)
        if row.get("status") in {"executed", "timeout", "infra"}:
            seen_source_run.setdefault(src, set()).add(tid)
        if row.get("status") == "not_run":
            seen_source_not.setdefault(src, set()).add(tid)
        if row.get("status") == "infra":
            slot["n_infra"] += 1
        if row.get("status") == "timeout":
            slot["n_timeout"] += 1
        if row.get("status") == "no_reference":
            slot["n_no_reference"] += 1
        if row.get("probe") == "oracle" and row.get("status") == "executed" and row.get("reward") is not None:
            slot["n_oracle_executed"] += 1
            oracle_bits.setdefault(src, []).append(1.0 if row.get("accepted") else 0.0)
            if row.get("accepted") is False:
                slot["n_reference_fails"] += 1
        if row.get("probe") == "nop" and row.get("status") == "executed" and row.get("reward") is not None:
            slot["n_nop_executed"] += 1
            nop_bits.setdefault(src, []).append(0.0 if row.get("accepted") else 1.0)
            if row.get("accepted") is True:
                slot["n_nop_passes"] += 1
    for src, slot in by_source.items():
        slot["n_tasks"] = len(seen_source_tasks.get(src, set()))
        slot["n_with_reference"] = len(seen_source_ref.get(src, set()))
        slot["n_run"] = len(seen_source_run.get(src, set()))
        only_not = seen_source_not.get(src, set()) - seen_source_run.get(src, set())
        slot["n_not_run"] = len(only_not)
        slot["correct_accept"] = _mean(oracle_bits.get(src, []))
        slot["incorrect_reject"] = _mean(nop_bits.get(src, []))

    ref_fails = [
        {
            "task_id": r["task_id"],
            "source_benchmark": r.get("source_benchmark"),
            "failing_tests": r.get("failing_tests") or [],
            "last_error_line": r.get("last_error_line") or "",
        }
        for r in oracle_exec
        if r.get("accepted") is False
    ]
    return {
        "n_tasks": n_tasks,
        "n_with_reference": n_with_reference,
        "n_run": len(run_ids),
        "n_trials": len(rows),
        "correct_accept": _mean([1.0 if r.get("accepted") else 0.0 for r in oracle_exec]),
        "incorrect_reject": _mean([0.0 if r.get("accepted") else 1.0 for r in nop_exec]),
        "n_reference_fails": n_reference_fails,
        "n_nop_passes": n_nop_passes,
        "n_infra": n_infra,
        "n_timeout": n_timeout,
        "n_no_reference": n_no_reference,
        "n_not_run": len(not_run),
        "not_run": list(not_run),
        "reference_failures": ref_fails,
        "by_source": dict(sorted(by_source.items())),
        "wall_clock_total": float(wall_clock_total),
        "comparison": comparison_block(tb21_path),
    }


def trial_key(row: dict) -> tuple[str, str]:
    return (row["task_id"], row["probe"])


def summary_path_for(out_path: Path) -> Path:
    name = out_path.name
    if name.endswith(".jsonl"):
        return out_path.with_name(name[: -len(".jsonl")] + ".summary.json")
    return out_path.with_suffix(out_path.suffix + ".summary.json")


def _progress(msg: str) -> None:
    print(f"[harbor_index_control] {msg}", flush=True)


def run_experiment(
    *,
    dataset: Path,
    jobs_dir: Path,
    out_path: Path,
    summary_path: Path | None = None,
    budget_sec: float = BUDGET_SEC,
    trial_cap_sec: int = TRIAL_CAP_SEC,
    tb21_path: Path = DEFAULT_TB21,
    resume: bool = True,
) -> dict:
    dataset = dataset.resolve()
    jobs_dir = Path(jobs_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(out_path)
    if summary_path is None:
        summary_path = summary_path_for(out_path)
    catalog = order_catalog([catalog_task(p) for p in discover_index_tasks(dataset)])
    n_tasks = len(catalog)
    n_with_reference = sum(1 for c in catalog if c["has_reference"])
    t_start = time.monotonic()
    existing = load_existing_rows(out_path) if resume else []
    done = {trial_key(r) for r in existing}
    rows = list(existing)
    not_run: list[str] = []

    def persist(row: dict) -> None:
        rows.append(row)
        done.add(trial_key(row))
        append_jsonl(out_path, row)

    def remaining() -> float:
        return budget_sec - (time.monotonic() - t_start)

    def dump_summary() -> dict:
        wall = time.monotonic() - t_start
        summary = summarize_rows(
            rows,
            wall_clock_total=wall,
            n_tasks=n_tasks,
            n_with_reference=n_with_reference,
            tb21_path=tb21_path,
            not_run=not_run,
        )
        summary["dataset"] = str(dataset)
        summary["n_catalog"] = n_tasks
        write_json(summary_path, summary)
        return summary

    _progress(
        f"catalog n_tasks={n_tasks} n_with_reference={n_with_reference} "
        f"resume_rows={len(existing)} budget_sec={budget_sec} trial_cap_sec={trial_cap_sec}"
    )

    for meta in catalog:
        tid = meta["task_id"]
        src = meta["source_benchmark"]
        mem = meta["memory_mb"]
        task_dir = Path(meta["path"])
        has_ref = bool(meta["has_reference"])
        probes = ["oracle", "nop"] if has_ref else ["oracle", "nop"]
        task_started = False
        for probe in probes:
            key = (tid, probe)
            if key in done:
                prev = next((r for r in rows if trial_key(r) == key), None)
                if prev is not None and prev.get("status") in {"executed", "timeout", "infra"}:
                    task_started = True
                continue
            if probe == "oracle" and not has_ref:
                persist(
                    build_trial_row(
                        task_id=tid,
                        source_benchmark=src,
                        probe="oracle",
                        reward=None,
                        status="no_reference",
                        elapsed_sec=0.0,
                        memory_mb=mem,
                        test_stdout_tail="",
                        intended="accept",
                        path=str(task_dir),
                    )
                )
                _progress(f"{tid} oracle no_reference memory_mb={mem}")
                continue
            if remaining() <= 0 and not task_started:
                persist(
                    build_trial_row(
                        task_id=tid,
                        source_benchmark=src,
                        probe=probe,
                        reward=None,
                        status="not_run",
                        elapsed_sec=0.0,
                        memory_mb=mem,
                        test_stdout_tail="",
                        path=str(task_dir),
                    )
                )
                if tid not in not_run:
                    not_run.append(tid)
                continue
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            job_name = f"{tid}-{probe}-{stamp}"
            _progress(f"{tid} {probe} memory_mb={mem} -> {job_name}")
            run = run_harbor_capped(
                task_dir,
                "nop" if probe.startswith("nop") else "oracle",
                jobs_dir,
                job_name,
                cap_sec=int(trial_cap_sec),
                build_heavy_sec=int(trial_cap_sec) + 3600,
            )
            task_started = True
            status = run["status"]
            if status == "skipped_heavy":
                status = "timeout"
            stdout_tail = run.get("test_stdout_tail") or ""
            full_stdout = ""
            matches = list(jobs_dir.glob(f"{job_name}/*/verifier/test-stdout.txt"))
            if matches:
                newest = max(matches, key=lambda p: p.stat().st_mtime)
                try:
                    full_stdout = newest.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    full_stdout = stdout_tail
            else:
                full_stdout = stdout_tail
            extracted = extract_failures(full_stdout)
            row = build_trial_row(
                task_id=tid,
                source_benchmark=src,
                probe=probe,
                reward=run["reward"],
                status=status,
                elapsed_sec=run["elapsed_sec"],
                memory_mb=mem,
                test_stdout_tail=tail_lines(full_stdout, STDOUT_TAIL_LINES) if full_stdout else stdout_tail,
                stderr_tail=run.get("stderr_tail") or "",
                job_name=job_name,
                path=str(task_dir),
                failing_tests=extracted["failing_tests"] if extracted["failing_tests"] else None,
                last_error_line=extracted["last_error_line"] or None,
            )
            persist(row)
            _progress(
                f"{tid} {probe} status={row['status']} reward={row['reward']} "
                f"elapsed={row['elapsed_sec']:.1f}s remaining={remaining():.0f}s"
            )
        dump_summary()

    summary = dump_summary()
    public = {k: summary[k] for k in summary if k not in {"by_source", "reference_failures"}}
    public["by_source"] = {k: {"n_tasks": v["n_tasks"], "n_run": v["n_run"], "n_reference_fails": v["n_reference_fails"], "n_nop_passes": v["n_nop_passes"], "n_infra": v["n_infra"], "n_timeout": v["n_timeout"]} for k, v in (summary.get("by_source") or {}).items()}
    public["n_reference_failures_listed"] = len(summary.get("reference_failures") or [])
    print(json.dumps(public, indent=2, default=str), flush=True)
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Harbor-Index 1.0 oracle/nop external control")
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    p.add_argument("--jobs", type=Path, default=DEFAULT_JOBS)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--summary", type=Path, default=None)
    p.add_argument("--tb21-summary", type=Path, default=DEFAULT_TB21)
    p.add_argument("--budget-sec", type=float, default=BUDGET_SEC)
    p.add_argument("--trial-cap-sec", type=int, default=TRIAL_CAP_SEC)
    p.add_argument("--no-resume", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_experiment(
        dataset=args.dataset,
        jobs_dir=args.jobs,
        out_path=args.out,
        summary_path=args.summary,
        budget_sec=args.budget_sec,
        trial_cap_sec=args.trial_cap_sec,
        tb21_path=args.tb21_summary,
        resume=not args.no_resume,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
