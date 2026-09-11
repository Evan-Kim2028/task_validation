from task_validation.evidence.spec_atoms import extract_atoms, spec_from_record
from task_validation.evidence.vev import vev_from_spec


def test_ungrounded_error_and_literal():
    rec = {
        "problem_statement": "Fix the parser so empty input does not crash.",
        "test_patch": 'def test_get_annotation():\n    with pytest.raises(ValueError, match="secret"):\n        get_annotation()\n',
        "FAIL_TO_PASS": '["test_get_annotation"]',
    }
    spec = spec_from_record(rec)
    assert spec["n_enforced"] > 0
    assert spec["spec_gap"] > 0
    assert any("get_annotation" in x or "valueerror" in x or "secret" in x for x in spec["ungrounded_sample"])
    vev = vev_from_spec("t1", spec)
    assert vev.primitives["specification_sufficiency"].value == spec["spec_gap"]
    assert 0 <= vev.untrained_risk() <= 1


def test_well_aligned_prompt_has_small_gap():
    rec = {
        "problem_statement": "get_annotation must raise ValueError on empty input.",
        "test_patch": "def test_get_annotation():\n    with pytest.raises(ValueError):\n        get_annotation()\n",
        "FAIL_TO_PASS": '["test_get_annotation"]',
    }
    spec = spec_from_record(rec)
    assert spec["spec_gap"] < spec_from_record(
        {
            "problem_statement": "Fix it.",
            "test_patch": rec["test_patch"],
            "FAIL_TO_PASS": rec["FAIL_TO_PASS"],
        }
    )["spec_gap"]
