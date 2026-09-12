"""Fixture tests for judge-calibrated bounds. No network."""

from __future__ import annotations

import random

from task_validation.sampling.estimators import clopper_pearson_upper
from task_validation.sampling.ppi import ppi_mean_ucb, poststrat_exact_ucb
from task_validation.sampling.judge_bound import (
    FROZEN_PREDICATES,
    allocate_judge_strata,
    calibrated_prevalence_ucb,
    clopper_pearson_lower,
    evaluate_predicates,
    ppi_with_judge,
    rogan_gladen,
    rogan_gladen_point,
    simulate_cell,
    stratified_by_judge_ucb,
)


def test_frozen_predicates_written():
    assert "1,699" in FROZEN_PREDICATES["J1"] or "1699" in FROZEN_PREDICATES["J1"]
    assert "0.80" in FROZEN_PREDICATES["J1"]
    assert "p=0.02" in FROZEN_PREDICATES["J2"] and "m=100" in FROZEN_PREDICATES["J2"]
    assert "2x" in FROZEN_PREDICATES["J3"]
    assert FROZEN_PREDICATES["J1"].startswith("judge AUROC")


def test_rogan_gladen_point_identity():
    # p_j = 0.3, se=0.9, sp=0.8 => pi = (0.3-0.2)/(0.9+0.8-1) = 0.1/0.7
    est = rogan_gladen(0.3, 0.9, 0.8)
    assert abs(est.p_hat - (0.1 / 0.7)) < 1e-12
    assert abs(rogan_gladen_point(0.3, 0.9, 0.8) - 0.1 / 0.7) < 1e-12
    # Perfect classifier: pi = p_j
    assert abs(rogan_gladen_point(0.4, 1.0, 1.0) - 0.4) < 1e-12
    assert rogan_gladen_point(0.4, 0.4, 0.4) is None


def test_rogan_gladen_bootstrap_ucb_above_point():
    est = rogan_gladen(
        0.3,
        0.85,
        0.9,
        n_sens=40,
        n_spec=60,
        n_boot=300,
        seed="rg-toy",
    )
    assert est.method == "rogan-gladen-boot"
    assert est.ucb95 >= est.p_hat - 1e-12
    assert 0.0 <= est.p_hat <= 1.0
    assert 0.0 <= est.ucb95 <= 1.0
    empty = rogan_gladen(0.3, 0.85, 0.9, n_sens=0, n_spec=50, n_boot=50)
    assert empty.ucb95 == 1.0


def test_clopper_pearson_lower_matches_upper_flip():
    assert clopper_pearson_lower(0, 20, 0.05) == 0.0
    lo = clopper_pearson_lower(20, 20, 0.05)
    assert abs(lo - 0.05 ** (1 / 20)) < 1e-4
    k, n = 3, 20
    assert abs(clopper_pearson_lower(k, n, 0.05) - (1.0 - clopper_pearson_upper(n - k, n, 0.05))) < 1e-15
    assert clopper_pearson_lower(k, n, 0.05) < k / n < clopper_pearson_upper(k, n, 0.05)


def test_calibrated_perfect_judge_covers():
    y = [1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
    j = list(y)
    # Census judge, calibration is the first 6 units (3 pos, 3 neg), all correct.
    cal_y = y[:6]
    cal_j = j[:6]
    est = calibrated_prevalence_ucb(j, cal_y, cal_j, alpha=0.05)
    true_p = 0.3
    assert est.method == "calibrated-fnr-fpr"
    assert abs(est.p_hat - true_p) < 1e-12
    assert est.ucb95 >= true_p - 1e-12
    assert est.fnr == 0.0
    assert est.fpr == 0.0
    # Unidentified Se (no invalids in cal) is vacuous.
    vac = calibrated_prevalence_ucb(j, [0, 0, 0, 0], [0, 0, 0, 1], alpha=0.05)
    assert vac.ucb95 == 1.0


def test_calibrated_misaligned_raises():
    try:
        calibrated_prevalence_ucb([1, 0], [1], [1, 0])
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_stratified_matches_poststrat_bonferroni():
    y_flag = [1, 0, 1]
    y_un = [0, 0, 0, 0]
    est = stratified_by_judge_ucb(y_flag, y_un, 10, 40, alpha=0.05)
    ref = poststrat_exact_ucb([y_flag, y_un], [10, 40], alpha=0.05)
    assert abs(est.ucb95 - ref.ucb95) < 1e-15
    assert abs(est.p_hat - ref.p_hat) < 1e-15
    assert est.method == "stratified-judge-cp-bonferroni"
    u_flag = clopper_pearson_upper(2, 3, 0.025)
    u_un = clopper_pearson_upper(0, 4, 0.025)
    assert abs(est.ucb95 - (10 / 50 * u_flag + 40 / 50 * u_un)) < 1e-12


def test_ppi_with_judge_matches_ppi_mean():
    y = [1, 0, 0, 1, 0, 0]
    f = [0.9, 0.2, 0.1, 0.8, 0.3, 0.05]
    f_pop = f + [0.4] * 10
    a = ppi_with_judge(y, f, f_pop, alpha=0.05)
    b = ppi_mean_ucb(y, f, f_pop, alpha=0.05)
    assert abs(a.p_hat - b.p_hat) < 1e-15
    assert abs(a.ucb95 - b.ucb95) < 1e-15
    assert a.method.startswith("ppi++")


def test_allocate_proportional_and_flag_heavy():
    n0, n1 = allocate_judge_strata(100, 800, 200, "proportional")
    assert n0 + n1 == 100
    assert n1 == 20
    h0, h1 = allocate_judge_strata(100, 800, 200, "flag-heavy")
    assert h0 + h1 == 100
    assert h1 > n1
    tiny = allocate_judge_strata(5, 2, 2, "proportional")
    assert tiny[0] + tiny[1] == 4
    # nonempty strata get at least one when n>=2
    a0, a1 = allocate_judge_strata(10, 100, 3, "flag-heavy")
    assert a1 >= 1 and a0 >= 1
    assert a0 + a1 == 10


def _noisy_pop(n: int, p: float, se: float, sp: float, seed: int):
    rng = random.Random(seed)
    n_pos = int(round(p * n))
    y = [1] * n_pos + [0] * (n - n_pos)
    j = []
    f = []
    for yi in y:
        if yi == 1:
            ji = 1 if rng.random() < se else 0
        else:
            ji = 1 if rng.random() < (1.0 - sp) else 0
        j.append(ji)
        # Probability auxiliary: peaked around the true label with noise.
        f.append(min(1.0, max(0.0, (0.75 if yi else 0.25) + rng.uniform(-0.1, 0.1))))
    return y, j, f


def test_coverage_sanity_synthetic_noisy_judge():
    y, j, f = _noisy_pop(160, 0.30, 0.85, 0.85, seed=7)
    rows = simulate_cell(y, j, f, n=50, reps=250, seed="judge-cover-toy", n_boot=80)
    by = {r["estimator"]: r for r in rows}
    assert by["srs-hypergeometric"]["coverage"] >= 0.93
    assert by["calibrated-fnr-fpr"]["coverage"] >= 0.93
    assert by["strat-judge-proportional"]["coverage"] >= 0.95
    assert by["strat-judge-flag-heavy"]["coverage"] >= 0.95
    for r in rows:
        assert r["mean_ucb"] >= r["true_p"] - 0.03
        assert 0.0 <= r["mean_p_hat"] <= 1.0
        assert 0.0 <= r["mean_ucb"] <= 1.0


def _cell(pop, n, est, cover, ucb):
    return {
        "pop_id": pop,
        "n": n,
        "estimator": est,
        "coverage": cover,
        "mean_ucb": ucb,
        "usable": cover >= 0.95,
        "true_p": 0.02,
    }


def test_evaluate_predicates_j2_j3_logic():
    estimators = (
        "srs-hypergeometric",
        "rogan-gladen-boot",
        "calibrated-fnr-fpr",
        "strat-judge-proportional",
        "strat-judge-flag-heavy",
        "ppi++-judge",
    )
    cells = []
    for n in (30, 50, 100, 200):
        for est in estimators:
            cover = 0.99
            if est == "srs-hypergeometric":
                ucb = 0.09 if n < 200 else 0.04
            elif est == "strat-judge-proportional":
                ucb = 0.04 if n >= 100 else 0.08
            else:
                ucb = 0.20
            cells.append(_cell("thin-p02-majority", n, est, cover, ucb))
            cells.append(_cell("thin-p02-conservative", n, est, cover, ucb))
    report = {
        "meta": {"auroc_p_invalid_majority": 0.81},
        "cells": cells,
        "savings": [
            {
                "pop_id": "thin-p02-majority",
                "eps": 0.05,
                "n_valid": {
                    "srs-hypergeometric": 200,
                    "rogan-gladen-boot": None,
                    "calibrated-fnr-fpr": None,
                    "strat-judge-proportional": 100,
                    "strat-judge-flag-heavy": None,
                    "ppi++-judge": None,
                },
            },
            {
                "pop_id": "thin-p02-conservative",
                "eps": 0.05,
                "n_valid": {
                    "srs-hypergeometric": 200,
                    "rogan-gladen-boot": None,
                    "calibrated-fnr-fpr": None,
                    "strat-judge-proportional": 100,
                    "strat-judge-flag-heavy": None,
                    "ppi++-judge": None,
                },
            },
        ],
    }
    pred = evaluate_predicates(report)
    assert pred["J1"]["pass"] is True
    assert pred["J2"]["pass"] is True
    assert pred["J3"]["pass"] is True
    assert pred["all_pass"] is True
    report["meta"]["auroc_p_invalid_majority"] = 0.79
    pred_fail = evaluate_predicates(report)
    assert pred_fail["J1"]["pass"] is False
    assert pred_fail["all_pass"] is False
