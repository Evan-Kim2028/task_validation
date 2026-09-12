"""Fixture tests for the spec auditor. No network."""

from __future__ import annotations

from task_validation.evidence.llm_spec_audit import (
    COMBINATION_RULE,
    FROZEN_PREDICATES,
    SAMPLE_SEED,
    auroc,
    auditor_score,
    build_prompt,
    cohens_kappa,
    combination_scores,
    cost_usd,
    draw_sample,
    evaluate_predicates,
    instance_for_prompt,
    join_row,
    model_material,
    parse_response,
    pick_model,
    project_cost,
    prompt_leaks_labels,
    retain_tail,
    score_parsed,
    seed_to_int,
    truncate_packet,
)


ISSUE = "Calling foo() with an empty list should return []."
TEST_PATCH = (
    "diff --git a/tests/test_foo.py b/tests/test_foo.py\n"
    "@@\n"
    "+def test_foo_empty():\n"
    "+    assert foo([]) == []\n"
)
GOLD = (
    "diff --git a/foo.py b/foo.py\n"
    "@@\n"
    "+def foo(xs):\n"
    "+    return list(xs)\n"
)


def _rec(**extra):
    rec = {
        "task_id": "demo__demo-1",
        "instance_id": "demo__demo-1",
        "problem_statement": ISSUE,
        "patch": GOLD,
        "test_patch": TEST_PATCH,
        "FAIL_TO_PASS": '["tests/test_foo.py::test_foo_empty"]',
        "repo": "demo/demo",
        "base_commit": "abc123",
    }
    rec.update(extra)
    return rec


def test_instance_for_prompt_drops_labels():
    rec = _rec(
        human_validity_label="invalid",
        p_logistic=0.91,
        y=1,
        votes=[1, 1, 0],
        openai_2024_conservative=1,
        majority_invalid=1,
        human_severity={"underspecified": 3, "false_negative": 2},
    )
    inst = instance_for_prompt(rec)
    assert "human_validity_label" not in inst
    assert "p_logistic" not in inst
    assert "votes" not in inst
    assert "human_severity" not in inst
    assert inst["problem_statement"] == ISSUE
    assert inst["patch"] == GOLD


def test_build_prompt_omits_gold_labels():
    rec = _rec(
        human_validity_label="invalid",
        p_logistic=0.91,
        openai_2024_conservative=1,
        majority_invalid=1,
        p_i=0.0,
    )
    built = build_prompt(rec)
    user = built["messages"][1]["content"]
    assert prompt_leaks_labels(user) == []
    assert "0.91" not in user
    assert ISSUE in user
    assert "test_foo_empty" in user
    assert GOLD in user
    assert built["messages"][0]["role"] == "system"


def test_truncate_prioritizes_issue_and_tests():
    rec = _rec(
        problem_statement="ISSUE_BODY " * 50,
        test_patch="TEST_BODY " * 50,
        patch="GOLD_BODY " * 5000,
    )
    packet = truncate_packet(rec, budget_tokens=400)
    assert "ISSUE_BODY" in packet["issue"]
    assert packet["truncated"]["gold_patch"] is True
    assert packet["truncated"]["issue"] is False


def test_parse_fenced_json_and_aliases():
    raw = """here is the audit
```json
{
  "underspecified": 2,
  "false_negative": "1",
  "other_major_issues": 1,
  "other_reason": "hidden path",
  "confidence": 80,
  "rationale": "The issue omits the required error type. Tests pin a private helper name.",
  "p_invalid": 0.7
}
```
"""
    parsed = parse_response(raw)
    assert parsed["underspecified"] == 2
    assert parsed["false_negative"] == 1
    assert parsed["other_major_issue"] == 1
    assert parsed["confidence"] == 0.8
    assert parsed["p_invalid"] == 0.7
    scored = score_parsed(parsed)
    assert scored["s"] == auditor_score(2, 1, 1)
    assert scored["s"] == 2.25
    assert scored["model_material"] == 1


def test_parse_chat_response_dict():
    raw = {
        "choices": [
            {
                "message": {
                    "content": '{"underspecified": 0, "false_negative": 0, '
                    '"other_major_issue": 0, "other_reason": "", '
                    '"confidence": 0.4, "rationale": "Clear issue. Tests match.", '
                    '"p_invalid": 0.1}'
                }
            }
        ]
    }
    parsed = parse_response(raw)
    assert parsed["underspecified"] == 0
    assert model_material(parsed) == 0
    assert score_parsed(parsed)["s"] == 0.0


