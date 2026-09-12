"""Link existing public human/maintenance labels. Do not merge provenances.

SWE-bench 2024 labels are issue-vs-F2P fairness, not evaluator discrimination.
TVB is not loaded. TB maintenance is not loaded. Harbor packets stay pending.
"""

from __future__ import annotations

import json
from pathlib import Path

SWE_PROTOCOLS = (
    {
        "protocol": "openai_2024_conservative",
        "y_key": "openai_2024_conservative",
        "confidence": "multi_rater_at_least_one",
        "rule": "any of 3 raters material",
    },
    {
        "protocol": "majority_invalid",
        "y_key": "majority_invalid",
        "confidence": "multi_rater_majority",
        "rule": "at least 2 of 3 raters material",
    },
    {
        "protocol": "unanimous_invalid",
        "y_key": "unanimous_invalid",
        "confidence": "multi_rater_unanimous",
        "rule": "all 3 raters material",
    },
)


def _label(bit: int) -> str:
    return "INVALID" if int(bit) else "VALID"


def rows_from_swe_targets(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            for proto in SWE_PROTOCOLS:
                y = rec.get(proto["y_key"])
                if y is None:
                    continue
                rows.append(
                    {
                        "task_id": rec["task_id"],
                        "benchmark": "swe-bench",
                        "benchmark_version": "verified-ensemble-2024",
                        "protocol": proto["protocol"],
                        "label": _label(int(y)),
                        "ambiguous": False,
                        "provenance": "EXPERT_VERIFIED",
                        "confidence": proto["confidence"],
                        "n_raters": rec.get("n_raters"),
                        "n_material_votes": rec.get("n_material_votes"),
                        "estimand": "issue_statement_vs_fail_to_pass_fairness",
                        "not_estimand": "evaluator_discrimination",
                        "verified_membership_is_not_gt": True,
                        "rule": proto["rule"],
                        "source_file": str(path),
                    }
                )
    return rows


def rows_from_harbor_gold(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            rows.append(
                {
                    "task_id": rec["task_id"],
                    "benchmark": rec.get("benchmark") or "eval_tasks",
                    "benchmark_version": rec.get("benchmark_version") or "local",
                    "protocol": "pending_human_packet",
                    "label": "AMBIGUOUS"
                    if rec.get("human_validity_label") == "ambiguous"
                    else "PENDING",
                    "ambiguous": rec.get("human_validity_label") in {"ambiguous", "pending", None},
                    "provenance": rec.get("human_label_provenance") or "PENDING_HUMAN",
                    "confidence": "unlabeled",
                    "n_raters": rec.get("n_raters") or 0,
                    "estimand": "material_invalidity",
                    "not_estimand": None,
                    "source_file": str(path),
                    "note": "Do not fill with a model. Human packets are deferred.",
                }
            )
    return rows


def holes() -> list[dict]:
    return [
        {
            "task_id": None,
            "benchmark": "task-verification-bench",
            "protocol": "author_acknowledged_fix",
            "label": None,
            "n": 0,
            "status": "not_loaded",
            "reason": "OpenReview QdDcI0Ftvo did not resolve to a public dataset",
        },
        {
            "task_id": None,
            "benchmark": "terminal-bench",
            "protocol": "historical_maintenance",
            "label": None,
            "n": 0,
            "status": "not_loaded",
            "reason": "TB 2.1 maintenance IDs not ingested yet",
        },
    ]


def write_linkage(
    *,
    swe_targets: Path,
    harbor_gold: Path | None,
    out: Path,
) -> dict:
    rows = rows_from_swe_targets(swe_targets)
    if harbor_gold:
        rows.extend(rows_from_harbor_gold(harbor_gold))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    by_proto: dict[str, int] = {}
    by_label: dict[str, int] = {}
    for row in rows:
        by_proto[row.get("protocol") or ""] = by_proto.get(row.get("protocol") or "", 0) + 1
        by_label[row.get("label") or ""] = by_label.get(row.get("label") or "", 0) + 1
    summary = {
        "n_rows": len(rows),
        "n_protocols": by_proto,
        "n_labels": by_label,
        "holes": holes(),
        "merged_provenances": False,
        "swe_verified_membership_used_as_gt": False,
        "out": str(out),
    }
    Path(str(out).replace(".jsonl", ".summary.json")).write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary
