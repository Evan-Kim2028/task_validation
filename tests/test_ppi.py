import math
import random

from task_validation.sampling.estimators import (
    _z_one_sided,
    clopper_pearson_upper,
    srs_estimate,
)
from task_validation.sampling.ppi import (
    auroc_binary,
    difference_estimator_ucb,
    mix_scores_to_auroc,
    ppi_mean_ucb,
    poststrat_exact_ucb,
    simulate_cell,
    srs_cp_ucb,
)


def test_srs_cp_matches_existing_estimator():
    y = [1, 0, 0, 1, 0]
    est = srs_cp_ucb(y, N=40, alpha=0.05)
    ref = srs_estimate(k=2, n=5, N=40, alpha=0.05)
    assert est.p_hat == ref.p_hat
    assert abs(est.ucb95 - ref.ucb95) < 1e-15
    assert "hypergeometric" in est.method


def test_ppi_constant_scores_reduces_to_sample_mean():
    y = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    f = [0.4] * 10
    f_pop = [0.4] * 100
    est = ppi_mean_ucb(y, f, f_pop, alpha=0.05)
    assert abs(est.lam) < 1e-12
    assert abs(est.p_hat - 0.1) < 1e-12
    # s^2 = 0.1, se = sqrt(0.1/10) = 0.1, plus pred term 0
    se = math.sqrt(0.1 / 10)
    z = _z_one_sided(0.05)
    assert abs(est.se - se) < 1e-9
    assert abs(est.ucb95 - min(1.0, 0.1 + z * se)) < 1e-9
    assert est.method == "ppi++-normal"


def test_ppi_lam_one_closed_form():
    y = [1.0, 0.0]
    f_lab = [0.8, 0.2]
    f_pop = [0.8, 0.2, 0.5, 0.5]
    est = ppi_mean_ucb(y, f_lab, f_pop, alpha=0.05, lam=1.0)
    # theta = 1 * 0.5 + mean([0.2, -0.2]) = 0.5
    assert abs(est.p_hat - 0.5) < 1e-12
    assert est.lam == 1.0


def test_ppi_power_tune_perfect_labeled_match():
    y = [0.0, 1.0, 0.0, 1.0]
    f = [0.0, 1.0, 0.0, 1.0]
    est = ppi_mean_ucb(y, f, f, alpha=0.05)
    # cov = var = 1/3, r = 1, lam = (1/3) / (2/3) = 0.5
    assert abs(est.lam - 0.5) < 1e-12
    assert abs(est.p_hat - 0.5) < 1e-12


def test_difference_perfect_predictions_zero_width():
    y_pop = [1, 0, 1, 0, 1, 0, 1, 0]
    f_pop = [float(v) for v in y_pop]
    y_lab = y_pop[:4]
    f_lab = f_pop[:4]
    est = difference_estimator_ucb(y_lab, f_lab, f_pop, alpha=0.05)
    assert abs(est.p_hat - 0.5) < 1e-12
    assert est.se == 0.0
    assert abs(est.ucb95 - 0.5) < 1e-12
    assert est.method == "difference-greg-fpc"


def test_difference_fpc_known_se():
    y = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    f = [0.5] * 10
    f_pop = [0.5] * 100
    est = difference_estimator_ucb(y, f, f_pop, alpha=0.05, lam=1.0)
    assert abs(est.p_hat - 0.1) < 1e-12
    # residuals y-f have sample var 0.1; FPC = 0.9; var = 0.9 * 0.1 / 10
    se = math.sqrt(0.9 * 0.1 / 10)
    assert abs(est.se - se) < 1e-12
    z = _z_one_sided(0.05)
    assert abs(est.ucb95 - (0.1 + z * se)) < 1e-9


def test_poststrat_bonferroni_matches_weighted_cp():
    y_by = [[0, 0, 0, 0, 0], [1, 0]]
    n_h = [50, 50]
    est = poststrat_exact_ucb(y_by, n_h, alpha=0.05)
    u0 = clopper_pearson_upper(0, 5, 0.025)
    u1 = clopper_pearson_upper(1, 2, 0.025)
    assert abs(est.ucb95 - 0.5 * (u0 + u1)) < 1e-12
    assert abs(est.p_hat - (0.5 * 0.0 + 0.5 * 0.5)) < 1e-12
    assert est.method == "poststrat-cp-bonferroni"


def test_poststrat_empty_stratum_ucb_is_one():
    y_by = [[0, 0, 0, 0], []]
    est = poststrat_exact_ucb(y_by, [20, 20], alpha=0.05)
    u0 = clopper_pearson_upper(0, 4, 0.025)
    assert abs(est.ucb95 - (0.5 * u0 + 0.5 * 1.0)) < 1e-12


def test_auroc_perfect_and_ties():
    y = [0, 0, 1, 1]
    assert auroc_binary(y, [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert auroc_binary(y, [0.9, 0.8, 0.2, 0.1]) == 0.0
    # complete ties
    assert auroc_binary(y, [0.5, 0.5, 0.5, 0.5]) == 0.5


def test_mix_degrade_lowers_auroc():
    rng = random.Random(0)
    y = [0] * 40 + [1] * 40
    f = [0.2] * 40 + [0.8] * 40
    mixed, au, a = mix_scores_to_auroc(y, f, 0.6, rng, toward_label=False)
    assert au is not None
    assert au < 0.95
    assert abs(au - 0.6) < 0.03
    assert 0.0 < a <= 1.0
    mixed_up, au_up, _ = mix_scores_to_auroc(y, f, 0.95, rng, toward_label=True)
    assert au_up is not None and au_up >= 0.9
    assert mixed and mixed_up


def test_coverage_sanity_synthetic_300_reps():
    rng = random.Random(1)
    n_pop = 160
    y = [1 if i < 48 else 0 for i in range(n_pop)]  # p = 0.3
    f = []
    for yi in y:
        base = 0.78 if yi else 0.22
        f.append(min(1.0, max(0.0, base + rng.uniform(-0.12, 0.12))))
    rows = simulate_cell(y, f, n=50, reps=300, seed="ppi-cover-toy")
    by = {r["estimator"]: r for r in rows}
    assert by["srs-hypergeometric"]["coverage"] >= 0.93
    assert by["poststrat-cp-bonferroni"]["coverage"] >= 0.95
    # Normal PPI / difference should be near nominal on this not-rare p.
    assert by["ppi++-normal"]["coverage"] >= 0.90
    assert by["difference-greg-fpc"]["coverage"] >= 0.90
    for r in rows:
        assert r["mean_ucb"] >= r["true_p"] - 0.02
        assert 0.0 <= r["mean_p_hat"] <= 1.0
