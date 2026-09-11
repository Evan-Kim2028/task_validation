"""Calibration slope and intercept of predicted probabilities."""

from __future__ import annotations

import math


def _logit(p: float) -> float:
    eps = 1e-6
    p = min(1 - eps, max(eps, p))
    return math.log(p / (1 - p))


def calibration_slope_intercept(y: list[int], p: list[float]) -> dict:
    """Logistic regression y ~ logit(p). Slope 1 and intercept 0 is perfect.

    Implemented with Newton steps on two coefficients. No sklearn required.
    """
    z = [_logit(pi) for pi in p]
    b0, b1 = 0.0, 1.0
    n = len(y)
    if n == 0:
        return {"intercept": None, "slope": None}
    for _ in range(25):
        p_hat = []
        for zi in z:
            eta = b0 + b1 * zi
            # stable sigmoid
            if eta >= 0:
                p_hat.append(1 / (1 + math.exp(-eta)))
            else:
                e = math.exp(eta)
                p_hat.append(e / (1 + e))
        # Hessian and gradient
        g0 = g1 = 0.0
        h00 = h01 = h11 = 0.0
        for yi, pi, zi in zip(y, p_hat, z):
            w = pi * (1 - pi)
            resid = pi - yi
            g0 += resid
            g1 += resid * zi
            h00 += w
            h01 += w * zi
            h11 += w * zi * zi
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            break
        db0 = (h11 * g0 - h01 * g1) / det
        db1 = (-h01 * g0 + h00 * g1) / det
        b0 -= db0
        b1 -= db1
        if abs(db0) + abs(db1) < 1e-8:
            break
    return {"intercept": b0, "slope": b1}
