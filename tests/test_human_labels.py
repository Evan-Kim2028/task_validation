import json
from pathlib import Path

from task_validation.ingest.human_labels import rows_from_swe_targets, write_linkage


def test_swe_protocols_not_merged(tmp_path: Path):
    src = tmp_path / "targets.jsonl"
    src.write_text(
        json.dumps(
            {
                "task_id": "repo__1",
                "n_raters": 3,
                "n_material_votes": 1,
                "openai_2024_conservative": 1,
                "majority_invalid": 0,
                "unanimous_invalid": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rows = rows_from_swe_targets(src)
    assert len(rows) == 3
    by = {r["protocol"]: r["label"] for r in rows}
    assert by["openai_2024_conservative"] == "INVALID"
    assert by["majority_invalid"] == "VALID"
    assert by["unanimous_invalid"] == "VALID"
    assert all(r["not_estimand"] == "evaluator_discrimination" for r in rows)
    assert all(r["verified_membership_is_not_gt"] for r in rows)


def test_write_linkage_summary(tmp_path: Path):
    src = tmp_path / "targets.jsonl"
    src.write_text(
        json.dumps(
            {
                "task_id": "repo__1",
                "n_raters": 3,
                "n_material_votes": 0,
                "openai_2024_conservative": 0,
                "majority_invalid": 0,
                "unanimous_invalid": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "human_labels.jsonl"
    summary = write_linkage(swe_targets=src, harbor_gold=None, out=out)
    assert summary["merged_provenances"] is False
    assert summary["swe_verified_membership_used_as_gt"] is False
    assert summary["n_rows"] == 3
    assert any(h["status"] == "not_loaded" for h in summary["holes"])
