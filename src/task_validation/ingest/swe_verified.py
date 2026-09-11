"""Ingest OpenAI SWE-bench Verified ensemble annotations into EvalQA-Gold."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from task_validation.schema import EvidenceVector, GoldRow, material_invalid_from_swe_filter

ENSEMBLE_CSV_NAME = "ensembled_annotations_public.csv"
SOURCE_URL = "https://cdn.openai.com/introducing-swe-bench-verified/swe-bench-annotation-results.zip"


def _f(value: str) -> float:
    return float(value) if value not in ("", None) else 0.0


def _b(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def load_ensemble_csv(path: Path) -> list[GoldRow]:
    rows: list[GoldRow] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for rec in reader:
            filter_out = _b(rec["filter_out"])
            underspec = _f(rec["underspecified"])
            false_neg = _f(rec["false_negative"])
            other = _f(rec["other_major_issues"])
            label, severity = material_invalid_from_swe_filter(
                filter_out=filter_out,
                underspecified=underspec,
                false_negative=false_neg,
                other_major_issues=other,
            )
            repo = rec["instance_id"].split("__")[0] if "__" in rec["instance_id"] else None
            n_raters = 3
            rows.append(
                GoldRow(
                    task_id=rec["instance_id"],
                    benchmark="swe-bench",
                    benchmark_version="test-2024-annotations",
                    provenance="EXPERT_VERIFIED",
                    language="python",
                    repository=repo,
                    domain="software-engineering",
                    human_validity_label=label,
                    human_label_provenance="EXPERT_VERIFIED",
                    human_severity=severity,
                    n_raters=n_raters,
                    difficulty=rec.get("difficulty") or None,
                    evidence=EvidenceVector(
                        extra={
                            "underspecified_notes": rec.get("underspecified_notes") or "",
                            "false_negative_notes": rec.get("false_negative_notes") or "",
                            "other_notes": rec.get("other_notes") or "",
                            "source_url": SOURCE_URL,
                        }
                    ),
                    artifacts={"instance_id": rec["instance_id"]},
                )
            )
    return rows


def write_jsonl(rows: list[GoldRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")


def summarize(rows: list[GoldRow]) -> dict:
    n = len(rows)
    n_invalid = sum(1 for r in rows if r.human_validity_label == "invalid")
    return {
        "n": n,
        "n_invalid": n_invalid,
        "n_valid": sum(1 for r in rows if r.human_validity_label == "valid"),
        "invalid_rate": (n_invalid / n) if n else None,
        "benchmark": "swe-bench",
        "label_protocol": "openai-swe-bench-verified-2024-conservative",
        "source_url": SOURCE_URL,
    }
