from task_validation.evidence.swe_artifacts import (
    CHEAP_FEATURE_NAMES,
    FORBIDDEN_PREDICTORS,
    swe_cheap_features,
)
from task_validation.model.fit import assert_no_leakage


def test_frozen_list_has_no_human_severity():
    assert not (set(CHEAP_FEATURE_NAMES) & FORBIDDEN_PREDICTORS)
    assert_no_leakage(list(CHEAP_FEATURE_NAMES))


def test_wide_test_signal_on_unmentioned_identifier():
    rec = {
        "problem_statement": "The parser crashes on empty input.",
        "patch": "diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-x\n+y\n",
        "test_patch": "diff --git a/test_a.py b/test_a.py\n@@ -0,0 +1,3 @@\n+def test_get_annotation():\n+    assert get_annotation() == 'secret'\n",
        "FAIL_TO_PASS": '["test_get_annotation"]',
        "PASS_TO_PASS": "[]",
        "hints_text": "",
    }
    f = swe_cheap_features(rec)
    assert f["n_fail_to_pass"] == 1.0
    assert f["test_has_exact_string_literal"] == 1.0
    assert f["test_only_id_frac"] > 0.0
    assert f["f2p_in_statement_frac"] == 0.0


def test_reproduction_and_traceback_flags():
    rec = {
        "problem_statement": "Traceback:\nError: boom\nTo reproduce: run foo. See https://example.com",
        "patch": "",
        "test_patch": "",
        "FAIL_TO_PASS": "[]",
        "PASS_TO_PASS": "[]",
        "hints_text": "hint",
    }
    f = swe_cheap_features(rec)
    assert f["has_traceback"] == 1.0
    assert f["has_http_url"] == 1.0
    assert f["has_reproduction_hint"] == 1.0
    assert f["hints_chars"] == 4.0
