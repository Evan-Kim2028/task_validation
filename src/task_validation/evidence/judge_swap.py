"""Judge-swap experiment on the Harbor-Index judge stratum (doc 51).

Runs the official verifier of each judge-configured task unchanged, but
points its OpenAI SDK path at the devin-backed judge shim (judge_shim.py):
JUDGE_MODELS=devin-swe2max routes to the openai provider in
native_judge.judge_provider_for_model, OPENAI_API_KEY is a dummy, and
OPENAI_BASE_URL is http://172.17.0.1:<port>/v1 so verifier containers reach
the host-bound shim.

This measures rubric robustness to a judge change: same rubric, same inputs,
different judge model. It does NOT measure the shipped verifier's verdicts.
Rows carry verifier_kind=judge_swap and never pool with execution-verified or
shipped-judge evidence; certificate.py raises if a judge_swap verdict is
presented for certification.

Per run recorded: reward, sha256 of the verifier's judgment JSON (the judge
verdict text hash), shim request count over the trial window, and wall time.
k=3 on the oracle output and k=3 on the nop output, each in a fresh
container via `harbor run`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from task_validation.evidence.harbor_index_control import (
    catalog_task,
    discover_index_tasks,
    order_catalog,
    summary_path_for,
)
from task_validation.evidence.judge_shim import (
    DEFAULT_DEVIN_MODEL,
    DEFAULT_HOST_ADDR,
    DEFAULT_LOG as DEFAULT_SHIM_LOG,
    DEFAULT_PORT,
    DEFAULT_SCRATCH,
    ShimConfig,
    count_shim_requests,
    serve_in_thread,
)
from task_validation.evidence.judge_verifier import (
    DEFAULT_DATASET,
    detect_judge,
    judge_subruns,
    read_judge_details,
    run_harbor_judge,
)
from task_validation.evidence.tb21_pairs import (
    STDOUT_TAIL_LINES,
    append_jsonl,
    load_existing_rows,
    tail_lines,
    write_json,
)

SWAP_PROTOCOL = "verifier_judge_swap.devin_swe2max.fresh_environment.execution"
SWAP_VERIFIER_KIND = "judge_swap"
SWAP_JUDGE_MODEL = "devin-swe2max"  # no claude/gemini/deepseek -> openai path
SWAP_GRADE = "B"
SWAP_DUMMY_KEY = "sk-judge-shim"
SWAP_JUDGE_REPEATS = "1"
SWAP_JUDGE_CONCURRENCY = "1"

DEFAULT_OUT = Path("data/gold/harbor_index_judge_swap.jsonl")
DEFAULT_JOBS = Path("/tmp/tv-hindex/judge-swap-jobs")
DEFAULT_STRATA = Path("data/gold/harbor_index_strata.json")
BUDGET_SEC = 48 * 60 * 60
TRIAL_CAP_SEC = 2 * 60 * 60
VERIFIER_TIMEOUT_MULT = 6.0

_DETERMINISTIC_MATCH_PREFIXES = (
    "Canonical tool names differ",
    "Exact normalized argument match",
    "Unresolved ENV placeholder args",
    "Missing required agent args",
)
_LLM_DETAIL_KEYS = {
    "reasoning",
    "judge_reason",
    "model_answer",
    "extracted_final_answer",
}


def swap_verifier_env(base_url: str) -> dict[str, str]:
    """The only env the swap run injects; everything else stays stock."""
    return {
        "JUDGE_MODELS": SWAP_JUDGE_MODEL,
        "JUDGE_REPEATS": SWAP_JUDGE_REPEATS,
        "JUDGE_CONCURRENCY": SWAP_JUDGE_CONCURRENCY,
        "OPENAI_API_KEY": SWAP_DUMMY_KEY,
        "OPENAI_BASE_URL": base_url,
    }


def judge_task_ids(dataset: Path, strata_path: Path | None = DEFAULT_STRATA) -> list[str]:
    """The judge stratum from the frozen strata map; detection as fallback."""
    if strata_path is not None and Path(strata_path).is_file():
        strata = json.loads(Path(strata_path).read_text(encoding="utf-8"))
        ids = list((strata.get("ids_by_stratum") or {}).get("judge") or [])
        if ids:
            return sorted(ids)
    return sorted(
        p.name
        for p in discover_index_tasks(Path(dataset))
        if detect_judge(p)["is_judge"]
    )


def shim_judge_rows(log_path: Path) -> list[dict]:
    path = Path(log_path)
    if not path.is_file():
        return []
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("endpoint") in ("chat_completions", "responses"):
                rows.append(row)
    return rows


def details_imply_llm_calls(details: dict) -> bool:
    """True when the verifier's own detail JSON proves a model generated text.

    Conservative: only positive markers count. hle/omnimath runs carry
    reasoning/model_answer keys; gaia2 answer mode carries judge_reason;
    gaia2 action mode marks LLM-judged pairs by a reason string outside the
    deterministic set. widesearch F1-only results and short-circuited runs
    correctly return False.
    """
    found = False

    def visit(node: object) -> None:
        nonlocal found
        if found:
            return
        if isinstance(node, dict):
            if _LLM_DETAIL_KEYS.intersection(node):
                found = True
                return
            for pair in node.get("matched_pairs") or []:
                if isinstance(pair, dict):
                    reason = str(pair.get("reason") or "").strip()
                    if reason and not reason.startswith(_DETERMINISTIC_MATCH_PREFIXES):
                        found = True
                        return
            for entry in node.get("unmatched_details") or []:
                text = str(entry)
                _, _, reason = text.partition("rejected: ")
                if reason and not reason.startswith(_DETERMINISTIC_MATCH_PREFIXES):
                    found = True
                    return
            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(details or {})
    return found


def verdict_sha256(details: dict) -> str | None:
    if not details:
        return None
    blob = json.dumps(details, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_swap_row(
    *,
    task_id: str,
    src: str,
    probe: str,
    rep: int,
    reward: float | None,
    status: str,
    elapsed_sec: float,
    details: dict | None,
    shim_rows_new: list[dict],
    shim_rows_before: int,
    memory_mb: int | None,
    test_stdout_tail: str,
    stderr_tail: str = "",
    job_name: str | None = None,
    path: str | None = None,
    base_url: str = "",
    verifier_timeout_mult: float = VERIFIER_TIMEOUT_MULT,
) -> dict:
    judge_runs = judge_subruns(details or {})
    llm_evidence = details_imply_llm_calls(details or {})
    shim_requests = len(shim_rows_new)
    if status == "executed" and llm_evidence and shim_requests == 0:
        status = "shim_bypassed"
    if status not in ("executed", "shim_bypassed"):
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
        "label_protocol": SWAP_PROTOCOL,
        "grade": SWAP_GRADE,
        "verifier_kind": SWAP_VERIFIER_KIND,
        "adjudicator": "machine",
        "judge_model": SWAP_JUDGE_MODEL,
        "judge_models": [SWAP_JUDGE_MODEL],
        "judge_providers": ["openai"],
        "judge_repeats": int(SWAP_JUDGE_REPEATS),
        "judge_runs": judge_runs,
        "detail_files": sorted((details or {}).keys()),
        "verdict_sha256": verdict_sha256(details or {}),
        "judge_llm_evidence": llm_evidence,
        "shim_requests": shim_requests,
        "shim_log_rows_before": shim_rows_before,
        "shim_elapsed_sec": sum(
            float(r.get("elapsed_sec") or 0.0) for r in shim_rows_new
        ),
        "shim_request_errors": sum(
            1 for r in shim_rows_new if r.get("status") != 200
        ),
        "openai_base_url": base_url,
        "verifier_timeout_mult": verifier_timeout_mult,
        "memory_mb": memory_mb,
        "test_stdout_tail": test_stdout_tail,
        "stderr_tail": stderr_tail,
        "job_name": job_name,
        "path": path,
    }
    return row


def run_key(row: dict) -> tuple[str, str, int]:
    return (row["task_id"], row["probe"], int(row.get("rep") or 0))


def drop_infra_rows(out_path: Path, task_ids: list[str]) -> dict:
    """Rewrite out_path without status=infra rows for the named tasks.

    Resume keys on (task_id, probe, rep), so an infra row would otherwise be
    skipped forever; dropping it makes the next resume re-execute the trial.
    Executed and shim_bypassed rows are never touched.
    """
    out_path = Path(out_path)
    rows = load_existing_rows(out_path)
    wanted = set(task_ids)
    kept = [
        r
        for r in rows
        if not (r.get("status") == "infra" and r.get("task_id") in wanted)
    ]
    dropped = len(rows) - len(kept)
    if out_path.is_file() and dropped:
        tmp = out_path.with_name(out_path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for r in kept:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(out_path)
    return {"rows_before": len(rows), "dropped": dropped, "rows_after": len(kept)}


def summarize_swap(
    rows: list[dict], *, wall_clock_total: float, n_judge_tasks: int
) -> dict:
    by_task: dict[str, list[dict]] = {}
    for row in rows:
        by_task.setdefault(row["task_id"], []).append(row)
    tasks: dict[str, dict] = {}
    for tid, trials in sorted(by_task.items()):
        entry: dict[str, object] = {
            "statuses": sorted({str(t.get("status") or "") for t in trials}),
            "verdict_sha256": sorted(
                {str(t["verdict_sha256"]) for t in trials if t.get("verdict_sha256")}
            ),
            "shim_requests_total": sum(int(t.get("shim_requests") or 0) for t in trials),
        }
        for probe, key in (("oracle", "reference"), ("nop", "nop")):
            runs = [t for t in trials if t.get("probe") == probe]
            executed = [
                t for t in runs if t.get("status") in ("executed", "shim_bypassed")
            ]
            entry[key] = {
                "runs": len(runs),
                "executed": len(executed),
                "rewards": [t.get("reward") for t in runs],
                "shim_requests": [t.get("shim_requests") for t in runs],
                "elapsed_sec": [round(float(t.get("elapsed_sec") or 0), 1) for t in runs],
            }
        tasks[tid] = entry
    return {
        "protocol": SWAP_PROTOCOL,
        "grade": SWAP_GRADE,
        "verifier_kind": SWAP_VERIFIER_KIND,
        "judge_model": SWAP_JUDGE_MODEL,
        "n_judge_tasks": n_judge_tasks,
        "n_tasks_with_rows": len(tasks),
        "n_runs": len(rows),
        "n_shim_bypassed": sum(1 for r in rows if r.get("status") == "shim_bypassed"),
        "tasks": tasks,
        "wall_clock_total": float(wall_clock_total),
        "note": (
            "judge-swap rows measure rubric robustness to a judge change "
            "(doc 51). verifier_kind=judge_swap never enters a certificate: "
            "certificate.build_certificate rejects it, and it never pools "
            "with execution-verified or shipped-judge runs."
        ),
    }


def run_swap_experiment(
    *,
    dataset: Path,
    jobs_dir: Path,
    out_path: Path,
    summary_path: Path | None = None,
    strata_path: Path | None = DEFAULT_STRATA,
    shim_config: ShimConfig | None = None,
    k: int = 3,
    budget_sec: float = BUDGET_SEC,
    trial_cap_sec: int = TRIAL_CAP_SEC,
    verifier_timeout_mult: float = VERIFIER_TIMEOUT_MULT,
    task_filter: list[str] | None = None,
    resume: bool = True,
) -> dict:
    dataset = Path(dataset).resolve()
    jobs_dir = Path(jobs_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(out_path)
    if summary_path is None:
        summary_path = summary_path_for(out_path)
    shim_config = shim_config or ShimConfig()
    shim_log = Path(shim_config.log_path)

    wanted = set(task_filter) if task_filter else None
    judge_ids = set(judge_task_ids(dataset, strata_path))
    catalog = []
    for task_dir in discover_index_tasks(dataset):
        if task_dir.name not in judge_ids:
            continue
        meta = catalog_task(task_dir)
        if wanted is not None and meta["task_id"] not in wanted:
            continue
        catalog.append(meta)
    catalog = order_catalog(catalog)

    verifier_env = swap_verifier_env(shim_config.base_url)
    extra_args = ["--verifier-timeout-multiplier", str(verifier_timeout_mult)]

    server, _thread = serve_in_thread(shim_config)
    base_url = shim_config.base_url

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
        summary = summarize_swap(
            rows,
            wall_clock_total=time.monotonic() - t_start,
            n_judge_tasks=len(catalog),
        )
        summary["dataset"] = str(dataset)
        summary["k"] = k
        summary["shim"] = {
            "base_url": base_url,
            "port": shim_config.port,
            "host_addr": shim_config.host_addr,
            "log": str(shim_log),
            "devin_model": shim_config.devin_model,
            "n_requests": count_shim_requests(shim_log),
        }
        summary["verifier_env"] = {
            k_: ("<dummy>" if "KEY" in k_ else v) for k_, v in verifier_env.items()
        }
        write_json(summary_path, summary)
        return summary

    print(
        f"[judge_swap] judge_tasks={len(catalog)} k={k} resume_rows={len(existing)} "
        f"budget_sec={budget_sec} shim={base_url} log={shim_log}",
        flush=True,
    )

    try:
        for meta in catalog:
            tid = meta["task_id"]
            task_dir = Path(meta["path"])
            for probe in ("oracle", "nop"):
                agent = "oracle" if probe == "oracle" else "nop"
                for rep in range(k):
                    if (tid, probe, rep) in done:
                        continue
                    if remaining() <= 0:
                        persist(
                            build_swap_row(
                                task_id=tid,
                                src=meta["source_benchmark"],
                                probe=probe,
                                rep=rep,
                                reward=None,
                                status="not_run",
                                elapsed_sec=0.0,
                                details=None,
                                shim_rows_new=[],
                                shim_rows_before=count_shim_requests(shim_log),
                                memory_mb=meta["memory_mb"],
                                test_stdout_tail="",
                                path=str(task_dir),
                                base_url=base_url,
                                verifier_timeout_mult=verifier_timeout_mult,
                            )
                        )
                        continue
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                    job_name = f"jswap-{tid}-{probe}-{rep}-{stamp}"
                    before_rows = shim_judge_rows(shim_log)
                    print(
                        f"[judge_swap] {tid} {probe} rep={rep} -> {job_name}",
                        flush=True,
                    )
                    run = run_harbor_judge(
                        task_dir,
                        agent,
                        jobs_dir,
                        job_name,
                        verifier_env=verifier_env,
                        cap_sec=int(trial_cap_sec),
                        harbor_extra_args=extra_args,
                    )
                    after_rows = shim_judge_rows(shim_log)
                    new_rows = after_rows[len(before_rows):]
                    details = read_judge_details(jobs_dir, job_name)
                    row = build_swap_row(
                        task_id=tid,
                        src=meta["source_benchmark"],
                        probe=probe,
                        rep=rep,
                        reward=run["reward"],
                        status=run["status"],
                        elapsed_sec=run["elapsed_sec"],
                        details=details,
                        shim_rows_new=new_rows,
                        shim_rows_before=len(before_rows),
                        memory_mb=meta["memory_mb"],
                        test_stdout_tail=tail_lines(
                            run.get("test_stdout_tail") or "", STDOUT_TAIL_LINES
                        ),
                        stderr_tail=run.get("stderr_tail") or "",
                        job_name=job_name,
                        path=str(task_dir),
                        base_url=base_url,
                        verifier_timeout_mult=verifier_timeout_mult,
                    )
                    persist(row)
                    print(
                        f"[judge_swap] {tid} {probe} rep={rep} "
                        f"status={row['status']} reward={row['reward']} "
                        f"shim_requests={row['shim_requests']} "
                        f"elapsed={row['elapsed_sec']:.1f}s "
                        f"remaining={remaining():.0f}s",
                        flush=True,
                    )
                dump_summary()
        summary = dump_summary()
        return summary
    finally:
        server.shutdown()
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    p.add_argument("--jobs", type=Path, default=DEFAULT_JOBS)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--summary", type=Path, default=None)
    p.add_argument("--strata", type=Path, default=DEFAULT_STRATA)
    p.add_argument("--task", default="", help="comma-separated task ids; default all judge tasks")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--budget-sec", type=float, default=BUDGET_SEC)
    p.add_argument("--trial-cap-sec", type=int, default=TRIAL_CAP_SEC)
    p.add_argument("--verifier-timeout-multiplier", type=float, default=VERIFIER_TIMEOUT_MULT)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--host-addr", default=DEFAULT_HOST_ADDR)
    p.add_argument("--shim-log", type=Path, default=DEFAULT_SHIM_LOG)
    p.add_argument("--scratch", type=Path, default=DEFAULT_SCRATCH)
    p.add_argument("--devin-model", default=DEFAULT_DEVIN_MODEL)
    p.add_argument("--devin-timeout-sec", type=float, default=480.0)
    p.add_argument("--list", action="store_true", help="print the swap plan; never runs harbor")
    p.add_argument("--no-resume", action="store_true")
    p.add_argument(
        "--redo-infra",
        action="store_true",
        help="drop status=infra rows for --task ids from --out before running, "
        "so resume re-executes them; executed rows are untouched",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    shim_config = ShimConfig(
        port=args.port,
        host_addr=args.host_addr,
        log_path=args.shim_log,
        scratch_root=args.scratch,
        devin_model=args.devin_model,
        devin_timeout_sec=args.devin_timeout_sec,
    )
    task_filter = [t.strip() for t in args.task.split(",") if t.strip()] or None
    if args.list:
        ids = judge_task_ids(args.dataset, args.strata)
        if task_filter:
            ids = [t for t in ids if t in set(task_filter)]
        report = {
            "n_judge_tasks": len(ids),
            "tasks": ids,
            "k": args.k,
            "trials_planned": len(ids) * 2 * args.k,
            "protocol": SWAP_PROTOCOL,
            "grade": SWAP_GRADE,
            "verifier_kind": SWAP_VERIFIER_KIND,
            "judge_model": SWAP_JUDGE_MODEL,
            "verifier_env": swap_verifier_env(shim_config.base_url),
        }
        print(json.dumps(report, indent=2))
        return 0
    if args.redo_infra:
        if not task_filter:
            parser.error("--redo-infra requires --task")
        report = drop_infra_rows(args.out, task_filter)
        print(
            f"[judge_swap] redo_infra dropped={report['dropped']} "
            f"rows_after={report['rows_after']} out={args.out}",
            flush=True,
        )
    summary = run_swap_experiment(
        dataset=args.dataset,
        jobs_dir=args.jobs,
        out_path=args.out,
        summary_path=args.summary,
        strata_path=args.strata,
        shim_config=shim_config,
        k=args.k,
        budget_sec=args.budget_sec,
        trial_cap_sec=args.trial_cap_sec,
        verifier_timeout_mult=args.verifier_timeout_multiplier,
        task_filter=task_filter,
        resume=not args.no_resume,
    )
    public = {k_: summary[k_] for k_ in summary if k_ != "tasks"}
    public["per_task"] = {
        tid: {"statuses": t["statuses"], "reference": t["reference"], "nop": t["nop"]}
        for tid, t in (summary.get("tasks") or {}).items()
    }
    print(json.dumps(public, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
