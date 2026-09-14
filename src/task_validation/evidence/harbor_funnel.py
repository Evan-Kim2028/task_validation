"""Harbor-Index candidate funnel, reconstructed on the public dump (doc 45/48).

Stage 1 of arXiv 2609.04298 kept candidates with at most a 33% solve rate
over 18 frontier trials (3 trials x 6 frontier cells). The private filtering
database is not public; this module recomputes the same filter from the
kendx/Harbor-Adapter trial dump.

Ordering convention: "the 3 earliest trials per cell" is the first 3
trial_ids in the manifest cell row, i.e. `trial_index` 0..2 as written by
`task_validation.ingest.harbor_adapter.parse_manifest`.

External labels (the 82 published survivors) are evaluation-only (doc 43).
The index renamed every task, so the join to manifest (benchmark,
task_name) goes through each index task's README in
harbor-framework/harbor-index, which names the upstream record.
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from task_validation.evidence.footprint import (
    LOGIT_L2,
    LOGIT_MAX_ITER,
    design_matrix,
    fit_logit,
    predict_logit,
)
from task_validation.evidence.irt import auroc, bootstrap_auroc

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD = REPO_ROOT / "data" / "gold"
RAW = REPO_ROOT / "data" / "raw"

TRIALS_PATH = GOLD / "harbor_adapter_trials.jsonl"
STAGE1_PATH = GOLD / "harbor_funnel_stage1.jsonl"
STAGE1_SUMMARY_PATH = GOLD / "harbor_funnel_stage1.summary.json"
LABELS_PATH = GOLD / "harbor_funnel_labels.jsonl"
STRATA_PATH = GOLD / "harbor_index_strata.json"
MAPPER_JSON_PATH = GOLD / "harbor_funnel_mapper.json"
MAPPER_PNG_PATH = GOLD / "harbor_funnel_mapper.png"
TASK_TRAJ_PATH = GOLD / "harbor_adapter_task_traj.jsonl"
TRAJ_TRIALS_PATH = GOLD / "harbor_adapter_traj.jsonl"
TRAJ_EVAL_PATH = GOLD / "harbor_funnel_traj_eval.json"
HIDDEN_REQ_PATH = GOLD / "harbor_funnel_hidden_requirement.jsonl"
WITHIN_EVAL_PATH = GOLD / "harbor_funnel_within_benchmark.json"

PROTOCOL = "harbor_index_funnel.reconstructed.2026-09-13"

FRONTIER_CELLS = (
    ("claude-code", "claude-opus-4-6"),
    ("terminus-2", "claude-opus-4-6"),
    ("codex", "gpt-5.4"),
    ("terminus-2", "gpt-5.4"),
    ("gemini-cli", "gemini-3.1-pro-preview"),
    ("terminus-2", "gemini-3.1-pro-preview"),
)
TRIALS_PER_CELL = 3
STAGE1_RATE_CUTOFF = 1.0 / 3.0
# Doc 48 phrasing: n_succ <= 6 over up to 18 fetched trials. Equivalent to
# the 33% rate rule at exactly 18 trials; more permissive on sparse tasks.
STAGE1_MAX_SUCC = 6

# Features computable from manifest plus trial rows alone (doc 45 step 4
# adapted: task directories are not fetched, so the doc 40 static layout
# features are unavailable). Reward-derived features are kept in a separate
# group: they are a deterministic function of the stage-1 label and would
# leak it, so the eval matrix uses EXEC_FEATURES only.
EXEC_FEATURES = (
    "n_frontier_trials",
    "n_cells_ge3",
    "full_18",
    "n_all_trials",
    "input_tokens_mean",
    "cache_tokens_mean",
    "output_tokens_mean",
    "cost_usd_mean",
    "cost_usd_total",
    "agent_wall_sec_mean",
    "exception_rate",
)
REWARD_FEATURES = (
    "frontier_solve_rate",
    "frontier_n_succ",
    "reward_var",
    "all_trials_solve_rate",
    "cell_rate_0",
    "cell_rate_1",
    "cell_rate_2",
    "cell_rate_3",
    "cell_rate_4",
    "cell_rate_5",
)
ALL_FEATURES = EXEC_FEATURES + REWARD_FEATURES

# Doc 40 features not computable from manifest plus trial rows alone:
UNAVAILABLE_DOC40_FEATURES = (
    "reference_pass", "nop_reject", "determinism", "environment_failure",
    "instruction_chars", "instruction_lines", "stmt_n_identifiers",
    "test_file_count", "assertion_count", "literal_pins_absent",
    "solution_size", "resource_memory_mb", "resource_cpus", "timeout_sec",
    "network_isolated", "judge_verifier", "test_stmt_id_overlap",
    "test_only_id_frac", "n_fail_to_pass", "n_pass_to_pass",
    "patch_n_files", "patch_n_hunks", "patch_n_changed_lines",
    "test_n_files", "test_n_hunks", "test_n_changed_lines",
    "has_code_fence", "has_traceback", "has_http_url",
    "has_reproduction_hint", "hints_chars", "gold_to_test_line_ratio",
    "f2p_in_statement_frac", "test_has_exact_string_literal",
    "solve_rate_band", "n_attempted",
)

# Bridge: index task id -> manifest (benchmark, task_name). Sources are the
# "Original upstream task" section of each README in harbor-framework/
# harbor-index. None = published survivor with no manifest pair (the
# upstream DA-Code example ml-competition-017 was not sampled into the
# 6,627-candidate manifest).
INDEX_TO_MANIFEST = {
    "algotune-optimize-lti-sim": ("algotune", "algotune-lti-simulation"),
    "algotune-optimize-matrix-sqrt": ("algotune", "algotune-matrix-sqrt"),
    "algotune-optimize-ode-seirs": ("algotune", "algotune-ode-seirs"),
    "algotune-optimize-outer-product": ("algotune", "algotune-outer-product"),
    "algotune-simplex-projection-speedup": ("algotune", "algotune-unit-simplex-projection"),
    "arcagi2-grid-transform-88e3": ("arc-agi-2", "88e364bc_0"),
    "arcagi2-grid-transform-8b7b": ("arc-agi-2", "8b7bacbf_0"),
    "arcagi2-grid-transform-a32d": ("arc-agi-2", "a32d8b75_0"),
    "arcagi2-grid-transform-de80": ("arc-agi-2", "de809cff_0"),
    "arcagi2-grid-transform-faa9": ("arc-agi-2", "faa9f03d_0"),
    "bix-cpg-density-jackdaw": ("bixbench", "bix-52-q2"),
    "bix-diff-expr-mirna": ("bixbench", "bix-30-q1"),
    "bix-filter-chip-variants": ("bixbench", "bix-7-q2"),
    "bix-immune-pathway-enrichment": ("bixbench", "bix-6-q5"),
    "bix-ordinal-logit-covid": ("bixbench", "bix-10-q2"),
    "build-word2vec-pipeline": ("bigcodebench", "bigcodebench_657"),
    "codepde-solve-navier-stokes-1d": ("codepde", "codepde-cns1d"),
    "cybergym-arvo-368": ("cybergym", "cybergym_arvo_368"),
    "cybergym-ossfuzz-42m": ("cybergym", "cybergym_oss-fuzz_42535468"),
    "dacode-predict-essay-scores": None,
    "featurebench-add-feature-lightning-hooks": (
        "featurebench-modal",
        "lightning-ai__pytorch-lightning.126fa6f1.test_hooks.34620588.lv1",
    ),
    "featurebench-add-feature-mlflow-bedrock-autolog": (
        "featurebench-modal",
        "mlflow__mlflow.93dab383.test_bedrock_autolog.f008b521.lv1",
    ),
    "featurebench-add-feature-mlflow-unity-catalog": (
        "featurebench-modal",
        "mlflow__mlflow.93dab383.test_unity_catalog_rest_store.f47a7d9f.lv1",
    ),
    "featurebench-add-feature-xarray-backend-chunks": (
        "featurebench-modal",
        "pydata__xarray.97f3a746.test_backends_chunks.fa55f68a.lv1",
    ),
    "gaia-compare-sciencedirect-domains": ("gaia", "0b260a57-3f3a-4405-9f29-6d7a1012dbfb"),
    "gaia-find-chess-winning-move": ("gaia", "cca530fc-4052-43b2-b130-b30968d8aa44"),
    "gaia-find-flavor-graveyard-rhyme": ("gaia", "624cbf11-6a41-4692-af9c-36b3e5ca3130"),
    "gaia2-adapt-hard-1": ("gaia2", "gaia2-cli/0601_mz4dh4tml93gims9dxwrcz7i16t0p5ud"),
    "gaia2-adapt-hard-2": ("gaia2", "gaia2-cli/0626_cw20wcc87i9wq2c7i5yun18bbsybo9yr"),
    "gaia2-ambiguous": ("gaia2", "gaia2-cli/0160_lz4oktw0o3l9wuwpuwn4x8c653cp1tr6"),
    "gaia2-timed-1": ("gaia2", "gaia2-cli/0777_y3r2nol0ujohv1z7evrnx8llf1ce5hjh"),
    "gaia2-timed-2": ("gaia2", "gaia2-cli/0857_l115ixer60dr5v00hxk5lchc0l83w62e"),
    "gpqadiamond-cope-rearrangement-products": ("gpqa-diamond", "76"),
    "gso-speedup-hf-datasets": ("gso", "gso-gso-huggingface--datasets-5994036"),
    "gso-speedup-numpy-strings": ("gso", "gso-numpy--numpy-ef5e545"),
    "gso-speedup-pandas-merge": ("gso", "gso-pandas-dev--pandas-061c2e9"),
    "gso-speedup-pandas-period-fmt": ("gso", "gso-gso-pandas-dev--pandas-2cdca01"),
    "gso-speedup-pandas-seq-to-range": ("gso", "gso-pandas-dev--pandas-bfaf917"),
    "gso-speedup-pillow-filter": ("gso", "gso-uploadcare--pillow-simd-6eacce9"),
    "gso-speedup-pydantic-enum": ("gso", "gso-gso-pydantic--pydantic-ac9e6ee"),
    "hle-dirac-fermion-tunneling": ("hle", "hle/hle__66ec2799da20d530acf3bf1e"),
    "hle-fibered-category-schemes": ("hle", "hle/hle__6705610417b54abf9a949f33"),
    "hle-identify-city-from-photo": ("hle", "hle/hle__676762beff30b300db258691"),
    "hle-identify-ingvar-runestone": ("hle", "hle/hle__673216bc3125f3eae4e7a0bd"),
    "hle-interval-coverage-bound": ("hle", "hle/hle__66f63324376699e7c6894239"),
    "hle-name-alkaloid-compound": ("hle", "hle/hle__671dacdd355c956ce7de5aa5"),
    "hle-shock-wave-density-profile": ("hle", "hle/hle__6739674739118cf30f5f1075"),
    "hle-vowel-marking-system": ("hle", "hle/hle__6734d8b25e3e83209aa9ebd3"),
    "labbench-count-deg-in-pathway": ("labbench", "figqa-0078"),
    "labbench-habenula-fluorescence-change": ("labbench", "figqa-0104"),
    "labbench-highest-auc-neuron-set": ("labbench", "figqa-0114"),
    "labbench-read-asap2f-step-response": ("labbench", "figqa-0066"),
    "omnimath-find-perfect-square-functions": ("omnimath", "omnimath_2659"),
    "omnimath-maximize-gf-sum": ("omnimath", "omnimath_20"),
    "qcircuitbench-design-ternary-simon-circuit-n3": (
        "qcircuitbench",
        "generalized_simon_ternary-n3",
    ),
    "replicationbench-find-galactic-vz-peaks": (
        "replicationbench",
        "disk_ridges__peak_mean_vz_all",
    ),
    "scicode-dna-binding-site-scanner": ("scicode", "scicode-76"),
    "scicode-gaussian-beam-through-lens": ("scicode", "scicode-28"),
    "scicode-tetrahedron-dos-integral": ("scicode", "scicode-17"),
    "skillsbench-model-investment-shock-gdp": ("skillsbench", "shock-analysis-supply"),
    "skillsbench-ocr-receipts-to-excel": ("skillsbench", "jpg-ocr-stat"),
    "sldbench-discover-vocab-scaling-law": ("sldbench", "vocab_scaling_law"),
    "spider2-dbt-airport-arrivals": ("spider2", "spider2-airport001"),
    "spider2-dbt-twilio-messaging": ("spider2", "twilio001"),
    "swebenchpro-fix-file-suffix-chooser": (
        "swebenchpro",
        "instance_qutebrowser__qutebrowser-c0be28ebee3e1837aaf3f30ec534ccd6d038f129-v9f8e9d96c85c85a605e382f1510bd08563afc566",
    ),
    "swebenchpro-fix-teleport-k8s-session-path": (
        "swebenchpro",
        "instance_gravitational__teleport-eda668c30d9d3b56d9c69197b120b01013611186",
    ),
    "swebenchpro-fix-teleport-mtls-ca-limit": (
        "swebenchpro",
        "instance_gravitational__teleport-5dca072bb4301f4579a15364fcf37cc0c39f7f6c",
    ),
    "swebenchpro-improve-process-signal-messages": (
        "swebenchpro",
        "instance_qutebrowser__qutebrowser-5cef49ff3074f9eab1da6937a141a39a20828502-v02ad04386d5238fe2d1a1be450df257370de4b6a",
    ),
    "swebenchverified-fix-annotate-xy-array-copy": ("swebench-verified", "matplotlib__matplotlib-26466"),
    "swebenchverified-fix-django-mti-parent-link": ("swebench-verified", "django__django-12325"),
    "swebenchverified-fix-django-union-queryset-order": ("swebench-verified", "django__django-10554"),
    "swebenchverified-fix-span-selector-axes-limits": ("swebench-verified", "matplotlib__matplotlib-20676"),
    "swebenchverified-fix-sphinx-literal-nitpick": ("swebench-verified", "sphinx-doc__sphinx-9602"),
    "swelancer-fix-fab-menu-enter-key": ("swe-lancer", "26228-manager-0"),
    "swelancer-fix-ios-keyboard-reopen": ("swe-lancer", "20608-manager-0"),
    "swesmith-fix-oauth1-header-params": (
        "swesmith",
        "oauthlib__oauthlib.1fd52536.combine_file__dk41cpe1",
    ),
    "swtbenchverified-test-runserver-zero-address": ("swtbench", "django__django-16145"),
    "tb-dna-insert": ("terminal-bench", "dna-insert"),
    "tb-make-doom-for-mips": ("terminal-bench", "make-doom-for-mips"),
    "tb-train-fasttext": ("terminal-bench", "train-fasttext"),
    "usaco-assign-cows-to-barns": ("usaco", "1068"),
    "widesearch-list-bri-projects-2025": ("widesearch", "widesearch/widesearch-ws-zh-085"),
}


def _parse_ts(value) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _var(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def select_stage1_trials(task_rows: list[dict]) -> list[dict]:
    """Up to 3 earliest trials per frontier cell for one candidate.

    "Earliest" is manifest order: sort by trial_index, then trial_id for a
    stable tie-break. A trial row may appear once per (agent, model) cell.
    """
    by_cell: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in task_rows:
        cell = (row.get("agent"), row.get("model"))
        if cell in FRONTIER_CELLS:
            by_cell[cell].append(row)
    selected: list[dict] = []
    for cell in FRONTIER_CELLS:
        rows = sorted(
            by_cell.get(cell, []),
            key=lambda r: (r.get("trial_index"), str(r.get("trial_id"))),
        )
        selected.extend(rows[:TRIALS_PER_CELL])
    return selected


def _exec_stats(trials: list[dict]) -> dict:
    ins, caches, outs, costs, walls, excs = [], [], [], [], [], []
    for t in trials:
        ins.append(t.get("n_input_tokens"))
        caches.append(t.get("n_cache_tokens"))
        outs.append(t.get("n_output_tokens"))
        costs.append(t.get("cost_usd"))
        t0 = _parse_ts(t.get("started_at"))
        t1 = _parse_ts(t.get("finished_at"))
        if t0 is not None and t1 is not None:
            walls.append(t1 - t0)
        excs.append(1.0 if t.get("exception") else 0.0)
    return {
        "input_tokens_mean": _mean(ins),
        "cache_tokens_mean": _mean(caches),
        "output_tokens_mean": _mean(outs),
        "cost_usd_mean": _mean(costs),
        "cost_usd_total": sum(c for c in costs if c is not None) if costs else None,
        "agent_wall_sec_mean": _mean(walls),
        "exception_rate": _mean(excs),
    }


def stage1_record(benchmark: str, task_name: str, task_rows: list[dict]) -> dict:
    """One candidate row: frontier selection stats plus all-trials stats."""
    selected = select_stage1_trials(task_rows)
    by_cell: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in selected:
        by_cell[(t["agent"], t["model"])].append(t)

    rewards = [t.get("reward") for t in selected]
    n_succ = sum(1 for r in rewards if r is not None and r > 0)
    n_sel = len(selected)
    solve_rate = (n_succ / n_sel) if n_sel else None
    cell_counts = {i: len(by_cell.get(cell, [])) for i, cell in enumerate(FRONTIER_CELLS)}
    cell_rates = []
    for cell in FRONTIER_CELLS:
        rows = by_cell.get(cell, [])
        k = sum(1 for r in rows if r.get("reward") is not None and r["reward"] > 0)
        cell_rates.append(k / len(rows) if rows else None)

    all_rewards = [t.get("reward") for t in task_rows]
    all_succ = sum(1 for r in all_rewards if r is not None and r > 0)
    n_all = len(all_rewards)

    survived_rate = solve_rate is not None and solve_rate <= STAGE1_RATE_CUTOFF + 1e-9
    survived_n6 = n_sel > 0 and n_succ <= STAGE1_MAX_SUCC

    feats = _exec_stats(selected)
    rec = dict(feats)
    rec.update({
        "benchmark": benchmark,
        "task_name": task_name,
        "n_frontier_trials": n_sel,
        "frontier_n_succ": n_succ,
        "frontier_solve_rate": solve_rate,
        "n_cells_ge1": sum(1 for c in cell_counts.values() if c >= 1),
        "n_cells_ge3": sum(1 for c in cell_counts.values() if c >= TRIALS_PER_CELL),
        "full_18": 1.0 if n_sel == len(FRONTIER_CELLS) * TRIALS_PER_CELL else 0.0,
        "n_all_trials": n_all,
        "all_trials_n_succ": all_succ,
        "all_trials_solve_rate": (all_succ / n_all) if n_all else None,
        "reward_var": _var(rewards),
        "survived_stage1": bool(survived_rate),
        "survived_stage1_n_succ_le6": bool(survived_n6),
    })
    for i, rate in enumerate(cell_rates):
        rec[f"cell_rate_{i}"] = rate
        rec[f"cell_n_{i}"] = cell_counts[i]
    rec["features"] = {k: rec.get(k) for k in EXEC_FEATURES}
    rec["features"].update({k: rec.get(k) for k in REWARD_FEATURES})
    return rec


def aggregate_stage1(trial_rows: list[dict]) -> list[dict]:
    """Group in-scope trial rows by (benchmark, task_name)."""
    by_task: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in trial_rows:
        by_task[(row["benchmark"], row["task_name"])].append(row)
    return [
        stage1_record(b, t, rows)
        for (b, t), rows in sorted(by_task.items())
    ]


def load_in_scope_trials(path: Path = TRIALS_PATH) -> list[dict]:
    rows = []
    with path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("in_scope"):
                rows.append(r)
    return rows


def load_survivor_pairs() -> tuple[dict, list[str], list[str]]:
    """Map manifest pairs -> index id. Returns (pair->id, matched ids, unmatched ids)."""
    strata = json.loads(STRATA_PATH.read_text())
    index_ids = sorted(strata["tasks"].keys())
    pair_to_id = {}
    matched, unmatched = [], []
    for tid in index_ids:
        pair = INDEX_TO_MANIFEST.get(tid)
        if pair is None:
            unmatched.append(tid)
        else:
            pair_to_id[pair] = tid
            matched.append(tid)
    return pair_to_id, matched, unmatched


def write_stage1(records: list[dict]) -> dict:
    """Write stage1 jsonl + summary; return the summary dict."""
    with STAGE1_PATH.open("w") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")

    n = len(records)
    n_full18 = sum(1 for r in records if r["full_18"] == 1.0)
    n_ge3 = sum(1 for r in records if r["n_cells_ge3"] == len(FRONTIER_CELLS))
    n_surv_rate = sum(1 for r in records if r["survived_stage1"])
    n_surv_n6 = sum(1 for r in records if r["survived_stage1_n_succ_le6"])

    # Gap diagnostics vs the published 1,311: survivors by benchmark and
    # mean per-cell coverage, to see what drives any discrepancy.
    by_bench = defaultdict(lambda: {"n": 0, "survived": 0, "n_trials": 0})
    for r in records:
        s = by_bench[r["benchmark"]]
        s["n"] += 1
        s["survived"] += int(r["survived_stage1"])
        s["n_trials"] += r["n_frontier_trials"]
    bench_table = sorted(
        (
            {
                "benchmark": b,
                "n_tasks": s["n"],
                "n_survived": s["survived"],
                "survival_rate": s["survived"] / s["n"] if s["n"] else None,
                "mean_frontier_trials": s["n_trials"] / s["n"] if s["n"] else None,
            }
            for b, s in by_bench.items()
        ),
        key=lambda d: -(d["n_survived"]),
    )
    # Per-cell coverage: how many candidates have >=3 trials in each cell.
    per_cell_ge3 = {}
    per_cell_any = {}
    for i, (a, m) in enumerate(FRONTIER_CELLS):
        per_cell_ge3[f"{a}/{m}"] = sum(1 for r in records if r.get(f"cell_n_{i}", 0) >= 3)
        per_cell_any[f"{a}/{m}"] = sum(1 for r in records if r.get(f"cell_n_{i}", 0) >= 1)

    summary = {
        "protocol": PROTOCOL,
        "source": "kendx/Harbor-Adapter public trial dump, in-scope rows",
        "selection": "first 3 manifest trial_ids per frontier cell (trial_index 0-2)",
        "frontier_cells": [{"agent": a, "model": m} for a, m in FRONTIER_CELLS],
        "n_candidates": n,
        "n_full_18_coverage": n_full18,
        "n_ge3_all_six_cells": n_ge3,
        "expected_n_ge3_all_six_cells": 5684,
        "n_survived_stage1_rate_le_33pct": n_surv_rate,
        "n_survived_stage1_n_succ_le6": n_surv_n6,
        "published_stage1_survivors": 1311,
        "rate_rule_vs_published": {
            "diff": n_surv_rate - 1311,
            "abs_pct_diff": abs(n_surv_rate - 1311) / 1311.0,
        },
        "n6_rule_vs_published": {
            "diff": n_surv_n6 - 1311,
            "abs_pct_diff": abs(n_surv_n6 - 1311) / 1311.0,
        },
        "per_cell_ge3_coverage": per_cell_ge3,
        "per_cell_any_coverage": per_cell_any,
        "survivors_by_benchmark": bench_table,
    }
    return summary


def write_labels(records: list[dict]) -> dict:
    pair_to_id, matched, unmatched = load_survivor_pairs()
    id_to_pair = {v: k for k, v in pair_to_id.items()}
    with LABELS_PATH.open("w") as fh:
        for rec in records:
            pair = (rec["benchmark"], rec["task_name"])
            index_id = pair_to_id.get(pair)
            funnel = index_id is not None
            s1 = bool(rec["survived_stage1"])
            row = {
                "benchmark": rec["benchmark"],
                "task_name": rec["task_name"],
                "index_task_id": index_id,
                "survived_stage1": s1,
                "survived_funnel": funnel,
                "survived_2_to_4": (funnel if s1 else None),
                "protocol": PROTOCOL,
                "treatment_grade": {
                    "survived_stage1": "B",
                    "survived_funnel": "A",
                    "survived_2_to_4": "A",
                },
                "provenance": (
                    "survived_stage1 reconstructed from public Harbor-Adapter "
                    "trials (grade B); survived_funnel is the published 82-task "
                    "Harbor-Index list joined through harbor-index README "
                    "upstream records (grade A); survived_2_to_4 is the "
                    "published survivors conditioned on the reconstructed "
                    "stage-1 pass. External labels, eval-only (doc 43)."
                ),
            }
            fh.write(json.dumps(row) + "\n")
    matched_on_survivors = [
        tid for tid, pair in id_to_pair.items()
        if pair in {(r["benchmark"], r["task_name"]) for r in records if r["survived_stage1"]}
    ]
    return {
        "n_index_tasks": len(matched) + len(unmatched),
        "n_matched_to_manifest": len(matched),
        "unmatched_index_tasks": unmatched,
        "n_matched_and_survived_stage1": len(matched_on_survivors),
        "matched_but_not_stage1": sorted(set(matched) - set(matched_on_survivors)),
    }


def _label_vector(records: list[dict], label: str) -> tuple[list[int], list[dict]]:
    rows, y = [], []
    for r in records:
        if label == "survived_2_to_4":
            v = r["survived_funnel"] if r["survived_stage1"] else None
        else:
            v = r[label]
        if v is None:
            continue
        rows.append(r)
        y.append(int(v))
    return y, rows


def _fit_logit_fast(X: list[list[float]], y: list[int]) -> dict:
    """numpy mirror of footprint.fit_logit: same class weights, IRLS with L2
    on coefficients only, same iteration cap and convergence tolerance. Used
    for the doc 54 feature-set grid where the pure-Python path is too slow.
    """
    import numpy as np

    n = len(y)
    if not n:
        return {"coef": [], "intercept": 0.0, "ok": False, "reason": "empty"}
    n_pos = sum(y)
    n_neg = n - n_pos
    pdim = len(X[0]) if X else 0
    if n_pos == 0 or n_neg == 0:
        p = n_pos / n
        intercept = (
            math.log(p / (1.0 - p)) if 0.0 < p < 1.0 else (10.0 if p >= 1 else -10.0)
        )
        return {
            "coef": [0.0] * pdim,
            "intercept": intercept,
            "ok": False,
            "reason": "constant_y",
        }
    Xa = np.asarray(X, dtype=float)
    ya = np.asarray(y, dtype=float)
    X1 = np.concatenate([np.ones((n, 1)), Xa], axis=1)
    w_obs = np.where(ya == 1.0, n / (2.0 * n_pos), n / (2.0 * n_neg))
    beta = np.zeros(pdim + 1)
    for _ in range(LOGIT_MAX_ITER):
        eta = X1 @ beta
        p_hat = 1.0 / (1.0 + np.exp(-np.clip(eta, -60.0, 60.0)))
        pc = np.clip(p_hat, 1e-6, 1.0 - 1e-6)
        wi = w_obs * pc * (1.0 - pc)
        z = eta + (ya - pc) / (pc * (1.0 - pc))
        WX = X1 * wi[:, None]
        A = X1.T @ WX
        bvec = WX.T @ z
        A[range(1, pdim + 1), range(1, pdim + 1)] += LOGIT_L2
        try:
            sol = np.linalg.solve(A, bvec)
        except np.linalg.LinAlgError:
            break
        delta = float(((sol - beta) ** 2).sum())
        beta = sol
        if delta < 1e-10:
            break
    return {
        "coef": beta[1:].tolist(),
        "intercept": float(beta[0]),
        "ok": True,
        "reason": None,
    }


def _oof_predict(
    rows: list[dict],
    y: list[int],
    feature_names: tuple[str, ...],
    fold_key: str,
    fitter,
) -> tuple[list[float], dict, int]:
    """Grouped out-of-fold scores: rows[i] is scored by a model fit on all
    rows outside its fold, so no task is scored by a model that saw it."""
    by_fold = defaultdict(list)
    for i, r in enumerate(rows):
        by_fold[r[fold_key]].append(i)

    oof = [None] * len(rows)
    fold_aurocs = {}
    n_undefined = 0
    for fold in sorted(by_fold):
        test_set = set(by_fold[fold])
        test_idx = by_fold[fold]
        train_idx = [i for i in range(len(rows)) if i not in test_set]
        train_rows = [rows[i] for i in train_idx]
        test_rows = [rows[i] for i in test_idx]
        ytr = [y[i] for i in train_idx]
        yte = [y[i] for i in test_idx]
        Xtr, stats = design_matrix(train_rows, feature_names)
        Xte, _ = design_matrix(test_rows, feature_names, stats=stats)
        model = fitter(Xtr, ytr)
        scores = predict_logit(model, Xte)
        for i, s in zip(test_idx, scores):
            oof[i] = s
        a = auroc(yte, scores)
        if a is None:
            n_undefined += 1
        else:
            fold_aurocs[fold] = a
    return oof, fold_aurocs, n_undefined


def eval_label(
    rows: list[dict],
    y: list[int],
    feature_names: tuple[str, ...] = EXEC_FEATURES,
    *,
    fold_key: str = "benchmark",
    fitter=fit_logit,
    seed: int = 20260913,
) -> dict:
    """Leave-one-fold-out logistic AUROC plus naive pooled contrast.

    Folds are the distinct values of rows[i][fold_key]; the default
    "benchmark" reproduces doc 52, "family" gives the doc 54
    leave-one-benchmark-family-out variant. Same model class as doc 40:
    median imputation, missingness indicators, standardized design matrix,
    L2 logit (fit_logit in footprint.py, or its numpy mirror).
    """
    by_fold = defaultdict(list)
    for i, r in enumerate(rows):
        by_fold[r[fold_key]].append(i)

    oof, fold_aurocs, n_undefined = _oof_predict(
        rows, y, feature_names, fold_key, fitter
    )

    boot = bootstrap_auroc(y, [s for s in oof], n_reps=400, seed=seed)
    # Naive pooled: fit and score on all rows.
    Xall, _ = design_matrix(rows, feature_names)
    pooled_model = fitter(Xall, y)
    pooled_scores = predict_logit(pooled_model, Xall)
    pooled = auroc(y, pooled_scores)
    return {
        "n": len(y),
        "n_pos": sum(y),
        "lobo_auroc": boot["value"],
        "lobo_ci95": boot["ci95"],
        "pooled_auroc": pooled,
        "fold_key": fold_key,
        "n_folds": len(by_fold),
        "n_folds_undefined_auroc": n_undefined,
        "fold_aurocs": fold_aurocs,
    }


def eval_solve_rate_only(records: list[dict]) -> dict:
    """AUROC of stage-1 solve rate alone on survived_2_to_4."""
    rows, y = [], []
    for r in records:
        if not r["survived_stage1"]:
            continue
        rate = r["frontier_solve_rate"]
        if rate is None:
            continue
        rows.append(r)
        y.append(int(r["survived_funnel"]))
    # Lower rate -> harder task -> more likely curated? Use -rate so higher
    # score means "more likely survivor"; AUROC is symmetric under sign flip
    # only if we report 1-a. Report auroc of rate itself and its complement.
    scores = [-r["frontier_solve_rate"] for r in rows]
    boot = bootstrap_auroc(y, scores, n_reps=400, seed=20260913)
    return {"n": len(y), "n_pos": sum(y), "auroc_neg_rate": boot["value"], "ci95": boot["ci95"],
            "auroc_raw_rate": auroc(y, [r["frontier_solve_rate"] for r in rows])}


# --- Doc 54: trajectory and verifier feature extension ---------------------
#
# Group A is the doc 52 execution set (EXEC_FEATURES from stage-1 records).
# Groups B, C, D come from the trajectory extract: B and the rate half of C
# and all of D are read off the "frontier" bundle of
# harbor_adapter_task_traj.jsonl (all frontier-cell trials in the dump, not
# only the 18 stage-1-selected). The two failed-test signature features
# (share of failing frontier trials sharing the single most common failed
# test; distinct failed tests) are not in the per-task aggregate, so they are
# recomputed by streaming harbor_adapter_traj.jsonl restricted to the six
# frontier cells.

_FRONTIER_BUNDLE_MAP = {
    "traj_n_steps_mean": "n_steps_mean",
    "traj_n_tool_calls_mean": "n_tool_calls_mean",
    "traj_assistant_chars_mean": "total_assistant_chars_mean",
    "traj_observation_chars_mean": "total_observation_chars_mean",
    "traj_hit_timeout_rate": "hit_timeout_rate",
    "traj_exception_rate": "exception_rate",
    "traj_agent_wall_sec_mean": "agent_wall_sec_mean",
    "ver_has_report_json_rate": "has_report_json_rate",
    "ver_n_tests_total_mean": "n_tests_total_mean",
    "ver_n_tests_failed_mean": "n_tests_failed_mean",
    "ver_reward_partial_rate": "reward_partial_rate",
    "shortcut_answer_file_rate": "mentions_answer_file_rate",
    "shortcut_git_probe_rate": "git_history_probe_rate",
    "shortcut_network_fetch_rate": "network_fetch_rate",
}
TRAJ_FEATURES = (
    "traj_n_steps_mean",
    "traj_n_tool_calls_mean",
    "traj_assistant_chars_mean",
    "traj_observation_chars_mean",
    "traj_hit_timeout_rate",
    "traj_exception_rate",
    "traj_agent_wall_sec_mean",
)
VERIFIER_FEATURES = (
    "ver_has_report_json_rate",
    "ver_n_tests_total_mean",
    "ver_n_tests_failed_mean",
    "ver_reward_partial_rate",
    "ver_top_failed_share",
    "ver_n_distinct_failed_tests",
)
SHORTCUT_FEATURES = (
    "shortcut_answer_file_rate",
    "shortcut_git_probe_rate",
    "shortcut_network_fetch_rate",
)
FEATURE_GROUPS = {
    "A": EXEC_FEATURES,
    "B": TRAJ_FEATURES,
    "C": VERIFIER_FEATURES,
    "D": SHORTCUT_FEATURES,
}
FEATURE_SETS = {
    "A": EXEC_FEATURES,
    "A+B": EXEC_FEATURES + TRAJ_FEATURES,
    "A+B+C": EXEC_FEATURES + TRAJ_FEATURES + VERIFIER_FEATURES,
    "A+B+C+D": EXEC_FEATURES + TRAJ_FEATURES + VERIFIER_FEATURES + SHORTCUT_FEATURES,
    "B+C+D": TRAJ_FEATURES + VERIFIER_FEATURES + SHORTCUT_FEATURES,
}
# Leave-one-benchmark-FAMILY-out grouping (doc 54): benchmarks that share a
# generator or task family count as one fold, so held-out scores cannot ride
# on within-family source recognition. Everything else folds by benchmark.
SWE_FAMILY = frozenset(
    {
        "swebench-verified",
        "swebenchpro",
        "swesmith",
        "swebench-multilingual",
        "swtbench",
        "multi-swe-bench",
        "swe-lancer",
    }
)
TERMINAL_FAMILY = frozenset({"terminal-bench", "skillsbench", "compilebench"})
MATH_QA_FAMILY = frozenset(
    {
        "aime",
        "omnimath",
        "ineqmath",
        "gpqa-diamond",
        "hle",
        "simpleqa",
        "mmmlu",
        "arc-agi-2",
    }
)
BENCHMARK_FAMILIES = (
    ("swe_family", SWE_FAMILY),
    ("terminal_family", TERMINAL_FAMILY),
    ("math_qa_family", MATH_QA_FAMILY),
)
_BENCH_TO_FAMILY = {b: fam for fam, members in BENCHMARK_FAMILIES for b in members}
_FRONTIER_CELL_SET = frozenset(FRONTIER_CELLS)

STOP_RULE_THRESHOLD = 0.65  # doc 45 stop rule for survived_2_to_4
MIN_FAILING_FRONTIER_TRIALS = 6  # doc 54 hidden-requirement flag


def benchmark_family(benchmark: str) -> str:
    """Fold key for the family variant; unmatched benchmarks fold alone."""
    return _BENCH_TO_FAMILY.get(benchmark, benchmark)


def join_task_traj(
    label_rows: list[dict], task_traj_rows: list[dict]
) -> tuple[list[dict], dict]:
    """Left-join per-task trajectory aggregates onto label rows.

    Key is (benchmark, task_name). Unmatched label rows keep "traj" = None;
    their B/C/D features stay missing and surface as imputation plus
    missingness indicators in the eval matrix.
    """
    by_pair: dict[tuple[str, str], dict] = {}
    n_dup = 0
    for r in task_traj_rows:
        key = (r["benchmark"], r["task_name"])
        if key in by_pair:
            n_dup += 1
        by_pair[key] = r
    label_keys = {(r["benchmark"], r["task_name"]) for r in label_rows}
    joined, missing = [], []
    for lab in label_rows:
        key = (lab["benchmark"], lab["task_name"])
        rec = dict(lab)
        rec["traj"] = by_pair.get(key)
        if rec["traj"] is None:
            missing.append(key)
        joined.append(rec)
    coverage = {
        "n_label_rows": len(label_rows),
        "n_task_traj_rows": len(task_traj_rows),
        "n_matched": len(label_rows) - len(missing),
        "n_unmatched_labels": len(missing),
        "unmatched_label_keys": [f"{b}|{t}" for b, t in missing],
        "n_task_traj_not_in_labels": sum(
            1 for k in by_pair if k not in label_keys
        ),
        "n_duplicate_task_traj_keys": n_dup,
        "match_rate": (len(label_rows) - len(missing)) / len(label_rows)
        if label_rows
        else None,
    }
    return joined, coverage


def frontier_failed_test_stats(
    path: Path = TRAJ_TRIALS_PATH,
    pairs: set[tuple[str, str]] | None = None,
) -> dict:
    """Stream per-trial rows; per task: failing-frontier count, distinct
    failed tests, and the share of failing frontier trials containing the
    single most common failed test (the hidden-requirement signature).

    A failing trial is one with n_tests_failed > 0; failed test names are
    per-trial deduped upstream, so a Counter value is a trial count.
    """
    states: dict[tuple[str, str], dict] = {}
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            if not r.get("in_scope"):
                continue
            if (r.get("agent"), r.get("model")) not in _FRONTIER_CELL_SET:
                continue
            key = (r["benchmark"], r["task_name"])
            if pairs is not None and key not in pairs:
                continue
            st = states.get(key)
            if st is None:
                st = {"n_frontier": 0, "n_failing": 0, "failed": Counter()}
                states[key] = st
            st["n_frontier"] += 1
            if (r.get("n_tests_failed") or 0) > 0:
                st["n_failing"] += 1
                for name in r.get("failed_test_names") or []:
                    st["failed"][name] += 1
    out = {}
    for key, st in states.items():
        top_name, top_n = (st["failed"].most_common(1)[0] if st["failed"] else (None, 0))
        nf = st["n_failing"]
        out[key] = {
            "n_frontier_trials_seen": st["n_frontier"],
            "n_failing_frontier_trials": nf,
            "n_distinct_failed_tests": len(st["failed"]),
            "top_failed_test": top_name,
            "top_failed_share": (top_n / nf) if nf else None,
        }
    return out


def build_traj_eval_records(
    label_rows: list[dict],
    stage1_rows: list[dict],
    task_traj_rows: list[dict],
    failed_stats: dict,
) -> tuple[list[dict], dict]:
    """Merge labels + stage-1 (A) + trajectory/verifier/shortcut features.

    Returns (records, join_coverage). Each record carries a flat "features"
    dict spanning groups A-D; unmatched trajectory rows leave B/C/D missing.
    """
    joined, coverage = join_task_traj(label_rows, task_traj_rows)
    stage1_by_pair = {(r["benchmark"], r["task_name"]): r for r in stage1_rows}
    n_surv_matched = 0
    n_funnel_matched = 0
    records = []
    for rec in joined:
        lab = {k: rec[k] for k in rec if k != "traj"}
        key = (lab["benchmark"], lab["task_name"])
        t = rec["traj"]
        if t is not None and lab.get("survived_stage1"):
            n_surv_matched += 1
        if t is not None and lab.get("survived_funnel"):
            n_funnel_matched += 1
        fb = (t or {}).get("frontier") or {}
        fs = failed_stats.get(key) or {}
        s1 = stage1_by_pair.get(key) or {}
        feats = {k: s1.get(k) for k in EXEC_FEATURES}
        for dst, src in _FRONTIER_BUNDLE_MAP.items():
            feats[dst] = fb.get(src)
        feats["ver_top_failed_share"] = fs.get("top_failed_share")
        nd = fs.get("n_distinct_failed_tests")
        feats["ver_n_distinct_failed_tests"] = float(nd) if nd is not None else None
        records.append(
            {
                "benchmark": lab["benchmark"],
                "task_name": lab["task_name"],
                "family": benchmark_family(lab["benchmark"]),
                "index_task_id": lab.get("index_task_id"),
                "survived_stage1": lab["survived_stage1"],
                "survived_funnel": lab["survived_funnel"],
                "survived_2_to_4": lab["survived_2_to_4"],
                "frontier_solve_rate": s1.get("frontier_solve_rate"),
                "n_failing_frontier_trials": fs.get("n_failing_frontier_trials", 0),
                "n_frontier_trials_seen": fs.get("n_frontier_trials_seen", 0),
                "n_distinct_failed_tests": fs.get("n_distinct_failed_tests", 0),
                "top_failed_test": fs.get("top_failed_test"),
                "top_failed_share": fs.get("top_failed_share"),
                "features": feats,
            }
        )
    coverage["n_stage1_survivors_matched"] = n_surv_matched
    coverage["n_survived_funnel_matched"] = n_funnel_matched
    return records, coverage


def hidden_requirement_flags(
    records: list[dict],
    min_failing: int = MIN_FAILING_FRONTIER_TRIALS,
    top_n: int = 20,
) -> list[dict]:
    """Stage-1 survivors whose failing frontier trials concentrate on one
    test: a candidate machine flag for broken tasks stage 2 should catch.

    Ordered by share of failing frontier trials containing the most common
    failed test, then by failing-trial count, then key. Eval-only evidence;
    never a bound input (doc 43).
    """
    cands = [
        r
        for r in records
        if r["survived_stage1"]
        and r["n_failing_frontier_trials"] >= min_failing
        and r["top_failed_share"] is not None
    ]
    cands.sort(
        key=lambda r: (
            -r["top_failed_share"],
            -r["n_failing_frontier_trials"],
            r["benchmark"],
            r["task_name"],
        )
    )
    out = []
    for rank, r in enumerate(cands[:top_n], start=1):
        out.append(
            {
                "rank": rank,
                "benchmark": r["benchmark"],
                "task_name": r["task_name"],
                "index_task_id": r["index_task_id"],
                "survived_funnel": r["survived_funnel"],
                "survived_2_to_4": r["survived_2_to_4"],
                "frontier_solve_rate": r["frontier_solve_rate"],
                "n_frontier_trials_seen": r["n_frontier_trials_seen"],
                "n_failing_frontier_trials": r["n_failing_frontier_trials"],
                "n_distinct_failed_tests": r["n_distinct_failed_tests"],
                "top_failed_test": r["top_failed_test"],
                "top_failed_share": r["top_failed_share"],
                "protocol": PROTOCOL,
                "evidence_grade": "eval-only candidate flag (doc 43, doc 54)",
            }
        )
    return out


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def run_traj_eval(
    labels_path: Path = LABELS_PATH,
    stage1_path: Path = STAGE1_PATH,
    task_traj_path: Path = TASK_TRAJ_PATH,
    traj_trials_path: Path = TRAJ_TRIALS_PATH,
    out_json: Path = TRAJ_EVAL_PATH,
    out_hidden: Path = HIDDEN_REQ_PATH,
) -> dict:
    """Doc 54 pipeline: join, feature groups A-D, LOBO + family LOFO evals,
    univariate table, stop-rule application, hidden-requirement flags."""
    label_rows = _load_jsonl(labels_path)
    stage1_rows = _load_jsonl(stage1_path)
    task_traj_rows = _load_jsonl(task_traj_path)
    label_pairs = {(r["benchmark"], r["task_name"]) for r in label_rows}
    print(f"[traj_eval] labels={len(label_rows)} task_traj={len(task_traj_rows)}")
    failed_stats = frontier_failed_test_stats(traj_trials_path, pairs=label_pairs)
    print(f"[traj_eval] failed-test stats for {len(failed_stats)} tasks")
    records, coverage = build_traj_eval_records(
        label_rows, stage1_rows, task_traj_rows, failed_stats
    )
    coverage["n_stage1_survivors"] = sum(
        1 for r in records if r["survived_stage1"]
    )
    coverage["n_survived_funnel"] = sum(
        1 for r in records if r["survived_funnel"]
    )

    evals: dict = {}
    for label in ("survived_2_to_4", "survived_funnel"):
        y, rows = _label_vector(records, label)
        per_label = {}
        for set_name, feats in FEATURE_SETS.items():
            per_label[set_name] = {
                "lobo": eval_label(
                    rows, y, feats, fold_key="benchmark", fitter=_fit_logit_fast
                ),
                "lofo": eval_label(
                    rows, y, feats, fold_key="family", fitter=_fit_logit_fast
                ),
            }
            print(
                f"[traj_eval] {label} {set_name} "
                f"lobo={per_label[set_name]['lobo']['lobo_auroc']:.4f} "
                f"lofo={per_label[set_name]['lofo']['lobo_auroc']:.4f}",
                flush=True,
            )
        evals[label] = per_label

    y24, rows24 = _label_vector(records, "survived_2_to_4")
    yfun, rowsfun = _label_vector(records, "survived_funnel")
    all_feats = FEATURE_SETS["A+B+C+D"]
    univariate = []
    for f in all_feats:
        group = next(g for g, fs in FEATURE_GROUPS.items() if f in fs)
        e24 = eval_label(
            rows24, y24, (f,), fold_key="benchmark", fitter=_fit_logit_fast
        )
        efun = eval_label(
            rowsfun, yfun, (f,), fold_key="benchmark", fitter=_fit_logit_fast
        )
        univariate.append(
            {
                "feature": f,
                "group": group,
                "survived_2_to_4_lobo_auroc": e24["lobo_auroc"],
                "survived_funnel_lobo_auroc": efun["lobo_auroc"],
            }
        )
    univariate.sort(
        key=lambda d: -(d["survived_2_to_4_lobo_auroc"] or 0.0)
    )

    flags = hidden_requirement_flags(records)
    n_flag_among_82 = sum(1 for f in flags if f["survived_funnel"])
    with out_hidden.open("w", encoding="utf-8") as fh:
        for row in flags:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    n_eligible = sum(
        1
        for r in records
        if r["survived_stage1"]
        and r["n_failing_frontier_trials"] >= MIN_FAILING_FRONTIER_TRIALS
    )
    signature_computable = [
        {
            "benchmark": k[0],
            "task_name": k[1],
            "n_failing_frontier_trials": v["n_failing_frontier_trials"],
            "n_distinct_failed_tests": v["n_distinct_failed_tests"],
            "top_failed_test": v["top_failed_test"],
            "top_failed_share": v["top_failed_share"],
            "survived_stage1": next(
                r["survived_stage1"]
                for r in records
                if (r["benchmark"], r["task_name"]) == k
            ),
        }
        for k, v in failed_stats.items()
        if v["n_failing_frontier_trials"] > 0
    ]

    headline = evals["survived_2_to_4"]["A+B+C+D"]["lofo"]
    stop = {
        "rule": "doc 45: LOBO AUROC for survived_2_to_4 under 0.65 means the funnel footprint is benchmark identity and the plan stops",
        "applied_to": "leave-one-benchmark-family-out AUROC, survived_2_to_4, feature set A+B+C+D",
        "threshold": STOP_RULE_THRESHOLD,
        "value": headline["lobo_auroc"],
        "ci95": headline["lobo_ci95"],
        "triggers": bool(
            headline["lobo_auroc"] is not None
            and headline["lobo_auroc"] < STOP_RULE_THRESHOLD
        ),
    }
    stop["decision"] = (
        "STOP: the family-held-out footprint is benchmark identity"
        if stop["triggers"]
        else "CONTINUE: letter of the stop rule not met at family granularity"
    )

    out = {
        "protocol": PROTOCOL,
        "inputs": {
            "labels": str(labels_path),
            "stage1": str(stage1_path),
            "task_traj": str(task_traj_path),
            "traj_trials": str(traj_trials_path),
        },
        "join_coverage": coverage,
        "feature_groups": {k: list(v) for k, v in FEATURE_GROUPS.items()},
        "feature_sets": {k: list(v) for k, v in FEATURE_SETS.items()},
        "benchmark_families": {
            fam: sorted(members) for fam, members in BENCHMARK_FAMILIES
        },
        "evals": evals,
        "univariate_lobo": univariate,
        "stop_rule": stop,
        "hidden_requirement": {
            "path": str(out_hidden),
            "min_failing_frontier_trials": MIN_FAILING_FRONTIER_TRIALS,
            "n_flagged": len(flags),
            "n_flagged_among_82": n_flag_among_82,
            "n_flagged_rejected": len(flags) - n_flag_among_82,
            "n_stage1_survivors_eligible": n_eligible,
            "signature_computable_tasks": signature_computable,
            "coverage_note": (
                "Named failed tests exist only for skillsbench in this "
                "extract: _report_stats parses pytest-style report.json, and "
                "the swebench-verified and spreadsheetbench reports use other "
                "schemas (40,093 in-scope rows carry report.json; 133 carry "
                "parsed failed test names, all skillsbench). The flag is "
                "therefore unevaluable on the survivor population."
            ),
        },
    }
    out_json.write_text(json.dumps(out, indent=1, sort_keys=False) + "\n")
    return out


# --- Doc 54 correction: within-benchmark signal -----------------------------
#
# The doc 54 held-out numbers are transfer tests: leave-one-benchmark-out
# asks whether a signature learned on other benchmarks predicts an unseen
# one. That test cannot refute the different hypothesis that each benchmark
# population carries its own signature. The pooled AUROC is also confounded:
# AUROC is a pairwise ranking statistic, so pooling lets the model earn
# credit for separating tasks from different benchmarks. This section
# restricts every comparison pair to tasks from the same benchmark, where
# benchmark identity carries no information, in two ways: (1) pooled-trained
# OOF scores evaluated within each benchmark, and (2) a model trained and
# cross-validated inside one benchmark at a time.

WITHIN_MIN_POS = 5  # minimum kept tasks for a benchmark to enter either eval
WITHIN_MIN_NEG = 5  # minimum rejected survivors for the OOF eval
CV_5FOLD_MIN_CLASS = 10  # 5-fold needs ~2 of each class per test fold
WITHIN_BOOT_SEED = 20260914
WITHIN_FEATURE_SETS = ("A", "A+B", "A+B+C+D")


def within_group_concordance(
    y: list[int], scores: list[float], groups: list
) -> dict:
    """AUROC computed over same-group pairs only.

    A positive scores above a same-group negative = 1, a tie = 0.5 (the
    Mann-Whitney numerator summed over groups before dividing). Cross-group
    pairs never enter, so group identity cannot earn credit.
    """
    import bisect

    by_group: dict = defaultdict(lambda: [[], []])
    for t, s, g in zip(y, scores, groups):
        if s is None:
            continue
        by_group[g][0 if t == 1 else 1].append(s)
    num = 0.0
    den = 0
    for pos_scores, neg_scores in by_group.values():
        if not pos_scores or not neg_scores:
            continue
        neg_sorted = sorted(neg_scores)
        n_neg = len(neg_sorted)
        for s in pos_scores:
            lo = bisect.bisect_left(neg_sorted, s)
            hi = bisect.bisect_right(neg_sorted, s)
            num += lo + 0.5 * (hi - lo)
            den += n_neg
    return {
        "value": (num / den) if den else None,
        "n_pairs": den,
        "concordant_pair_equivalents": num,
    }


def _stratified_boot_idx(groups: list, rng: random.Random) -> list[int]:
    """Resample tasks within each group, preserving per-group sizes."""
    by_g = defaultdict(list)
    for i, g in enumerate(groups):
        by_g[g].append(i)
    idx = []
    for members in by_g.values():
        idx.extend(rng.choice(members) for _ in members)
    return idx


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    i = p * (len(ys) - 1)
    lo = int(i)
    hi = min(lo + 1, len(ys) - 1)
    w = i - lo
    return ys[lo] * (1.0 - w) + ys[hi] * w


def _pos_weighted_mean_auroc(
    y: list[int], scores: list[float], groups: list
) -> float | None:
    """Mean of per-group AUROC weighted by each group's positive count.

    Groups whose (resampled) labels are single-class contribute nothing.
    """
    by_g = defaultdict(lambda: [[], []])
    for t, s, g in zip(y, scores, groups):
        by_g[g][t].append(s)
    num = 0.0
    wsum = 0
    for neg_scores, pos_scores in by_g.values():
        if not pos_scores or not neg_scores:
            continue
        n_pos = len(pos_scores)
        yg = [1] * n_pos + [0] * len(neg_scores)
        a = auroc(yg, pos_scores + neg_scores)
        if a is not None:
            num += a * n_pos
            wsum += n_pos
    return (num / wsum) if wsum else None


def _seed_for(seed: int, tag: str) -> int:
    return seed + sum(ord(c) for c in tag)


def within_benchmark_eval(
    rows: list[dict],
    y: list[int],
    scores: list[float],
    *,
    min_pos: int = WITHIN_MIN_POS,
    min_neg: int = WITHIN_MIN_NEG,
    n_reps: int = 400,
    seed: int = WITHIN_BOOT_SEED,
) -> dict:
    """Within-benchmark AUROC of precomputed honest scores.

    scores[i] must be an honest score for rows[i] (grouped OOF, so no task
    is scored by a model that saw it). Per benchmark with at least min_pos
    positives and min_neg negatives: AUROC plus a bootstrap interval over
    that benchmark's tasks. Plus a positives-weighted mean across qualified
    benchmarks, and the same statistic as one concordance over all
    within-benchmark pairs (pair-count weighted rather than mean-of-AUROC).
    """
    groups = [r["benchmark"] for r in rows]
    by_b = defaultdict(list)
    for i, b in enumerate(groups):
        by_b[b].append(i)

    per_bench = []
    qualified = set()
    for b in sorted(by_b):
        idx = by_b[b]
        yb = [y[i] for i in idx]
        sb = [scores[i] for i in idx]
        n_pos = sum(yb)
        n_neg = len(yb) - n_pos
        qual = n_pos >= min_pos and n_neg >= min_neg
        entry = {
            "benchmark": b,
            "n": len(idx),
            "n_pos": n_pos,
            "n_neg": n_neg,
            "n_pairs": n_pos * n_neg,
            "qualified": qual,
            "auroc": auroc(yb, sb),
            "ci95": None,
        }
        if qual:
            boot = bootstrap_auroc(
                yb, sb, n_reps=n_reps, seed=_seed_for(seed, b)
            )
            entry["ci95"] = boot["ci95"]
            qualified.add(b)
        per_bench.append(entry)

    q_idx = [i for i, b in enumerate(groups) if b in qualified]
    yq = [y[i] for i in q_idx]
    sq = [scores[i] for i in q_idx]
    gq = [groups[i] for i in q_idx]

    rng = random.Random(seed)
    wboots, cboots, cboots_q = [], [], []
    for _ in range(n_reps):
        bidx = _stratified_boot_idx(gq, rng)
        yb_ = [yq[i] for i in bidx]
        sb_ = [sq[i] for i in bidx]
        gb_ = [gq[i] for i in bidx]
        w = _pos_weighted_mean_auroc(yb_, sb_, gb_)
        if w is not None:
            wboots.append(w)
        c = within_group_concordance(yb_, sb_, gb_)
        if c["value"] is not None:
            cboots_q.append(c["value"])
        aidx = _stratified_boot_idx(groups, rng)
        c = within_group_concordance(
            [y[i] for i in aidx], [scores[i] for i in aidx], groups
        )
        if c["value"] is not None:
            cboots.append(c["value"])

    conc_all = within_group_concordance(y, scores, groups)
    conc_q = within_group_concordance(yq, sq, gq)
    # Exact pair decomposition: the pooled AUROC is a pair-count weighted
    # mean of within-benchmark and cross-benchmark pair concordance. The
    # cross term is the component that can ride on benchmark identity.
    n_pos_all = sum(y)
    n_pairs_total = n_pos_all * (len(y) - n_pos_all)
    pooled = auroc(y, scores)
    c_total = pooled * n_pairs_total if pooled is not None else None
    n_cross = n_pairs_total - conc_all["n_pairs"]
    c_cross = (
        c_total - conc_all["concordant_pair_equivalents"]
        if c_total is not None
        else None
    )
    return {
        "min_pos": min_pos,
        "min_neg": min_neg,
        "n_benchmarks_qualified": len(qualified),
        "per_benchmark": per_bench,
        "positives_weighted_mean": {
            "value": _pos_weighted_mean_auroc(yq, sq, gq),
            "ci95": [_pct(wboots, 0.025), _pct(wboots, 0.975)],
            "n_bootstrap": n_reps,
            "n_defined": len(wboots),
        },
        "concordance_all_pairs": {
            **conc_all,
            "ci95": [_pct(cboots, 0.025), _pct(cboots, 0.975)],
            "n_bootstrap": n_reps,
            "n_defined": len(cboots),
        },
        "concordance_qualified_pairs": {
            **conc_q,
            "ci95": [_pct(cboots_q, 0.025), _pct(cboots_q, 0.975)],
            "n_bootstrap": n_reps,
            "n_defined": len(cboots_q),
        },
        "concordance_cross_pairs": {
            "value": (c_cross / n_cross) if n_cross else None,
            "n_pairs": n_cross,
            "concordant_pair_equivalents": c_cross,
            "pooled_auroc": pooled,
        },
    }


def _cv_folds(
    y: list[int], n_pos: int, n_neg: int, seed: int
) -> tuple[str, list[list[int]]]:
    """5-fold when each test fold can carry about two of each class;
    leave-one-out otherwise. Fold assignment is stratified and seeded."""
    n = len(y)
    if n_pos >= CV_5FOLD_MIN_CLASS and n_neg >= CV_5FOLD_MIN_CLASS:
        rng = random.Random(seed)
        pos = [i for i in range(n) if y[i] == 1]
        neg = [i for i in range(n) if y[i] == 0]
        rng.shuffle(pos)
        rng.shuffle(neg)
        folds = [[] for _ in range(5)]
        for k, i in enumerate(pos):
            folds[k % 5].append(i)
        for k, i in enumerate(neg):
            folds[k % 5].append(i)
        return "5fold", folds
    return "loo", [[i] for i in range(n)]


def within_benchmark_cv(
    rows: list[dict],
    y: list[int],
    feature_names: tuple[str, ...],
    *,
    seed: int = WITHIN_BOOT_SEED,
    fitter=_fit_logit_fast,
    n_reps: int = 400,
) -> dict:
    """Cross-validated scores fit inside one benchmark's rows only.

    Honest validation needs enough kept tasks that held-out ranking is not
    dominated by single positives; under CV_5FOLD_MIN_CLASS kept, the OOF
    AUROC is reported as a suggestive small-n statistic, not a validated
    per-population model.
    """
    n = len(y)
    n_pos = sum(y)
    n_neg = n - n_pos
    method, folds = _cv_folds(y, n_pos, n_neg, seed)
    oof = [None] * n
    n_fit_single_class = 0
    for test_idx in folds:
        test_set = set(test_idx)
        train_idx = [i for i in range(n) if i not in test_set]
        Xtr, stats = design_matrix(
            [rows[i] for i in train_idx], feature_names
        )
        ytr = [y[i] for i in train_idx]
        model = fitter(Xtr, ytr)
        if not model["ok"]:
            n_fit_single_class += 1
        Xte, _ = design_matrix(
            [rows[i] for i in test_idx], feature_names, stats=stats
        )
        for i, s in zip(test_idx, predict_logit(model, Xte)):
            oof[i] = s
    boot = bootstrap_auroc(y, oof, n_reps=n_reps, seed=seed)
    too_small = n_pos < CV_5FOLD_MIN_CLASS
    return {
        "n": n,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "cv_method": method,
        "n_folds": len(folds),
        "n_folds_fit_single_class": n_fit_single_class,
        "oof_auroc": boot["value"],
        "ci95": boot["ci95"],
        "too_small_to_validate": too_small,
        "note": (
            f"kept tasks = {n_pos} (< {CV_5FOLD_MIN_CLASS}): the OOF AUROC is "
            "a suggestive small-n statistic, not a fitted and validated "
            "per-population model"
            if too_small
            else "sample size admits an honest fit-and-validate read"
        ),
    }


def run_within_benchmark(
    labels_path: Path = LABELS_PATH,
    stage1_path: Path = STAGE1_PATH,
    task_traj_path: Path = TASK_TRAJ_PATH,
    traj_trials_path: Path = TRAJ_TRIALS_PATH,
    out_json: Path = WITHIN_EVAL_PATH,
    seed: int = WITHIN_BOOT_SEED,
) -> dict:
    """Doc 54 correction: within-benchmark AUROC on survived_2_to_4.

    Population: the 1,331 reconstructed stage-1 survivors. Feature sets A,
    A+B, A+B+C+D from FEATURE_SETS. Two analyses: (1) pooled-trained LOBO
    OOF scores ranked inside each benchmark, and (2) per-benchmark
    cross-validation.
    """
    label_rows = _load_jsonl(labels_path)
    stage1_rows = _load_jsonl(stage1_path)
    task_traj_rows = _load_jsonl(task_traj_path)
    survivor_pairs = {
        (r["benchmark"], r["task_name"])
        for r in label_rows
        if r["survived_stage1"]
    }
    print(f"[within] survivors={len(survivor_pairs)}", flush=True)
    failed_stats = frontier_failed_test_stats(
        traj_trials_path, pairs=survivor_pairs
    )
    records, _coverage = build_traj_eval_records(
        label_rows, stage1_rows, task_traj_rows, failed_stats
    )
    y, rows = _label_vector(records, "survived_2_to_4")

    counts = []
    by_b = defaultdict(list)
    for i, r in enumerate(rows):
        by_b[r["benchmark"]].append(i)
    for b in sorted(by_b):
        idx = by_b[b]
        n_pos = sum(y[i] for i in idx)
        n_neg = len(idx) - n_pos
        counts.append(
            {
                "benchmark": b,
                "n_survivors": len(idx),
                "n_kept": n_pos,
                "qualifies_within_eval": (
                    n_pos >= WITHIN_MIN_POS and n_neg >= WITHIN_MIN_NEG
                ),
                "qualifies_cv": n_pos >= WITHIN_MIN_POS,
            }
        )
    counts.sort(key=lambda d: (-d["n_kept"], -d["n_survivors"], d["benchmark"]))

    pooled_trained = {}
    for set_name in WITHIN_FEATURE_SETS:
        feats = FEATURE_SETS[set_name]
        oof, _fa, _nu = _oof_predict(
            rows, y, feats, "benchmark", _fit_logit_fast
        )
        pooled_trained[set_name] = within_benchmark_eval(
            rows, y, oof, seed=seed
        )
        # In-sample pooled contrast: same statistic on scores from a model
        # that saw every task. Diagnostic for how much of the pooled AUROC
        # is within-benchmark ranking versus memorized source identity.
        Xall, _ = design_matrix(rows, feats)
        pooled_scores = predict_logit(_fit_logit_fast(Xall, y), Xall)
        pooled_trained[set_name]["in_sample_pooled_concordance"] = (
            within_group_concordance(
                y, pooled_scores, [r["benchmark"] for r in rows]
            )
        )
        print(
            f"[within] pooled-trained {set_name} "
            f"concordance={pooled_trained[set_name]['concordance_all_pairs']['value']}",
            flush=True,
        )

    per_bench_cv = {}
    for b in sorted(by_b):
        idx = by_b[b]
        n_pos = sum(y[i] for i in idx)
        if n_pos < WITHIN_MIN_POS:
            continue
        rows_b = [rows[i] for i in idx]
        y_b = [y[i] for i in idx]
        per_bench_cv[b] = {
            set_name: within_benchmark_cv(
                rows_b, y_b, FEATURE_SETS[set_name], seed=_seed_for(seed, b)
            )
            for set_name in WITHIN_FEATURE_SETS
        }
        print(
            f"[within] cv {b} n={len(idx)} kept={n_pos} "
            f"A={per_bench_cv[b]['A']['oof_auroc']}",
            flush=True,
        )

    out = {
        "protocol": PROTOCOL,
        "date": "2026-09-14",
        "question": (
            "Does the funnel footprint rank kept tasks above rejected "
            "stage-1 survivors inside one benchmark, where benchmark "
            "identity carries no information?"
        ),
        "inputs": {
            "labels": str(labels_path),
            "stage1": str(stage1_path),
            "task_traj": str(task_traj_path),
            "traj_trials": str(traj_trials_path),
        },
        "population": {
            "label": "survived_2_to_4",
            "n": len(y),
            "n_pos": sum(y),
            "n_benchmarks": len(by_b),
            "n_benchmarks_zero_kept": sum(
                1 for c in counts if c["n_kept"] == 0
            ),
            "n_benchmarks_ge_10_kept": sum(
                1 for c in counts if c["n_kept"] >= 10
            ),
            "max_kept": max(c["n_kept"] for c in counts),
        },
        "benchmark_counts": counts,
        "score_provenance": {
            "pooled_trained": (
                "leave-one-benchmark-out grouped OOF scores, identical "
                "folding and model class to evals.survived_2_to_4 in "
                "harbor_funnel_traj_eval.json; no task is scored by a "
                "model that saw it"
            ),
            "in_sample_pooled": (
                "in-sample scores from the model fit on all 1,331 "
                "survivors; diagnostic only, tasks were seen"
            ),
            "within_cv": (
                f"per-benchmark cross-validation: 5-fold when a benchmark "
                f"has >= {CV_5FOLD_MIN_CLASS} of each class, leave-one-out "
                "otherwise; stratified seeded fold deal"
            ),
        },
        "pooled_trained_within_evaluated": pooled_trained,
        "within_benchmark_cv": per_bench_cv,
        "bootstrap_seed": seed,
        "n_bootstrap": 400,
    }
    out_json.write_text(json.dumps(out, indent=1, sort_keys=False) + "\n")
    return out


def build_mapper(
    records: list[dict],
    feature_names: tuple[str, ...] = ALL_FEATURES,
    n_intervals: int = 12,
    overlap: float = 0.40,
) -> dict:
    """Mapper graph over the standardized feature matrix, solve-rate lens.

    Diagnostic only. numpy + scikit-learn (DBSCAN) per doc 45 step 5.
    Node color = survived_funnel rate. Edges = shared members.
    """
    import numpy as np
    from sklearn.cluster import DBSCAN

    rows = [r for r in records if r["frontier_solve_rate"] is not None]
    X, _stats = design_matrix(rows, feature_names)
    X = np.asarray(X, dtype=float)
    lens = np.asarray([r["frontier_solve_rate"] for r in rows], dtype=float)

    lo, hi = float(lens.min()), float(lens.max())
    span = (hi - lo) or 1.0
    length = span / (n_intervals * (1.0 - overlap) + overlap)
    step = length * (1.0 - overlap)

    nodes = []
    member_sets = []
    for i in range(n_intervals):
        a = lo + i * step
        b = a + length
        mask = (lens >= a) & (lens <= b if i == n_intervals - 1 else lens < b)
        idx = np.nonzero(mask)[0]
        if len(idx) == 0:
            continue
        sub = X[idx]
        # DBSCAN eps: median distance to k-th nearest neighbour within the
        # interval subset (k = min(5, n-1)). Diagnostic heuristic.
        if len(idx) <= 10:
            labels = np.zeros(len(idx), dtype=int)
        else:
            k = min(5, len(idx) - 1)
            d = np.sqrt(((sub[:, None, :] - sub[None, :, :]) ** 2).sum(-1))
            kth = np.sort(d, axis=1)[:, k]
            eps = float(np.median(kth)) or 1e-6
            labels = DBSCAN(eps=eps, min_samples=5).fit_predict(sub)
        for lab in sorted(set(labels)):
            members = idx[labels == lab]
            member_sets.append(set(int(m) for m in members))
            mf = [rows[m] for m in members]
            nodes.append({
                "id": len(nodes),
                "interval": i,
                "cluster": int(lab),
                "is_noise": bool(lab == -1),
                "size": int(len(members)),
                "lens_mean": float(np.mean([r["frontier_solve_rate"] for r in mf])),
                "survived_funnel_rate": float(np.mean([r["survived_funnel"] for r in mf])),
                "survived_stage1_rate": float(np.mean([r["survived_stage1"] for r in mf])),
                "dominant_benchmark": max(
                    {b: sum(1 for r in mf if r["benchmark"] == b) for b in {r["benchmark"] for r in mf}}.items(),
                    key=lambda kv: kv[1],
                )[0],
                "benchmark_counts": dict(sorted(
                    ((b, sum(1 for r in mf if r["benchmark"] == b)) for b in {r["benchmark"] for r in mf}),
                    key=lambda kv: -kv[1],
                )),
                "member_ids": [f"{r['benchmark']}|{r['task_name']}" for r in mf],
            })
    edges = []
    for i in range(len(member_sets)):
        for j in range(i + 1, len(member_sets)):
            inter = member_sets[i] & member_sets[j]
            if inter:
                edges.append({"source": i, "target": j, "shared": len(inter)})

    zero = [n for n in nodes if n["survived_funnel_rate"] == 0.0]
    return {
        "protocol": PROTOCOL,
        "diagnostic_only": True,
        "params": {
            "n_intervals": n_intervals,
            "overlap": overlap,
            "clustering": "DBSCAN(min_samples=5, eps=median k=5 NN distance per interval)",
            "lens": "frontier_solve_rate",
            "features": list(feature_names),
            "n_points": len(rows),
            "n_excluded_null_lens": len(records) - len(rows),
        },
        "nodes": nodes,
        "edges": edges,
        "n_nodes": len(nodes),
        "n_edges": len(edges),
        "n_zero_survivor_nodes": len(zero),
        "zero_survivor_dominant_benchmarks": dict(sorted(
            ((b, sum(1 for n in zero if n["dominant_benchmark"] == b))
             for b in {n["dominant_benchmark"] for n in zero}),
            key=lambda kv: -kv[1],
        )),
    }


def render_mapper_png(graph: dict, path: Path = MAPPER_PNG_PATH) -> None:
    import numpy as np
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    nodes = graph["nodes"]
    if not nodes:
        return
    # Node position: interval index (x) vs mean lens (y); jitter by cluster
    # for legibility. Size ~ sqrt(members), color = survived_funnel rate.
    xs = np.array([n["interval"] + (n["cluster"] % 5) * 0.08 for n in nodes])
    ys = np.array([n["lens_mean"] + (n["cluster"] % 3) * 0.004 for n in nodes])
    sizes = np.array([max(20.0, 2.0 * math.sqrt(n["size"])) for n in nodes])
    colors = np.array([n["survived_funnel_rate"] for n in nodes])

    fig, ax = plt.subplots(figsize=(9, 6))
    pos = {n["id"]: (x, y) for n, x, y in zip(nodes, xs, ys)}
    for e in graph["edges"]:
        (x0, y0), (x1, y1) = pos[e["source"]], pos[e["target"]]
        ax.plot([x0, x1], [y0, y1], color="0.75", lw=0.5, zorder=1)
    sc = ax.scatter(xs, ys, s=sizes, c=colors, cmap="viridis", zorder=2,
                    edgecolor="0.2", linewidth=0.4)
    fig.colorbar(sc, ax=ax, label="survived_funnel rate")
    ax.set_xlabel("lens interval (stage-1 frontier solve rate)")
    ax.set_ylabel("node mean solve rate")
    ax.set_title("Mapper over funnel footprint (diagnostic only)")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> None:
    trials = load_in_scope_trials()
    print(f"[harbor_funnel] in-scope trial rows: {len(trials)}")
    records = aggregate_stage1(trials)
    print(f"[harbor_funnel] candidates: {len(records)}")
    summary = write_stage1(records)

    pair_to_id, matched, unmatched = load_survivor_pairs()
    for rec in records:
        rec["survived_funnel"] = (rec["benchmark"], rec["task_name"]) in pair_to_id
        rec["index_task_id"] = pair_to_id.get((rec["benchmark"], rec["task_name"]))
    label_summary = write_labels(records)
    print(json.dumps(label_summary, indent=1))

    evals = {}
    for label in ("survived_stage1", "survived_funnel", "survived_2_to_4"):
        y, rows = _label_vector(records, label)
        evals[label] = eval_label(rows, y)
        print(label, json.dumps({k: v for k, v in evals[label].items() if k != "fold_aurocs"}))
    evals["solve_rate_only_survived_2_to_4"] = eval_solve_rate_only(records)
    print("solve_rate_only", evals["solve_rate_only_survived_2_to_4"])

    graph = build_mapper(records)
    MAPPER_JSON_PATH.write_text(json.dumps(graph) + "\n")
    render_mapper_png(graph)
    print(f"[mapper] nodes={graph['n_nodes']} edges={graph['n_edges']} "
          f"zero_survivor={graph['n_zero_survivor_nodes']}")

    summary["label_summary"] = label_summary
    summary["evals"] = evals
    summary["mapper"] = {k: v for k, v in graph.items() if k not in ("nodes", "edges")}
    summary["unavailable_doc40_features"] = list(UNAVAILABLE_DOC40_FEATURES)
    STAGE1_SUMMARY_PATH.write_text(json.dumps(summary, indent=1) + "\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "traj-eval":
        run_traj_eval()
    elif len(sys.argv) > 1 and sys.argv[1] == "within-eval":
        run_within_benchmark()
    else:
        main()
