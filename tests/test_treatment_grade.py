from task_validation.evidence.treatment_grade import (
    analyze_pilot,
    assay_rates,
    grade_trial,
)
from task_validation.model.sample_2x2 import sample_2x2
from task_validation.ingest.tb_maintenance import TB21_CHANGED, rows as tb_rows


def test_remove_required_is_heuristic_not_a_negative_control():
    g = grade_trial({"family": "remove_required", "intended": "reject", "reward": 0.0})
    assert g["label_grade"] == "C"
    assert g["intended_uncertain"] is True
    assert g["label_justified"] is False


def test_nop_and_reference_are_ab():
    assert grade_trial({"family": "nop", "intended": "reject"})["label_grade"] == "A"
    assert grade_trial({"family": "reference", "intended": "accept"})["label_grade"] == "B"
    assert grade_trial({"family": "revert_gold", "intended": "reject"})["label_grade"] == "B"


def test_ab_rates_drop_heuristic_false_accept():
    trials = [
        grade_trial({"family": "reference", "intended": "accept", "reward": 1.0, "accepted": True}),
        grade_trial({"family": "preserve", "intended": "accept", "reward": 1.0, "accepted": True}),
        grade_trial({"family": "nop", "intended": "reject", "reward": 0.0, "accepted": False}),
        grade_trial({"family": "remove_required", "intended": "reject", "reward": 1.0, "accepted": True}),
        grade_trial({"family": "revert_gold", "intended": "reject", "reward": 0.0, "accepted": False}),
    ]
    all_in = assay_rates(trials, min_grade="C")
    ab = assay_rates(trials, min_grade="B")
    assert abs(all_in["false_accept"] - (1 / 3)) < 1e-9
    assert ab["false_accept"] == 0.0
    assert ab["incorrect_reject"] == 1.0


def test_analyze_flags_remove_required_false_accept():
    rec = {
        "task_id": "x",
        "trials": [
            {"family": "reference", "intended": "accept", "reward": 1.0, "accepted": True},
            {"family": "remove_required", "intended": "reject", "reward": 1.0, "accepted": True},
            {"family": "nop", "intended": "reject", "reward": 0.0, "accepted": False},
        ],
    }
    report = analyze_pilot([rec])
    assert report["n_remove_required_false_accept"] == 1
    assert report["mean_rates_ab_only"]["false_accept"] == 0.0


def test_tb21_has_28_and_named_misspec():
    assert len(TB21_CHANGED) == 28
    recs = tb_rows()
    assert len(recs) == 28
    q = [r for r in recs if r["task_id"] == "query-optimize"][0]
    assert q["named_misspec"]
    assert q["provenance"] == "HISTORICAL_MAINTENANCE"


def test_sample_2x2_four_cells(tmp_path):
    import json

    p = tmp_path / "oof.jsonl"
    # 8 valid low, 8 valid high, 8 invalid low, 8 invalid high
    rows = []
    i = 0
    for y, ps in [(0, [0.1, 0.2, 0.15, 0.12, 0.11, 0.18, 0.19, 0.14]), (1, [0.8, 0.9, 0.7, 0.85, 0.6, 0.95, 0.75, 0.88])]:
        for p_ in ps:
            i += 1
            rows.append({"task_id": f"repo{i}__x-{i}", "repository": f"repo{i}", "y": y, "p_logistic": p_})
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = sample_2x2(p, n_per_cell=2, extra=1, salt="t")
    assert out["executed"] is False
    assert len(out["run_ids"]) == 8
    for cell, items in out["cells"].items():
        assert len(items) == 3
        ys = {it["y"] for it in items}
        assert len(ys) == 1
