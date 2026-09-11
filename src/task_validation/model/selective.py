"""Selective risk control for the accepted (low-risk) tail.

Learn-then-test style: nested accept-if-score<=lambda sets. On calibration,
keep the largest lambda whose Clopper-Pearson UCB on invalidity is <= alpha.
This is a filter, not a population certificate.

Inspired by conformal / selective risk control (Angelopoulos et al.; 2026
SRC/CRC variants). We use a one-sided Clopper-Pearson bound on the
calibration accepted set rather than a full LTT grid Bonferroni, which is
slightly optimistic on the grid but conservative per chosen lambda.
"""

from __future__ import annotations

from task_validation.sampling.estimators import clopper_pearson_upper


def select_lambda(
    y_cal: list[int],
    scores_cal: list[float],
    alpha: float = 0.05,
    ucb_alpha: float = 0.05,
) -> dict:
    """Largest accept-set of lowest-risk calibration points with UCB<=alpha."""
    order = sorted(range(len(y_cal)), key=lambda i: (scores_cal[i], i))
    best = {"lambda": None, "n_accept": 0, "k_invalid": 0, "ucb": 1.0, "alpha": alpha}
    for k in range(1, len(order) + 1):
        prefix = order[:k]
        inv = sum(y_cal[i] for i in prefix)
        ucb = clopper_pearson_upper(inv, k, ucb_alpha)
        if ucb <= alpha:
            lam = scores_cal[prefix[-1]]
            best = {
                "lambda": lam,
                "n_accept": k,
                "k_invalid": inv,
                "ucb": ucb,
                "alpha": alpha,
                "calib_residual": inv / k,
            }
    return best


def apply_lambda(y: list[int], scores: list[float], lam: float | None) -> dict:
    if lam is None:
        return {
            "n_accept": 0,
            "retain_frac": 0.0,
            "residual_invalid": None,
            "lambda": None,
        }
    kept = [i for i, s in enumerate(scores) if s <= lam]
    if not kept:
        return {
            "n_accept": 0,
            "retain_frac": 0.0,
            "residual_invalid": None,
            "lambda": lam,
        }
    inv = sum(y[i] for i in kept)
    return {
        "n_accept": len(kept),
        "retain_frac": len(kept) / len(y),
        "n_invalid": inv,
        "residual_invalid": inv / len(kept),
        "lambda": lam,
    }
