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


def _cmd_ingest_pro(args: argparse.Namespace) -> int:
    from task_validation.ingest.swe_pro import ingest_pro

    report = ingest_pro(Path(args.parquet), Path(args.out))
    print(json.dumps(report, indent=2))
    return 0 if report["n"] else 1


def _cmd_reconstruct_pro(args: argparse.Namespace) -> int:
    from task_validation.ingest.external_audits import enrichment, match_prefixes, parse_june_kim_claims
    from task_validation.model.risk_coverage import retain_curve

    rows = []
    with Path(args.pro).open(encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
    prefixes = parse_june_kim_claims(Path(args.claims_md))
    hits = match_prefixes([r["task_id"] for r in rows], prefixes)
    positive = set(hits)
    # Primary milestone ranking: prompt-vs-test (OpenAI's object), not
    # Scale requirements which often restate hidden pins.
    ranked_high = sorted(rows, key=lambda r: -float(r["features"].get("openai_style_risk") or r["features"]["cheap_risk"]))
    ranked_low = sorted(rows, key=lambda r: float(r["features"].get("openai_style_risk") or r["features"]["cheap_risk"]))
    y_kim = [1 if r["task_id"] in positive else 0 for r in rows]
    scores = [float(r["features"].get("openai_style_risk") or r["features"]["cheap_risk"]) for r in rows]
    # retain lowest risk → residual June Kim rate
    retain = retain_curve(y_kim, scores)
    fam = {}
    n_any_flag = 0
    mean_scores = {
        "family_strict": 0.0,
        "family_underspec": 0.0,
        "family_low_coverage": 0.0,
        "family_misleading": 0.0,
        "cheap_risk": 0.0,
    }
    for r in rows:
        fam[r["suspected_family"]] = fam.get(r["suspected_family"], 0) + 1
        if r.get("family_flags"):
            n_any_flag += 1
        for k in mean_scores:
            mean_scores[k] += float(r["features"][k])
    n = max(len(rows), 1)
    mean_scores = {k: v / n for k, v in mean_scores.items()}
    fam_in_kim = {}
    for r in rows:
        if r["task_id"] in positive:
            fam_in_kim[r["suspected_family"]] = fam_in_kim.get(r["suspected_family"], 0) + 1
    openai_ex = [r for r in rows if "77c16d53" in r["task_id"]]
    openai_rank = None
    openai_rank_cheap = None
    if openai_ex:
        order = [r["task_id"] for r in ranked_high]
        openai_rank = order.index(openai_ex[0]["task_id"]) + 1
        order_cheap = [
            r["task_id"]
            for r in sorted(rows, key=lambda r: -float(r["features"]["cheap_risk"]))
        ]
        openai_rank_cheap = order_cheap.index(openai_ex[0]["task_id"]) + 1
    report = {
        "n_pro": len(rows),
        "n_june_kim_prefixes": len(prefixes),
        "n_june_kim_matched": len(positive),
        "june_kim_base_rate": len(positive) / len(rows) if rows else None,
        "n_any_family_flag": n_any_flag,
        "mean_family_scores": mean_scores,
        "suspected_family_counts": fam,
        "june_kim_by_our_family": fam_in_kim,
        "enrichment_high_risk": enrichment([r["task_id"] for r in ranked_high], positive, (0.10, 0.15, 0.20, 0.30)),
        "retain_june_kim_in_low_risk": retain,
        "openai_published_example": {
            "pattern": "77c16d53",
            "matched_ids": [r["task_id"] for r in openai_ex],
            "rank_by_openai_style_risk_desc": openai_rank,
            "rank_by_cheap_risk_desc": openai_rank_cheap,
            "n": len(rows),
            "percentile_from_top": (openai_rank / len(rows)) if openai_rank else None,
            "family": openai_ex[0]["suspected_family"] if openai_ex else None,
            "cheap_risk": openai_ex[0]["features"].get("cheap_risk") if openai_ex else None,
            "openai_style_risk": openai_ex[0]["features"].get("openai_style_risk") if openai_ex else None,
            "prompt_missing_lit_frac": openai_ex[0]["features"].get("prompt_missing_lit_frac") if openai_ex else None,
            "requirements_defers_to_tests": openai_ex[0]["features"].get("requirements_defers_to_tests") if openai_ex else None,
            "note": "OpenAI TOC example. Rank is by openai_style_risk (prompt vs tests).",
        },
        "prompt_vs_test_flags": {
            "n_prompt_missing_lit_frac_ge_0.3": sum(
                1 for r in rows if float(r["features"].get("prompt_missing_lit_frac") or 0) >= 0.3
            ),
            "n_requirements_defers_to_tests": sum(
                1 for r in rows if float(r["features"].get("requirements_defers_to_tests") or 0) >= 1.0
            ),
        },
        "constraints": {
            "used_audit_labels_as_predictors": False,
            "optimized_to_30pct": False,
            "executed_docker": False,
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def _cmd_ablate_vev(args: argparse.Namespace) -> int:
    from task_validation.model.ablate_vev import ablate

    report = ablate(
        features_path=Path(args.features),
        oof_path=Path(args.oof),
        parquet_path=Path(args.parquet),
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def _cmd_vev_harbor(args: argparse.Namespace) -> int:
    from task_validation.evidence.harbor_vev import fill_execution
    from task_validation.evidence.spec_atoms import spec_from_record
    from task_validation.evidence.vev import ValidityEvidenceVector, vev_from_spec

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    instruction = Path(args.instruction).read_text(encoding="utf-8") if args.instruction else ""
    tests = Path(args.tests).read_text(encoding="utf-8") if args.tests else ""
    spec = spec_from_record(
        {
            "problem_statement": instruction,
            "test_patch": tests,
            "FAIL_TO_PASS": "[]",
        }
    )
    vev = vev_from_spec(report.get("task_id") or "harbor", spec)
    fill_execution(vev, report)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(vev.to_dict(), indent=2) + "\n", encoding="utf-8")
    print(json.dumps(vev.to_dict(), indent=2))
    return 0


def _cmd_ablate_causal(args: argparse.Namespace) -> int:
    from task_validation.model.ablate_causal import ablate_causal

    report = ablate_causal(Path(args.parquet), Path(args.oof), n=args.n)
    slim = {k: v for k, v in report.items() if k != "profiles"}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report) + "\n", encoding="utf-8")
    Path(str(args.out).replace(".json", ".summary.json")).write_text(
        json.dumps(slim, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(slim, indent=2))
    return 0


def _cmd_interrogate_verifier(args: argparse.Namespace) -> int:
    from task_validation.evidence.interrogate import (
        append_jsonl,
        complete_packages,
        interrogate_verifier,
        load_done_ids,
        matrix_row,
        summarize_records,
    )

    if args.tasks_root:
        root = Path(args.tasks_root).resolve()
        skip = {s.strip() for s in (args.exclude or "").split(",") if s.strip()}
        tasks = []
        for d in complete_packages(root):
            rel = str(d.relative_to(root)).replace("\\", "/")
            if rel in skip or d.name in skip:
                continue
            tasks.append(d)
        if args.limit:
            tasks = tasks[: args.limit]
        out = Path(args.out)
        work = Path(args.work)
        done = load_done_ids(out) if args.resume else set()
        rows: list[dict] = []
        if args.resume and out.is_file():
            with out.open(encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh if line.strip()]
        elif out.is_file() and not args.resume:
            out.unlink()
        for d in tasks:
            rel = str(d.relative_to(root)).replace("\\", "/")
            if rel in done:
                continue
            rec = interrogate_verifier(d, work, timeout=args.timeout, source_root=root)
            append_jsonl(out, rec)
            rows.append(rec)
            print(
                json.dumps(
                    {
                        "task_id": rec["task_id"],
                        "interrogable": rec["rates"]["interrogable"],
                        "elapsed_sec_total": rec["elapsed_sec_total"],
                        "rates": {
                            k: rec["rates"][k]
                            for k in (
                                "correct_accept",
                                "variant_accept",
                                "incorrect_reject",
                                "false_accept",
                                "false_reject",
                            )
                        },
                    }
                ),
                flush=True,
            )
        summary = summarize_records(rows)
        summary_path = out.with_name(out.stem + ".summary.json")
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        matrix_path = out.with_name(out.stem + ".matrix.jsonl")
        with matrix_path.open("w", encoding="utf-8") as fh:
            for rec in rows:
                fh.write(json.dumps(matrix_row(rec)) + "\n")
        print(json.dumps(summary, indent=2))
        return 0

    if not args.task:
        print("interrogate-verifier requires --task or --tasks-root", file=sys.stderr)
        return 2
    report = interrogate_verifier(Path(args.task), Path(args.work), timeout=args.timeout)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    slim = {
        "task_id": report["task_id"],
        "kind": report["kind"],
        "executed": report["executed"],
        "metadata_inferred": report["metadata_inferred"],
        "coverage": report.get("coverage"),
        "rates": report["rates"],
        "trials": [
            {
                "probe_id": t["probe_id"],
                "family": t["family"],
                "intended": t["intended"],
                "availability": t.get("availability"),
                "reward": t["reward"],
                "accepted": t["accepted"],
                "elapsed_sec": t["elapsed_sec"],
            }
            for t in report["trials"]
        ],
    }
    print(json.dumps(slim, indent=2))
    return 0 if report["rates"]["interrogable"] else 1


def _cmd_interrogate_judge(args: argparse.Namespace) -> int:
    from task_validation.evidence.judge_verifier import main as judge_main

    argv = [
        "--dataset", args.dataset,
        "--jobs", args.jobs,
        "--out", args.out,
        "--control", args.control,
        "--k", str(args.k),
        "--budget-sec", str(args.budget_sec),
        "--trial-cap-sec", str(args.trial_cap_sec),
    ]
    if args.summary:
        argv += ["--summary", args.summary]
    if args.strata_out:
        argv += ["--strata-out", args.strata_out]
    if args.task:
        argv += ["--task", args.task]
    if args.list:
        argv += ["--list"]
    if args.no_resume:
        argv += ["--no-resume"]
    return judge_main(argv)


def _cmd_judge_swap(args: argparse.Namespace) -> int:
    from task_validation.evidence.judge_swap import main as swap_main

    argv = [
        "--dataset", args.dataset,
        "--jobs", args.jobs,
        "--out", args.out,
        "--strata", args.strata,
        "--k", str(args.k),
        "--budget-sec", str(args.budget_sec),
        "--trial-cap-sec", str(args.trial_cap_sec),
        "--verifier-timeout-multiplier", str(args.verifier_timeout_multiplier),
        "--port", str(args.port),
        "--host-addr", args.host_addr,
        "--shim-log", args.shim_log,
        "--devin-model", args.devin_model,
        "--devin-timeout-sec", str(args.devin_timeout_sec),
    ]
    if args.summary:
        argv += ["--summary", args.summary]
    if args.task:
        argv += ["--task", args.task]
    if args.list:
        argv += ["--list"]
    if args.no_resume:
        argv += ["--no-resume"]
    return swap_main(argv)


def _cmd_link_human_labels(args: argparse.Namespace) -> int:
    from task_validation.ingest.human_labels import write_linkage

    summary = write_linkage(
        swe_targets=Path(args.swe_targets),
        harbor_gold=Path(args.harbor_gold) if args.harbor_gold else None,
        out=Path(args.out),
    )
    print(json.dumps(summary, indent=2))
    return 0


def _cmd_analyze_treatments(args: argparse.Namespace) -> int:
    from task_validation.evidence.treatment_grade import analyze_pilot

    rows = []
    with Path(args.records).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    report = analyze_pilot(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report) + "\n", encoding="utf-8")
    slim = {k: v for k, v in report.items() if k != "tasks"}
    Path(args.out).with_name(Path(args.out).stem + ".summary.json").write_text(
        json.dumps(slim, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(slim, indent=2))
    return 0


def _cmd_sample_swe_2x2(args: argparse.Namespace) -> int:
    from task_validation.model.sample_2x2 import sample_2x2

    report = sample_2x2(Path(args.oof), n_per_cell=args.n_per_cell, salt=args.salt)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cells"}, indent=2))
    return 0


def _cmd_ingest_tb_maintenance(args: argparse.Namespace) -> int:
    from task_validation.ingest.tb_maintenance import write_jsonl

    summary = write_jsonl(Path(args.out))
    print(json.dumps(summary, indent=2))
    return 0


def _cmd_rater_noise(args: argparse.Namespace) -> int:
    from task_validation.ingest.rater_noise import rater_noise

    report = rater_noise(Path(args.targets))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2)[:8000])
    return 0


