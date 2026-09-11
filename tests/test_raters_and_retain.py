from task_validation.ingest.swe_raters import fleiss_kappa_binary, pairwise_agreement, targets_for_task
from task_validation.model.risk_coverage import retain_curve
from task_validation.model.selective import apply_lambda, select_lambda
from task_validation.sampling.estimators import clopper_pearson_upper


def test_targets_ladder():
    raters = [
        {"underspecified": 2, "false_negative": 0, "other_major_issues": 0},
        {"underspecified": 0, "false_negative": 3, "other_major_issues": 0},
        {"underspecified": 0, "false_negative": 0, "other_major_issues": 0},
    ]
    t = targets_for_task(raters)
    assert t["n_material_votes"] == 2
    assert t["openai_2024_conservative"] == 1
    assert t["majority_invalid"] == 1
    assert t["unanimous_invalid"] == 0


def test_unanimous_requires_three():
    raters = [
        {"underspecified": 3, "false_negative": 0, "other_major_issues": 0},
        {"underspecified": 2, "false_negative": 0, "other_major_issues": 0},
        {"underspecified": 2, "false_negative": 0, "other_major_issues": 0},
    ]
    t = targets_for_task(raters)
    assert t["unanimous_invalid"] == 1


def test_fleiss_perfect_and_chance():
    perfect = [[1, 1, 1], [0, 0, 0], [1, 1, 1]]
    k = fleiss_kappa_binary(perfect)
    assert k["kappa"] == 1.0
    assert pairwise_agreement(perfect) == 1.0


def test_retain_lowest_risk_is_cleaner():
    y = [1, 1, 1, 1, 0, 0, 0, 0]
    scores = [0.9, 0.8, 0.7, 0.6, 0.4, 0.3, 0.2, 0.1]
    curve = retain_curve(y, scores, fracs=(0.25, 0.5, 1.0))
    assert curve[0]["residual_invalid"] == 0.0
    assert curve[1]["residual_invalid"] == 0.0
    assert curve[2]["residual_invalid"] == 0.5


def test_src_picks_prefix_with_ucb_below_alpha():
    y = [0] * 40 + [1] * 10
    scores = [i / 50 for i in range(50)]  # first 40 safest
    chosen = select_lambda(y, scores, alpha=0.10)
    assert chosen["lambda"] is not None
    assert chosen["ucb"] <= 0.10
    assert clopper_pearson_upper(chosen["k_invalid"], chosen["n_accept"], 0.05) <= 0.10 + 1e-9
    applied = apply_lambda(y, scores, chosen["lambda"])
    assert applied["n_accept"] == chosen["n_accept"]
