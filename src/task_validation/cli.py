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
    p.set_defaults(func=_cmd_simulate)

    p = sub.add_parser("build-queue", help="Write human-review packets and stop")
    p.add_argument("--gold", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--complete-only", action="store_true")
    p.add_argument("--skip", default="tasks/hello-world,hello-world")
    p.set_defaults(func=_cmd_build_queue)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
