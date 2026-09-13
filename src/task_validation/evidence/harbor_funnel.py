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
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from task_validation.evidence.footprint import (
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


def eval_label(
    rows: list[dict],
    y: list[int],
    feature_names: tuple[str, ...] = EXEC_FEATURES,
) -> dict:
    """Leave-one-benchmark-out logistic AUROC plus naive pooled contrast.

    Same model class as doc 40: median imputation, missingness indicators,
    standardized design matrix, L2 logit (fit_logit in footprint.py).
    """
    by_bench = defaultdict(list)
    for i, r in enumerate(rows):
        by_bench[r["benchmark"]].append(i)

    oof = [None] * len(rows)
    fold_aurocs = {}
    n_undefined = 0
    for bench in sorted(by_bench):
        test_set = set(by_bench[bench])
        test_idx = by_bench[bench]
        train_idx = [i for i in range(len(rows)) if i not in test_set]
        train_rows = [rows[i] for i in train_idx]
        test_rows = [rows[i] for i in test_idx]
        ytr = [y[i] for i in train_idx]
        yte = [y[i] for i in test_idx]
        Xtr, stats = design_matrix(train_rows, feature_names)
        Xte, _ = design_matrix(test_rows, feature_names, stats=stats)
        model = fit_logit(Xtr, ytr)
        scores = predict_logit(model, Xte)
        for i, s in zip(test_idx, scores):
            oof[i] = s
        a = auroc(yte, scores)
        if a is None:
            n_undefined += 1
        else:
            fold_aurocs[bench] = a

    boot = bootstrap_auroc(y, [s for s in oof], n_reps=400, seed=20260913)
    # Naive pooled: fit and score on all rows.
    Xall, _ = design_matrix(rows, feature_names)
    pooled_model = fit_logit(Xall, y)
    pooled_scores = predict_logit(pooled_model, Xall)
    pooled = auroc(y, pooled_scores)
    return {
        "n": len(y),
        "n_pos": sum(y),
        "lobo_auroc": boot["value"],
        "lobo_ci95": boot["ci95"],
        "pooled_auroc": pooled,
        "n_folds": len(by_bench),
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
    main()
