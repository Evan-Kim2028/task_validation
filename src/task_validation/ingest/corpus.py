"""Provenance-tagged validity corpus. Do not merge labels into one Y."""

from __future__ import annotations

import json
from pathlib import Path


def catalog(root: Path) -> dict:
    """Index existing gold files. Missing files stay holes."""

    def n_jsonl(p: Path) -> int | None:
        if not p.is_file():
            return None
        with p.open(encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())

    def n_json(p: Path) -> int | None:
        if not p.is_file():
            return None
        return 1

    sources = [
        {
            "name": "swe-bench-2024-conservative",
            "path": "data/gold/swe_rater_targets.jsonl",
            "n": n_jsonl(root / "data/gold/swe_rater_targets.jsonl"),
            "provenance": "EXPERT_VERIFIED",
            "estimand": "issue_statement_vs_fail_to_pass_fairness",
            "protocols": ["openai_2024_conservative", "majority_invalid", "unanimous_invalid"],
            "use": "A3 + B1 + 2x2 sample Y",
        },
        {
            "name": "swe-bench-pro-public",
            "path": "data/gold/swe_pro_features.jsonl",
            "n": n_jsonl(root / "data/gold/swe_pro_features.jsonl"),
            "provenance": "PENDING_HUMAN",
            "estimand": "none_as_gt",
            "eval_only": ["openai_published_example", "june_kim_prefix"],
            "use": "Track D reconstruction; do not fit 30%",
        },
        {
            "name": "june-kim-determinacy",
            "path": "data/raw/swe-bench-pro/CLAIMS.md",
            "n": 109,
            "provenance": "EXTERNAL_EXPERT_AUDIT",
            "estimand": "hidden_determinacy_floor",
            "use": "Track D eval-only",
        },
        {
            "name": "tb-2.1-maintenance",
            "path": "data/gold/tb21_maintenance.jsonl",
            "n": n_jsonl(root / "data/gold/tb21_maintenance.jsonl"),
            "provenance": "HISTORICAL_MAINTENANCE",
            "estimand": "author_acknowledged_pre_post_defect",
            "use": "A3 natural counterfactual; only query-optimize typed misspec in public post",
        },
        {
            "name": "harbor-eval-tasks-packets",
            "path": "data/gold/eval_tasks.jsonl",
            "n": n_jsonl(root / "data/gold/eval_tasks.jsonl"),
            "provenance": "PENDING_HUMAN",
            "estimand": "material_invalidity",
            "use": "human packets deferred",
        },
        {
            "name": "harbor-interrogation-16",
            "path": "data/gold/harbor_interrogate.jsonl",
            "n": n_jsonl(root / "data/gold/harbor_interrogate.jsonl"),
            "provenance": "execution_not_human",
            "estimand": "evaluator_behavior",
            "use": "Track A machinery; not 2024 Y",
        },
        {
            "name": "task-verification-bench",
            "path": None,
            "n": 0,
            "provenance": None,
            "status": "not_loaded",
            "use": "do not ingest until public dump exists",
        },
    ]
    return {
        "merged_into_one_y": False,
        "sources": sources,
        "gate": "A3",
        "note": "Cross-benchmark transfer uses provenance as a split, not extra N.",
    }


def write_catalog(root: Path, out: Path) -> dict:
    report = catalog(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
