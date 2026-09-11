"""Three-rater SWE-bench targets. Severity axes stay labels, never predictors.

A rater flags a material problem iff underspecified>=2 or false_negative>=2
or other_major_issues>=1. That rule matches the public `problematic` field
exactly on the 2024 dump.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


def rater_material(rec: dict) -> int:
    u = float(rec.get("underspecified") or 0)
    fn = float(rec.get("false_negative") or 0)
    other = float(rec.get("other_major_issues") or 0)
    return int(u >= 2 or fn >= 2 or other >= 1)


def load_rater_table(path: Path) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            by[rec["instance_id"]].append(
                {
                    "user_id": rec.get("user_id"),
                    "underspecified": float(rec.get("underspecified") or 0),
                    "false_negative": float(rec.get("false_negative") or 0),
                    "other_major_issues": float(rec.get("other_major_issues") or 0),
                    "material": rater_material(rec),
                    "problematic": str(rec.get("problematic")).strip().lower() == "true",
                }
            )
    return by


def targets_for_task(raters: list[dict]) -> dict:
    votes = [int(r["material"]) if "material" in r else rater_material(r) for r in raters]
    n = len(votes)
    n_pos = sum(votes)
    return {
        "n_raters": n,
        "n_material_votes": n_pos,
        "openai_2024_conservative": int(n_pos >= 1),
        "majority_invalid": int(n_pos >= 2),
        "unanimous_invalid": int(n_pos == n and n >= 3),
        "votes": votes,
        "user_ids": [r.get("user_id") for r in raters],
    }


def fleiss_kappa_binary(vote_rows: list[list[int]]) -> dict:
    """Fleiss' kappa for 2 categories, equal number of raters per item."""
    n_items = len(vote_rows)
    if n_items == 0:
        return {"kappa": None, "p_bar": None, "p_e": None}
    n_raters = len(vote_rows[0])
    p_bar = 0.0
    n1 = 0
    for votes in vote_rows:
        k = sum(votes)
        n1 += k
        p_bar += (k * (k - 1) + (n_raters - k) * (n_raters - k - 1)) / (
            n_raters * (n_raters - 1)
        )
    p_bar /= n_items
    p1 = n1 / (n_items * n_raters)
    p0 = 1.0 - p1
    p_e = p0 * p0 + p1 * p1
    kappa = (p_bar - p_e) / (1.0 - p_e) if p_e < 1 else None
    return {"kappa": kappa, "p_bar": p_bar, "p_e": p_e, "p_material_vote": p1}


def pairwise_agreement(vote_rows: list[list[int]]) -> float:
    agree = 0
    pairs = 0
    for votes in vote_rows:
        for i in range(len(votes)):
            for j in range(i + 1, len(votes)):
                pairs += 1
                agree += int(votes[i] == votes[j])
    return agree / pairs if pairs else 0.0


def build_targets(rater_csv: Path, out_jsonl: Path) -> dict:
    by = load_rater_table(rater_csv)
    vote_rows = []
    counts = {
        "openai_2024_conservative": 0,
        "majority_invalid": 0,
        "unanimous_invalid": 0,
    }
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as fh:
        for tid, raters in sorted(by.items()):
            t = targets_for_task(raters)
            t["task_id"] = tid
            fh.write(json.dumps(t) + "\n")
            vote_rows.append(t["votes"][:3] if len(t["votes"]) >= 3 else t["votes"])
            for k in counts:
                counts[k] += t[k]
    n = len(by)
    summary = {
        "n_tasks": n,
        "n_annotation_rows": sum(len(v) for v in by.values()),
        "rates": {k: v / n for k, v in counts.items()},
        "counts": counts,
        "fleiss_kappa_material": fleiss_kappa_binary(vote_rows),
        "pairwise_agreement_material": pairwise_agreement(vote_rows),
        "material_rule": "underspecified>=2 or false_negative>=2 or other_major_issues>=1",
        "note": "openai_2024_conservative equals at-least-one material rater and matches filter_out on this dump.",
        "out": str(out_jsonl),
    }
    return summary
