from task_validation.sampling.estimators import (
    clopper_pearson_upper,
    horvitz_thompson,
    hypergeometric_upper,
    srs_estimate,
)


def test_clopper_pearson_zero_events():
    # Classic rule of three: ~3/n, here exact CP for k=0, n=20, 95%.
    ucb = clopper_pearson_upper(0, 20, 0.05)
    expected = 1.0 - 0.05 ** (1 / 20)
    assert abs(ucb - expected) < 1e-4


def test_clopper_pearson_all_invalid():
    assert clopper_pearson_upper(5, 5, 0.05) == 1.0


def test_hypergeometric_tighter_than_binomial_when_n_near_N():
    k, n, N = 0, 20, 25
    hg = hypergeometric_upper(k, n, N, 0.05)
    cp = clopper_pearson_upper(k, n, 0.05)
    assert hg < cp
    assert 0 <= hg <= 1


def test_srs_estimate_records_method():
    est = srs_estimate(k=2, n=50, N=1000)
    assert est.p_hat == 2 / 50
    assert est.ucb95 > est.p_hat
    assert est.inclusion_probs_recorded
    assert "hypergeometric" in est.method


def test_horvitz_thompson_unbiased_on_census():
    labels = [1, 0, 1, 0]
    pis = [1.0, 1.0, 1.0, 1.0]
    assert horvitz_thompson(labels, pis, N=4) == 0.5
