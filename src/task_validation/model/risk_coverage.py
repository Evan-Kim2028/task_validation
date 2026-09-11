"""Accepted-tail residual invalidity. The number that matters for certification."""

from __future__ import annotations


RETAIN_FRACS = (0.01, 0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 1.00)


def retain_curve(y: list[int], scores: list[float], fracs: tuple[float, ...] = RETAIN_FRACS) -> list[dict]:
    """Keep the lowest-risk fraction. Residual = mean(y) among kept.

    Lower score = predicted safer. Sort ascending.
    """
    if not y:
        return []
    order = sorted(range(len(y)), key=lambda i: (scores[i], i))
    out = []
    n = len(y)
    for frac in fracs:
        k = max(1, int(round(frac * n)))
        k = min(k, n)
        kept = order[:k]
        invalid = sum(y[i] for i in kept)
        out.append(
            {
                "retain_frac": frac,
                "n_retained": k,
                "n_invalid": invalid,
                "residual_invalid": invalid / k,
            }
        )
    return out


def threshold_curve(y: list[int], scores: list[float], thresholds: list[float]) -> list[dict]:
    out = []
    for t in thresholds:
        kept = [i for i, s in enumerate(scores) if s <= t]
        if not kept:
            out.append({"threshold": t, "n_retained": 0, "residual_invalid": None})
            continue
        invalid = sum(y[i] for i in kept)
        out.append(
            {
                "threshold": t,
                "n_retained": len(kept),
                "retain_frac": len(kept) / len(y),
                "n_invalid": invalid,
                "residual_invalid": invalid / len(kept),
            }
        )
    return out
