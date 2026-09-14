"""Tiny-fixture tests for doc 59 conditional-taste helpers
(conditional_taste.py)."""

import json
import math

import pytest

from task_validation.evidence.conditional_taste import (
    build_swe_taste_labels,
    design_matrix,
    parse_verified500_ids,
    risk_tail,
    validity_membership_2x2,
    within_group_eval,
)
from task_validation.evidence.irt import auroc


# --- Verified-500 filename parsing -----------------------------------------


def _touch(d, name):
    (d / name).write_text("{}")


def test_parse_verified500_ids_basic(tmp_path):
    _touch(tmp_path, "astropy__astropy-12907__e19bf083e1.json")
    _touch(tmp_path, "django__django-12325__a1b2c3d4e5.json")
    _touch(tmp_path, "sympy__sympy-11400__00ff00ff00.json")
    ids = parse_verified500_ids(tmp_path)
    assert ids == [
        "astropy__astropy-12907",
        "django__django-12325",
        "sympy__sympy-11400",
    ]


def test_parse_verified500_ids_splits_on_last_separator(tmp_path):
    # Instance ids contain "__" themselves; the split must be the final
    # one before a hex hash.
    _touch(tmp_path, "sphinx-doc__sphinx-8713__0123456789.json")
    ids = parse_verified500_ids(tmp_path)
    assert ids == ["sphinx-doc__sphinx-8713"]


def test_parse_verified500_ids_ignores_non_json(tmp_path):
    _touch(tmp_path, "astropy__astropy-12907__e19bf083e1.json")
    (tmp_path / "README.txt").write_text("not an audit")
    ids = parse_verified500_ids(tmp_path)
    assert ids == ["astropy__astropy-12907"]


def test_parse_verified500_ids_malformed_raises(tmp_path):
    _touch(tmp_path, "astropy__astropy-12907__e19bf083e1.json")
    _touch(tmp_path, "no_separator.json")
    with pytest.raises(ValueError):
        parse_verified500_ids(tmp_path)


def test_parse_verified500_ids_non_hex_hash_raises(tmp_path):
    _touch(tmp_path, "astropy__astropy-12907__nothexZZ.json")
    with pytest.raises(ValueError):
        parse_verified500_ids(tmp_path)


def test_parse_verified500_ids_dedupes_and_sorts(tmp_path):
    _touch(tmp_path, "b__b-2__aaaaaa11.json")
    _touch(tmp_path, "a__a-1__bbbbbb22.json")
    _touch(tmp_path, "a__a-1__cccccc33.json")  # same id, different audit hash
    ids = parse_verified500_ids(tmp_path)
    assert ids == ["a__a-1", "b__b-2"]


def test_parse_verified500_ids_real_audit_dir():
    from task_validation.evidence.conditional_taste import VERIFIED500_AUDIT_DIR

    if not VERIFIED500_AUDIT_DIR.is_dir():
        pytest.skip("static_audits not present")
    ids = parse_verified500_ids(VERIFIED500_AUDIT_DIR)
    assert len(ids) == 500
    assert len(set(ids)) == 500
    assert all("__" in i for i in ids)


# --- taste_kept conditioning ------------------------------------------------


def test_taste_kept_defined_only_on_majority_valid():
    raters = {
        "a__a-1": {"task_id": "a__a-1", "n_raters": 3, "n_material_votes": 0,
                    "openai_2024_conservative": 0, "majority_invalid": 0,
                    "unanimous_invalid": 0, "votes": [0, 0, 0]},
        "b__b-2": {"task_id": "b__b-2", "n_raters": 3, "n_material_votes": 1,
                    "openai_2024_conservative": 0, "majority_invalid": 1,
                    "unanimous_invalid": 0, "votes": [0, 1, 1]},
    }
    repos = {"a__a-1": "a", "b__b-2": "b"}
    rows = {r["task_id"]: r for r in build_swe_taste_labels(raters, repos, {"a__a-1", "b__b-2"})}
    assert rows["a__a-1"]["taste_kept"]["value"] == 1
    # Invalid task cannot be "kept": membership must not leak through.
    assert rows["b__b-2"]["taste_kept"]["value"] is None
    assert rows["b__b-2"]["in_verified500"]["value"] is True
    for r in rows.values():
        for lab in (
            r["validity"]["majority_invalid"],
            r["in_verified500"],
            r["taste_kept"],
        ):
            assert lab["protocol"]
            assert lab["grade"] == "A"


def test_validity_membership_2x2_counts():
    raters = {
        f"t{i}": {"task_id": f"t{i}", "majority_invalid": 1 if i < 2 else 0,
                   "openai_2024_conservative": 1 if i < 2 else 0,
                   "unanimous_invalid": 0}
        for i in range(4)
    }
    repos = {f"t{i}": "g" for i in range(4)}
    rows = build_swe_taste_labels(raters, repos, {"t2", "t3"})
    tab = validity_membership_2x2(rows)["majority_invalid"]
    assert tab["valid_kept"] == 2
    assert tab["valid_not_kept"] == 0
    assert tab["invalid_kept"] == 0
    assert tab["invalid_not_kept"] == 2