def _cmd_validity_corpus(args: argparse.Namespace) -> int:
    from task_validation.ingest.corpus import write_catalog

    root = Path(args.root).resolve()
    report = write_catalog(root, Path(args.out))
    print(json.dumps(report, indent=2)[:8000])
    return 0


def _cmd_harbor_funnel_fetch(args: argparse.Namespace) -> int:
    from task_validation.ingest.harbor_adapter import run_fetch

    report = run_fetch(
        manifest_path=Path(args.manifest),
        adapters_path=Path(args.adapters),
        index_path=Path(args.index),
        out_path=Path(args.out),
        work_dir=Path(args.work),
        budget_bytes=int(args.budget_gb * 1024**3),
        dry_run=args.dry_run,
    )
    print(json.dumps(report, indent=2))
    return 0


def _cmd_harbor_extract_local(args: argparse.Namespace) -> int:
    from task_validation.ingest.harbor_adapter_local import run_extract_local

    report = run_extract_local(
        dump_dir=Path(args.dump_dir),
        manifest_path=Path(args.manifest),
        adapters_path=Path(args.adapters),
        out_dir=Path(args.out),
        workers=args.workers,
    )
    print(json.dumps(report, indent=2))
    return 0


def _cmd_ppi_lab(args: argparse.Namespace) -> int:
    from task_validation.sampling.ppi import format_key_tables, run_ppi_lab, write_ppi_lab

    report = run_ppi_lab(
        Path(args.gold),
        Path(args.targets),
        Path(args.oof),
        replicates=args.replicates,
        seed=args.seed,
    )
    write_ppi_lab(report, Path(args.out))
    tables = format_key_tables(report)
    print(tables)
    return 0