def test_join_does_not_change_score():
    audit = score_parsed(
        {
            "underspecified": 3,
            "false_negative": 1,
            "other_major_issue": 0,
            "other_reason": "",
            "confidence": 0.5,
            "rationale": "a. b.",
            "p_invalid": 0.9,
        }
    )
    audit["task_id"] = "demo__demo-1"
    joined = join_row(
        audit,
        compact={
            "human_validity_label": "invalid",
            "human_severity": {
                "underspecified": 2.0,
                "false_negative": 0.0,
                "other_major_issues": 0.0,
            },
        },
        raters={
            "openai_2024_conservative": 1,
            "majority_invalid": 0,
            "unanimous_invalid": 0,
            "votes": [1, 0, 0],
            "n_raters": 3,
            "n_material_votes": 1,
        },
        irt_item={"p_i": 0.25},
        oof={"p_logistic": 0.4},
    )
    assert joined["s"] == 3.0
    assert joined["p_invalid"] == 0.9
    assert joined["human_validity_label"] == "invalid"
    assert joined["openai_2024_conservative"] == 1
    assert joined["p_i"] == 0.25
    assert joined["p_logistic"] == 0.4
    assert joined["votes"] == [1, 0, 0]


def test_auroc_retain_kappa_combination():
    y = [1, 1, 1, 0, 0, 0]
    s = [3.0, 2.0, 2.25, 0.0, 0.0, 1.0]
    assert auroc(y, s) > 0.9
    tail = retain_tail(y, s, fracs=(0.5,))
    assert tail[0]["n_retained"] == 3
    assert tail[0]["residual_invalid"] == 0.0
    kappa = cohens_kappa([1, 1, 0, 0], [1, 0, 0, 0])
    assert 0.0 < kappa < 1.0
    combo = combination_scores([0.0, 2.0, 4.0], [0.0, 0.5, 1.0])
    assert combo[0] < combo[1] < combo[2]


def test_frozen_predicates_pass_and_fail():
    assert "AUROC(s, conservative)" in FROZEN_PREDICATES["F1"]
    assert "z(s)" in COMBINATION_RULE and "1-p_i" in COMBINATION_RULE
    good = evaluate_predicates(
        {"value": 0.80, "ci95": [0.72, 0.88]},
        0.45,
        0.15,
    )
    assert good["all_pass"] is True
    bad = evaluate_predicates(
        {"value": 0.74, "ci95": [0.68, 0.80]},
        0.20,
        0.40,
    )
    assert bad["F1"]["pass"] is False
    assert bad["F2"]["pass"] is False
    assert bad["F3"]["pass"] is False
    assert bad["all_pass"] is False


def test_draw_sample_deterministic_from_sorted_ids():
    ids = [f"z__{i}" for i in range(10)] + [f"a__{i}" for i in range(10)]
    a = draw_sample(ids, 5, SAMPLE_SEED)
    b = draw_sample(list(reversed(ids)), 5, SAMPLE_SEED)
    assert a == b
    assert len(set(a)) == 5
    assert seed_to_int(SAMPLE_SEED) == seed_to_int("swe-llm-audit-v0")
    assert seed_to_int(SAMPLE_SEED) != seed_to_int("other")


def test_pick_model_prefers_grok_46():
    catalog = [
        {
            "id": "openai/gpt-4.1-nano",
            "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
            "context_length": 200000,
        },
        {
            "id": "x-ai/grok-4.6",
            "pricing": {"prompt": "0.000002", "completion": "0.000006"},
            "context_length": 500000,
            "name": "Grok 4.6",
        },
        {
            "id": "x-ai/grok-4-fast",
            "pricing": {"prompt": "0.0000002", "completion": "0.0000005"},
            "context_length": 2000000,
        },
    ]
    picked = pick_model(catalog)
    assert picked["id"] == "x-ai/grok-4.6"
    assert picked["prompt_price"] == 0.000002
    fast_only = [m for m in catalog if m["id"] != "x-ai/grok-4.6"]
    assert pick_model(fast_only)["id"] == "x-ai/grok-4-fast"
    cheap = pick_model([catalog[0]])
    assert cheap["id"] == "openai/gpt-4.1-nano"


def test_project_cost_units():
    proj = project_cost([1000, 1000], 0.000002, 0.000006, completion_tokens=100)
    assert abs(proj["est_usd"] - (2000 * 0.000002 + 200 * 0.000006)) < 1e-12
    assert abs(cost_usd(1000, 500, 0.000002, 0.000006) - 0.005) < 1e-12