# --- within-group concordance ------------------------------------------------


def test_within_group_eval_removes_group_identity_credit():
    # g1's positives tie its negative (within = 0.5); g2 has only
    # negatives at a low score, so every cross pair is concordant.
    # Pooled AUROC (5/6) gets credit that no within-group pair earns.
    y =      [1,   1,   0,   0,   0]
    scores = [0.9, 0.9, 0.9, 0.1, 0.1]
    groups = ["g1", "g1", "g1", "g2", "g2"]
    out = within_group_eval(y, scores, groups, min_pos=1, min_neg=1, n_reps=50)
    assert out["concordance_all_pairs"]["value"] == pytest.approx(0.5)
    assert out["concordance_all_pairs"]["n_pairs"] == 2
    assert out["concordance_cross_pairs"]["value"] == pytest.approx(1.0)
    assert out["concordance_cross_pairs"]["n_pairs"] == 4
    assert auroc(y, scores) == pytest.approx(5 / 6)
    # Exact decomposition: pooled pairs = within + cross contributions.
    assert (0.5 * 2 + 1.0 * 4) / 6 == pytest.approx(5 / 6)


def test_within_group_eval_exact_concordance():
    y =      [1,   0,   0,   1,   0,   1,   0]
    scores = [0.9, 0.5, 0.1, 0.2, 0.8, 0.5, 0.5]
    groups = ["g1", "g1", "g1", "g2", "g2", "g3", "g3"]
    out = within_group_eval(y, scores, groups, min_pos=1, min_neg=1, n_reps=50)
    c = out["concordance_all_pairs"]
    assert c["n_pairs"] == 4
    assert c["concordant_pair_equivalents"] == pytest.approx(2.5)
    assert c["value"] == pytest.approx(0.625)
    # Pooled AUROC differs (7/12): group identity earns credit there.
    assert auroc(y, scores) == pytest.approx(7 / 12)


def test_within_group_eval_positives_weighted_mean():
    # Two groups: g1 (AUROC 1.0, 2 positives), g2 (AUROC 0.0, 1 positive).
    y =      [1, 1, 0, 0, 1, 0]
    scores = [0.9, 0.8, 0.1, 0.2, 0.1, 0.9]
    groups = ["g1", "g1", "g1", "g1", "g2", "g2"]
    out = within_group_eval(y, scores, groups, min_pos=1, min_neg=1, n_reps=50)
    w = out["positives_weighted_mean"]["value"]
    assert w == pytest.approx((1.0 * 2 + 0.0 * 1) / 3)


def test_within_group_eval_qualification_thresholds():
    # g2 fails min_pos=2 (only one positive) and is excluded from the
    # positives-weighted mean and the qualified concordance.
    y =      [1, 1, 0, 0, 1, 0, 0]
    scores = [0.9, 0.8, 0.1, 0.2, 0.5, 0.4, 0.6]
    groups = ["g1", "g1", "g1", "g1", "g2", "g2", "g2"]
    out = within_group_eval(y, scores, groups, min_pos=2, min_neg=1, n_reps=50)
    assert out["n_groups_qualified"] == 1
    per = {g["group"]: g for g in out["per_group"]}
    assert per["g1"]["qualified"] is True
    assert per["g2"]["qualified"] is False
    assert per["g2"]["ci95"] is None
    # Qualified-pair concordance uses only g1 pairs (2 pos x 2 neg = 4).
    assert out["concordance_qualified_pairs"]["n_pairs"] == 4
    assert out["concordance_all_pairs"]["n_pairs"] == 4 + 1 * 2


# --- risk tail ----------------------------------------------------------------


def test_risk_tail_top_score_kept_rate():
    y =      [1, 1, 1, 1, 0, 0, 0, 0]
    scores = [0.9, 0.8, 0.7, 0.6, 0.4, 0.3, 0.2, 0.1]
    tail = risk_tail(y, scores, fracs=(0.5,))
    assert tail[0]["n_retained"] == 4
    assert tail[0]["n_kept"] == 4
    assert tail[0]["kept_rate"] == pytest.approx(1.0)
    assert tail[-1]["retain_frac"] == 1.0
    assert tail[-1]["kept_rate"] == pytest.approx(0.5)


# --- design matrix --------------------------------------------------------------


def test_design_matrix_log1p_parameterized():
    rows = [
        {"features": {"x": 0.0, "b": 1.0}},
        {"features": {"x": 8.0, "b": 1.0}},
        {"features": {"x": 24.0, "b": 0.0}},
        {"features": {"x": None, "b": 1.0}},
    ]
    X, stats = design_matrix(rows, ("x", "b"), log1p_names=frozenset({"x"}))
    # log1p applied before imputation; the stored "median" slot holds the
    # mean of present values, matching footprint.design_matrix.
    med = stats["median"][0]
    assert med == pytest.approx((math.log1p(0.0) + math.log1p(8.0) + math.log1p(24.0)) / 3)
    assert stats["use_miss"] == [True, False]  # 25% missing on x
    assert len(X[0]) == 3  # x, b, x-missing indicator
