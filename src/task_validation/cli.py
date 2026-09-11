"""Command-line entry. Ingest, simulate, build the review queue. Stop before labeling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from task_validation.ingest.harbor_task import ingest_tree, write_jsonl as write_harbor
from task_validation.ingest.swe_verified import load_ensemble_csv, summarize, write_jsonl as write_swe
from task_validation.review.queue import write_manifest
from task_validation.sampling.simulate import (
    simulate_hybrid_discovery,
    simulate_srs,
    simulate_stratified,
)


def _cmd_ingest_swe(args: argparse.Namespace) -> int:
    rows = load_ensemble_csv(Path(args.csv))
    write_swe(rows, Path(args.out))
    print(json.dumps(summarize(rows), indent=2))
    return 0


def _cmd_ingest_harbor(args: argparse.Namespace) -> int:
    rows = ingest_tree(Path(args.root))
    write_harbor(rows, Path(args.out))
    complete = [
        r
        for r in rows
        if (r.evidence.static_checks or {}).get("has_instruction")
        and (r.evidence.static_checks or {}).get("has_solution")
        and (r.evidence.static_checks or {}).get("has_tests")
        and (r.evidence.static_checks or {}).get("has_environment")
    ]
    print(
        json.dumps(
            {
                "n_discovered": len(rows),
                "n_complete_package": len(complete),
                "ids": [r.task_id for r in complete],
            },
            indent=2,
        )
    )
    return 0


def _cmd_simulate(args: argparse.Namespace) -> int:
    population: dict[str, int] = {}
    strata: dict[str, str] = {}
    risks: dict[str, float] = {}
    with Path(args.gold).open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            tid = rec["task_id"]
            population[tid] = 1 if rec.get("human_validity_label") == "invalid" else 0
            sev = rec.get("human_severity") or {}
            # Weak proxy, not the label: FAIL_TO_PASS severity as a risk score.
            # Using the label itself would leak. Severity 0-3 is the annotation
            # feature most analogous to a future mutation/LLM-audit signal.
            risks[tid] = float(sev.get("false_negative") or 0.0) / 3.0
            repo = rec.get("repository") or "unknown"
            strata[tid] = repo
    n = args.n
    reps = args.replicates
    seed = args.seed
    if args.low_prevalence is not None:
        from task_validation.sampling.simulate import subsample_low_prevalence

        population = subsample_low_prevalence(population, args.low_prevalence, seed)
        true_p = sum(population.values()) / len(population)
        # Recompute strata/risks on the subset.
        strata = {i: strata[i] for i in population}
        risks = {i: risks.get(i, 0.0) for i in population}
        _ = true_p
    results = {
        "srs": simulate_srs(population, n, reps, seed),
        "stratified": simulate_stratified(population, strata, n, reps, seed),
        "hybrid": simulate_hybrid_discovery(population, strata, risks, n, reps, seed),
    }
    out = {
        name: {
            "design": r.design,
            "n": r.n,
            "replicates": r.replicates,
            "true_p": r.true_p,
            "mean_p_hat": r.mean_p_hat,
            "mean_ucb": r.mean_ucb,
            "coverage": r.coverage,
            "mean_invalids_found": r.mean_invalids_found,
        }
        for name, r in results.items()
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


def _cmd_build_queue(args: argparse.Namespace) -> int:
    from task_validation.schema import EvidenceVector, GoldRow

    rows: list[GoldRow] = []
    with Path(args.gold).open(encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            ev = d.pop("evidence", {}) or {}
            extra = ev.pop("extra", {}) or {}
            known = {k: ev[k] for k in EvidenceVector.__dataclass_fields__ if k in ev}
            evidence = EvidenceVector(**known)
            evidence.extra.update(extra)
            rows.append(GoldRow(**d, evidence=evidence))
    if args.complete_only:
        rows = [
            r
            for r in rows
            if (r.evidence.static_checks or {}).get("has_instruction")
            and (r.evidence.static_checks or {}).get("has_solution")
            and (r.evidence.static_checks or {}).get("has_tests")
            and (r.evidence.static_checks or {}).get("has_environment")
        ]
    skip = {s.strip() for s in (args.skip or "").split(",") if s.strip()}
    rows = [
        r
        for r in rows
        if r.task_id not in skip
        and Path(r.task_id).name not in skip
        and not any(r.task_id == s or r.task_id.startswith(s.rstrip("/") + "/") for s in skip)
    ]
    out = Path(args.out)
    write_manifest(rows, None, out)
    print(json.dumps({"n_packets": len(rows), "out": str(out)}, indent=2))
    return 0


def _cmd_join_swe(args: argparse.Namespace) -> int:
    from task_validation.ingest.swe_join import join_parquet

    report = join_parquet(Path(args.gold), Path(args.parquet), Path(args.out))
    print(json.dumps(report, indent=2))
    return 0 if report["n_matched"] else 1


def _cmd_fit_risk(args: argparse.Namespace) -> int:
    from task_validation.model.fit import fit_and_eval, load_feature_table

    rows = load_feature_table(Path(args.features))
    report = fit_and_eval(rows, seed=args.seed)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def _cmd_attach_harbor(args: argparse.Namespace) -> int:
    from task_validation.evidence.harbor_jobs import collect_job_outcomes
    from task_validation.evidence.harbor_static import harbor_cheap_features
    from task_validation.evidence.mutation import harbor_file_mutants

    gold_path = Path(args.gold)
    tasks_root = Path(args.tasks_root)
    jobs = collect_job_outcomes(Path(args.jobs_root)) if args.jobs_root else {}
    n = 0
    n_oracle = 0
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with gold_path.open(encoding="utf-8") as fh, out_path.open("w", encoding="utf-8") as out:
        for line in fh:
            rec = json.loads(line)
            rel = rec.get("artifacts", {}).get("relpath") or rec["task_id"]
            task_dir = tasks_root / rel
            slug = Path(rel).name
            if task_dir.is_dir():
                rec.setdefault("evidence", {})
                rec["evidence"]["static_checks"] = {
                    **(rec["evidence"].get("static_checks") or {}),
                    **{k: v for k, v in harbor_cheap_features(task_dir).items()},
                }
                mutants = harbor_file_mutants(task_dir)
                rec["evidence"]["mutation_score"] = None
                rec["evidence"].setdefault("extra", {})
                rec["evidence"]["extra"]["n_file_mutants"] = len(mutants)
            outcome = jobs.get(slug) or {}
            if "oracle" in outcome:
                rec["evidence"]["oracle_pass"] = outcome["oracle"] == 1.0
                n_oracle += 1
            if "nop" in outcome:
                rec["evidence"]["nop_fail"] = outcome["nop"] == 0.0
            if "cheat" in outcome:
                rec["evidence"]["exploit_probe_rejected"] = outcome["cheat"] == 0.0
            out.write(json.dumps(rec) + "\n")
            n += 1
    print(json.dumps({"n": n, "n_with_oracle_job": n_oracle, "n_job_slugs": len(jobs), "out": str(out_path)}, indent=2))
    return 0


def _cmd_rater_targets(args: argparse.Namespace) -> int:
    from task_validation.ingest.swe_raters import build_targets

    summary = build_targets(Path(args.csv), Path(args.out))
    meta = Path(args.out).with_suffix(".summary.json")
    meta.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


def _cmd_oof_eval(args: argparse.Namespace) -> int:
    from task_validation.model.fit import load_feature_table
    from task_validation.model.oof import grouped_oof, write_oof

    rows = load_feature_table(Path(args.features))
    if args.targets:
        by = {}
        with Path(args.targets).open(encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                by[rec["task_id"]] = rec
        y_key = args.y_key
        merged = []
        for r in rows:
            t = by.get(r["task_id"])
            if t is None:
                continue
            r = dict(r)
            r["y"] = t[y_key]
            r["openai_2024_conservative"] = t["openai_2024_conservative"]
            r["majority_invalid"] = t["majority_invalid"]
            r["unanimous_invalid"] = t["unanimous_invalid"]
            merged.append(r)
        rows = merged
    report = grouped_oof(rows, y_key="y")
    write_oof(report, Path(args.out))
    slim = {k: v for k, v in report.items() if k != "oof"}
    print(json.dumps(slim, indent=2)[:8000])
    return 0


def _cmd_run_harbor_evidence(args: argparse.Namespace) -> int:
    from task_validation.evidence.runner import run_static_execution_mutation

    task_dir = Path(args.task)
    work = Path(args.work)
    report = run_static_execution_mutation(
        task_dir,
        work,
        timeout=args.timeout,
        n_oracle=args.n_oracle,
        run_mutants=not args.skip_mutants,
        max_mutants=args.max_mutants,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k not in {"static", "oracle", "nop", "checks"}}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="task-validation")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest-swe", help="Load OpenAI SWE-bench Verified ensemble CSV")
    p.add_argument("--csv", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_ingest_swe)

    p = sub.add_parser("ingest-harbor", help="Walk a Harbor task tree")
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_ingest_harbor)

    p = sub.add_parser("simulate-coverage", help="UCB coverage on labeled gold")
    p.add_argument("--gold", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--replicates", type=int, default=200)
    p.add_argument("--seed", default="evalqa-gold-v0")
    p.add_argument("--low-prevalence", type=float, default=None)
    p.set_defaults(func=_cmd_simulate)

    p = sub.add_parser("build-queue", help="Write human-review packets and stop")
    p.add_argument("--gold", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--complete-only", action="store_true")
    p.add_argument("--skip", default="tasks/hello-world,hello-world")
    p.set_defaults(func=_cmd_build_queue)

    p = sub.add_parser("join-swe", help="Join SWE-bench parquet artifacts onto 2024 labels")
    p.add_argument("--gold", required=True)
    p.add_argument("--parquet", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_join_swe)

    p = sub.add_parser("fit-risk", help="Train logistic + HGB on cheap features only")
    p.add_argument("--features", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", default="evalqa-risk-v0")
    p.set_defaults(func=_cmd_fit_risk)

    p = sub.add_parser("attach-harbor", help="Attach jobs + static + mutant menu to Harbor gold")
    p.add_argument("--gold", required=True)
    p.add_argument("--tasks-root", required=True)
    p.add_argument("--jobs-root", default="")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_attach_harbor)

    p = sub.add_parser("rater-targets", help="Build conservative/majority/unanimous labels + IAA")
    p.add_argument("--csv", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_rater_targets)

    p = sub.add_parser("oof-eval", help="Grouped-CV OOF, retain curves, SRC, calibration")
    p.add_argument("--features", required=True)
    p.add_argument("--targets", default="")
    p.add_argument("--y-key", default="openai_2024_conservative")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_oof_eval)

    p = sub.add_parser("run-harbor-evidence", help="Oracle/nop/determinism/mutants via Harbor")
    p.add_argument("--task", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--n-oracle", type=int, default=2)
    p.add_argument("--max-mutants", type=int, default=4)
    p.add_argument("--skip-mutants", action="store_true")
    p.set_defaults(func=_cmd_run_harbor_evidence)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