def _cmd_coverage_lab(args: argparse.Namespace) -> int:
    from task_validation.sampling.coverage_lab import run_lab

    report = run_lab(
        Path(args.gold),
        Path(args.oof) if args.oof else None,
        n=args.n,
        replicates=args.replicates,
        seed=args.seed,
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report) + "\n", encoding="utf-8")
    slim = {k: v for k, v in report.items() if k != "rows"}
    slim["n_rows"] = len(report["rows"])
    Path(args.out).with_name(Path(args.out).stem + ".summary.json").write_text(
        json.dumps({"meta": slim, "rows": report["rows"], "sequential": report["sequential"]}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(slim, indent=2))
    return 0


def _cmd_build_decontam_index(args: argparse.Namespace) -> int:
    from task_validation.evidence.decontam import build_index

    pops = tuple(s.strip() for s in args.populations.split(",") if s.strip())
    report = build_index(
        Path(args.out_dir),
        tb4_root=Path(args.tb4_root),
        harbor_index_root=Path(args.harbor_index_root),
        tb21_root=Path(args.tb21_root),
        swe_parquet=Path(args.swe_parquet),
        swe_ids=Path(args.swe_ids),
        swe_verified500=Path(args.swe_verified500) if args.swe_verified500 else None,
        populations=pops,
        ngram_n=args.ngram_n,
        shingle=args.shingle,
    )
    print(json.dumps(report, indent=2))
    return 0


def _cmd_decontam_check(args: argparse.Namespace) -> int:
    from task_validation.evidence.decontam import check_path

    report = check_path(
        Path(args.task),
        Path(args.index_dir),
        ngram_n=args.ngram_n,
        shingle=args.shingle,
        jaccard_threshold=args.jaccard,
        min_ngram_hits=args.min_ngram_hits,
        scaffold_df=args.scaffold_df,
    )
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix == ".jsonl":
            with out.open("w", encoding="utf-8") as fh:
                for row in report["results"]:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    slim = {
        "index_dir": report["index_dir"],
        "populations": report["populations"],
        "n_candidates": report["n_candidates"],
        "n_flagged": report["n_flagged"],
        "results": [
            {
                "task_id": r["task_id"],
                "flagged": r["flagged"],
                "flag_reasons": r["flag_reasons"],
                "populations": {
                    pop: {
                        "max_jaccard": pr["max_jaccard"],
                        "nearest_task_id": pr["nearest_task_id"],
                        "max_ngram_hits": pr["max_ngram_hits"],
                        "ngram_nearest_task_id": pr["ngram_nearest_task_id"],
                    }
                    for pop, pr in r["populations"].items()
                },
            }
            for r in report["results"]
        ],
    }
    print(json.dumps(slim, indent=2))
    return 1 if report["n_flagged"] else 0


def _cmd_generator_gate_sample(args: argparse.Namespace) -> int:
    from task_validation.evidence import generator_gate as gg

    root = Path(args.root)
    name = args.name
    seed = args.seed or gg.default_seed(name)
    out = Path(args.out) if args.out else gg.default_manifest_path(name)
    extract = (
        Path(args.extract_dir) if args.extract_dir else gg.default_extract_dir(root, name)
    )
    manifest = gg.sample_generator(
        name=name,
        root=root,
        n=args.n,
        seed=seed,
        out_path=out,
        extract_dir=extract,
    )
    print(
        json.dumps(
            {
                "manifest": str(out),
                "generator": name,
                "N": manifest["N"],
                "n": manifest["n"],
                "seed": manifest["seed"],
                "extract_dir": manifest["extract_dir"],
            },
            indent=2,
        )
    )
    return 0


def _cmd_generator_gate_run(args: argparse.Namespace) -> int:
    from task_validation.evidence import generator_gate as gg

    name = args.name
    gg.run_gate(
        manifest_path=Path(args.manifest) if args.manifest else gg.default_manifest_path(name),
        out_path=Path(args.out) if args.out else gg.default_out_path(name),
        jobs_dir=Path(args.jobs) if args.jobs else gg.default_jobs_dir(name),
        extract_dir=Path(args.extract_dir) if args.extract_dir else None,
        concurrency=args.concurrency,
        k=args.k,
        probes=args.probes,
        budget_sec=args.budget_sec,
        trial_cap_sec=args.trial_cap_sec,
        timeout_mult=args.timeout_multiplier,
        verifier_mult=args.verifier_timeout_multiplier,
        build_mult=args.build_timeout_multiplier,
        prune_every=args.prune_every,
        epsilon=args.epsilon,
        resume=not args.no_resume,
        redo_infra=args.redo_infra,
        warmup=not args.no_warmup,
    )
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

    p = sub.add_parser("ingest-pro", help="Ingest SWE-Bench Pro public 731 + family features")
    p.add_argument("--parquet", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_ingest_pro)

    p = sub.add_parser("reconstruct-pro", help="Score Pro and compare to June Kim IDs (eval only)")
    p.add_argument("--pro", required=True)
    p.add_argument("--claims-md", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_reconstruct_pro)

    p = sub.add_parser("ablate-vev", help="Untrained spec-gap vs OOF logistic retain-tail")
    p.add_argument("--features", required=True)
    p.add_argument("--oof", required=True)
    p.add_argument("--parquet", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_ablate_vev)

    p = sub.add_parser("vev-from-harbor", help="Build a VEV from a Harbor evidence JSON")
    p.add_argument("--report", required=True)
    p.add_argument("--instruction", default="")
    p.add_argument("--tests", default="")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_vev_harbor)

    p = sub.add_parser("ablate-causal", help="Change causality / provenance / discrimination vs proxy")
    p.add_argument("--parquet", required=True)
    p.add_argument("--oof", required=True)
    p.add_argument("--n", type=int, default=150)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_ablate_causal)

    p = sub.add_parser(
        "interrogate-verifier",
        help="Run controlled implementations through the official Harbor verifier",
    )
    p.add_argument("--task", default="")
    p.add_argument("--tasks-root", default="")
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--exclude", default="experimental/lakehouse-stack-incident,lakehouse-stack-incident")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--resume", action="store_true")
    p.set_defaults(func=_cmd_interrogate_verifier)

    p = sub.add_parser(
        "interrogate-judge",
        help="k=3 oracle + k=3 nop judge-verifier runs per Harbor-Index judge task (doc 44)",
    )
    p.add_argument("--dataset", default="/home/evan/Documents/harbor-index-dataset/harbor-index-1.0")
    p.add_argument("--jobs", default="/tmp/tv-hindex/judge-jobs")
    p.add_argument("--out", default="data/gold/harbor_index_judge.jsonl")
    p.add_argument("--summary", default="")
    p.add_argument("--control", default="data/gold/harbor_index_control.jsonl")
    p.add_argument("--strata-out", default="", dest="strata_out")
    p.add_argument("--task", default="", help="comma-separated task ids; default all judge tasks")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--budget-sec", type=float, default=4 * 60 * 60)
    p.add_argument("--trial-cap-sec", type=int, default=30 * 60)
    p.add_argument("--list", action="store_true", help="enumerate judge tasks and audit env; never runs harbor")
    p.add_argument("--no-resume", action="store_true")
    p.set_defaults(func=_cmd_interrogate_judge)

    p = sub.add_parser(
        "judge-swap",
        help="k=3 oracle + k=3 nop judge-swap runs on the 16 judge tasks (doc 51)",
    )
    p.add_argument("--dataset", default="/home/evan/Documents/harbor-index-dataset/harbor-index-1.0")
    p.add_argument("--jobs", default="/tmp/tv-hindex/judge-swap-jobs")
    p.add_argument("--out", default="data/gold/harbor_index_judge_swap.jsonl")
    p.add_argument("--summary", default="")
    p.add_argument("--strata", default="data/gold/harbor_index_strata.json")
    p.add_argument("--task", default="", help="comma-separated task ids; default all judge tasks")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--budget-sec", type=float, default=48 * 60 * 60)
    p.add_argument("--trial-cap-sec", type=int, default=2 * 60 * 60)
    p.add_argument("--verifier-timeout-multiplier", type=float, default=6.0)
    p.add_argument("--port", type=int, default=8477)
    p.add_argument("--host-addr", default="172.17.0.1")
    p.add_argument("--shim-log", default="data/gold/judge_shim_log.jsonl")
    p.add_argument("--devin-model", default="swe-2-max")
    p.add_argument("--devin-timeout-sec", type=float, default=480.0)
    p.add_argument("--list", action="store_true", help="print the swap plan; never runs harbor")
    p.add_argument("--no-resume", action="store_true")
    p.set_defaults(func=_cmd_judge_swap)

    p = sub.add_parser(
        "link-human-labels",
        help="Mine existing public labels; do not merge provenances",
    )
    p.add_argument("--swe-targets", required=True)
    p.add_argument("--harbor-gold", default="")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_link_human_labels)

    p = sub.add_parser("analyze-treatments", help="Grade interrogation treatments A/B/C/D")
    p.add_argument("--records", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_analyze_treatments)

    p = sub.add_parser("sample-swe-2x2", help="List a 20-task 2x2 SWE sample; do not run Docker")
    p.add_argument("--oof", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--n-per-cell", type=int, default=5)
    p.add_argument("--salt", default="swe-2x2-v0")
    p.set_defaults(func=_cmd_sample_swe_2x2)

    p = sub.add_parser("ingest-tb-maintenance", help="Public TB 2.1 changed-task list")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_ingest_tb_maintenance)

    p = sub.add_parser("rater-noise", help="Single-rater vs 3-rater consensus error")
    p.add_argument("--targets", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_rater_noise)

    p = sub.add_parser("validity-corpus", help="Index gold sources; do not merge Y")
    p.add_argument("--root", default=".")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_validity_corpus)

    p = sub.add_parser("coverage-lab", help="Estimator coverage grid; stratified-normal is not release")
    p.add_argument("--gold", required=True)
    p.add_argument("--oof", default="")
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--replicates", type=int, default=500)
    p.add_argument("--seed", default="coverage-lab-v0")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_coverage_lab)

    p = sub.add_parser(
        "harbor-funnel-fetch",
        help="Fetch stage-1 frontier-cell rewards from Harbor-Adapter shards",
    )
    p.add_argument("--manifest", default="data/raw/harbor-adapter/harbor_adapters.manifest.parquet")
    p.add_argument("--adapters", default="data/raw/harbor-adapter/adapters54.json")
    p.add_argument("--index", default="data/raw/harbor-adapter/trial_shards.jsonl")
    p.add_argument("--out", default="data/gold/harbor_funnel_rewards.jsonl")
    p.add_argument("--work", default="data/raw/harbor-adapter/shards")
    p.add_argument("--budget-gb", type=float, default=40.0)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=_cmd_harbor_funnel_fetch)

    p = sub.add_parser(
        "harbor-extract-local",
        help="Extract every trial row from a local Harbor-Adapter dump",
    )
    p.add_argument("--dump-dir", required=True, help="local snapshot root (data/harbor_adapters/...)")
    p.add_argument("--manifest", default="data/raw/harbor-adapter/harbor_adapters.manifest.parquet")
    p.add_argument("--adapters", default="data/raw/harbor-adapter/adapters54.json")
    p.add_argument("--out", "--out-dir", dest="out", default="data/gold/harbor_adapter_local")
    p.add_argument("--workers", type=int, default=4, help="one shard in memory per worker")
    p.set_defaults(func=_cmd_harbor_extract_local)

    p = sub.add_parser(
        "ppi-lab",
        help="PPI++ / difference / poststrat vs SRS-CP label-savings coverage lab",
    )
    p.add_argument("--gold", default="data/gold/swe_verified_compact.jsonl")
    p.add_argument("--targets", default="data/gold/swe_rater_targets.jsonl")
    p.add_argument("--oof", default="data/gold/oof_openai_2024_conservative.oof.jsonl")
    p.add_argument("--replicates", type=int, default=2000)
    p.add_argument("--seed", default="ppi-lab-v0")
    p.add_argument("--out", default="data/gold/ppi_lab.json")
    p.set_defaults(func=_cmd_ppi_lab)

    p = sub.add_parser(
        "build-decontam-index",
        help="Index TB4, Harbor-Index, TB 2.1, SWE-Verified token shingles",
    )
    p.add_argument("--out-dir", default="data/gold/decontam_index")
    p.add_argument("--tb4-root", default="/home/evan/Documents/eval_tasks/research/tb-ref/tasks")
    p.add_argument(
        "--harbor-index-root",
        default="/home/evan/Documents/harbor-index-dataset/harbor-index-1.0",
    )
    p.add_argument(
        "--tb21-root",
        default=str(Path.home() / "Documents/tb21-dataset/terminal-bench-2-1"),
    )
    p.add_argument("--swe-parquet", default="data/raw/swe-bench/test.parquet")
    p.add_argument("--swe-ids", default="data/gold/swe_verified_compact.jsonl")
    p.add_argument(
        "--swe-verified500",
        default="data/raw/aba/swe_bench_verified/benchmark.json",
        help="Released Verified-500 task list; intersected with --swe-ids. "
        "Empty string indexes every id in --swe-ids.",
    )
    p.add_argument(
        "--populations",
        default="tb4,harbor_index,tb21,swe_verified",
    )
    p.add_argument("--ngram-n", type=int, default=13)
    p.add_argument("--shingle", type=int, default=5)
    p.set_defaults(func=_cmd_build_decontam_index)

    p = sub.add_parser(
        "decontam-check",
        help="Flag a candidate task sharing a 13-gram or shingle Jaccard >= threshold",
    )
    p.add_argument(
        "--task",
        required=True,
        help="Harbor task directory, or a .json/.jsonl of SWE-style records",
    )
    p.add_argument("--index-dir", default="data/gold/decontam_index")
    p.add_argument("--ngram-n", type=int, default=13)
    p.add_argument("--min-ngram-hits", type=int, default=1)
    p.add_argument("--shingle", type=int, default=5)
    p.add_argument("--jaccard", type=float, default=0.5)
    p.add_argument(
        "--scaffold-df",
        type=float,
        default=0.5,
        help="grams in more than this fraction of a population are harness scaffold",
    )
    p.add_argument("--out", default="")
    p.set_defaults(func=_cmd_decontam_check)

    p = sub.add_parser(
        "generator-gate-sample",
        help="Freeze an SRS manifest for one generator's Harbor tasks (doc 50)",
    )
    p.add_argument("--name", required=True, help="generator name, e.g. rst, seta, tmax")
    p.add_argument("--root", required=True, help="local root holding task dirs and/or *.tar files")
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--seed", default="", help="default gen-gate-<name>-v0")
    p.add_argument("--out", default="", help="default data/gold/gen_gate_<name>_manifest.json")
    p.add_argument(
        "--extract-dir",
        default="",
        help="where sampled tar members land; default <root>-gate-extract/<name>",
    )
    p.set_defaults(func=_cmd_generator_gate_sample)

    p = sub.add_parser(
        "generator-gate-run",
        help="Oracle/nop execution gate over the frozen manifest (doc 50 gate A)",
    )
    p.add_argument("--name", required=True)
    p.add_argument("--manifest", default="", help="default data/gold/gen_gate_<name>_manifest.json")
    p.add_argument("--out", default="", help="default data/gold/gen_gate_<name>.jsonl")
    p.add_argument("--jobs", default="", help="default /tmp/tv-gen-gate-<name>/jobs")
    p.add_argument("--extract-dir", default="", help="default: manifest extract_dir")
    p.add_argument("-n", "--concurrency", type=int, default=4, help="harbor --n-concurrent and runner parallelism")
    p.add_argument("-k", type=int, default=2, help="trials per probe (oracle and nop each)")
    p.add_argument(
        "--probes",
        default="oracle,nop",
        help="comma-separated subset of oracle,nop; 'nop' alone runs the one-sided "
        "empty-solution gate and every verdict lands in the none stratum (doc 44)",
    )
    p.add_argument("--budget-sec", type=float, default=24 * 60 * 60)
    p.add_argument("--trial-cap-sec", type=int, default=60 * 60)
    p.add_argument("--timeout-multiplier", type=float, default=1.0)
    p.add_argument("--verifier-timeout-multiplier", type=float, default=2.0)
    p.add_argument("--build-timeout-multiplier", type=float, default=2.0)
    p.add_argument("--prune-every", type=int, default=20, help="docker image+builder prune cadence in tasks; 0 disables")
    p.add_argument("--epsilon", type=float, default=0.05)
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--redo-infra", action="store_true", help="re-execute trials whose latest row is infra or timeout")
    p.add_argument(
        "--no-warmup",
        action="store_true",
        help="dispatch all of a task's trials at once (old behaviour); default runs the first trial alone to warm the image cache",
    )
    p.set_defaults(func=_cmd_generator_gate_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
