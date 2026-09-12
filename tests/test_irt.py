"""2PL IRT: synthetic recovery plus matrix / missing / MWU units."""

from __future__ import annotations

import math
import random

from task_validation.evidence.irt import (
    FROZEN_PREDICATE,
    auroc,
    build_matrix,
    cell_value,
    evaluate_frozen_predicate,
    fit_2pl,
    mann_whitney_u,
    near_constant,
    parse_results,
    pearson,
    sigmoid,
    solve_rate,
)


def _simulate_2pl(n_items: int, n_persons: int, seed: int):
    rng = random.Random(seed)
    true_a = [0.7 + 0.08 * i for i in range(n_items)]
    true_b = [(i - (n_items - 1) / 2) / (n_items / 4) for i in range(n_items)]
    true_th = [rng.gauss(0.0, 1.0) for _ in range(n_persons)]
    Y = []
    for i in range(n_items):
        row = []
        for j in range(n_persons):
            p = sigmoid(true_a[i] * (true_th[j] - true_b[i]))
            row.append(1 if rng.random() < p else 0)
        Y.append(row)
    return true_a, true_b, Y


def test_2pl_recovers_parameters():
    true_a, true_b, Y = _simulate_2pl(16, 180, seed=20260911)
    fit = fit_2pl(Y, max_iter=50)
    hat_a = fit["a"]
    hat_b = [b if b is not None else 0.0 for b in fit["b"]]
    corr_a = pearson(true_a, hat_a)
    corr_b = pearson(true_b, hat_b)
    assert corr_a is not None and corr_a > 0.5, corr_a
    assert corr_b is not None and corr_b > 0.85, corr_b
    assert all(a > 0 for a in hat_a)
    assert fit["n_iter"] >= 1
    assert fit["nll_end"] <= fit["nll_start"] + 1e-6


def test_no_generation_is_missing_resolved_is_one():
    parsed = parse_results(
        {
            "resolved": ["a", "b"],
            "no_generation": ["c"],
            "no_logs": ["d"],
            "generated": ["a", "b", "e"],
        }
    )
    assert cell_value(parsed, "a", assume_full=False) == 1
    assert cell_value(parsed, "e", assume_full=False) == 0
    assert cell_value(parsed, "c", assume_full=False) is None
    assert cell_value(parsed, "d", assume_full=False) is None
    assert cell_value(parsed, "z", assume_full=False) is None
    parsed_full = parse_results({"resolved": ["a"], "no_generation": ["c"]})
    assert cell_value(parsed_full, "b", assume_full=True) == 0
    assert cell_value(parsed_full, "c", assume_full=True) is None


def test_near_constant_and_solve_rate():
    p, n, k = solve_rate([1, 1, 0, None, 0])
    assert n == 4 and k == 2
    assert abs(p - 0.5) < 1e-12
    assert near_constant(0.01)
    assert near_constant(0.99)
    assert not near_constant(0.5)


def test_filter_90pct(tmp_path):
    labeled = [f"t{i}" for i in range(10)]
    full = tmp_path / "full" / "results"
    full.mkdir(parents=True)
    (full / "results.json").write_text(
        '{"resolved": ["t0", "t1"], "no_generation": ["t9"]}',
        encoding="utf-8",
    )
    thin = tmp_path / "thin" / "results"
    thin.mkdir(parents=True)
    (thin / "results.json").write_text(
        '{"resolved": ["t0"], "no_generation": ["t1","t2","t3","t4","t5"]}',
        encoding="utf-8",
    )
    packed = build_matrix(
        labeled,
        [full / "results.json", thin / "results.json"],
        min_attempt_frac=0.90,
    )
    assert packed["n_submissions_listed"] == 2
    assert packed["n_submissions_used"] == 1
    assert packed["used_names"] == ["full"]
    assert packed["matrix"][0] == [1]
    assert packed["matrix"][9] == [None]


def test_mann_whitney_and_auroc_direction():
    low = [0.1, 0.2, 0.15, 0.05]
    high = [0.8, 0.9, 0.85, 0.7]
    mw = mann_whitney_u(low, high)
    assert mw["median_x"] < mw["median_y"]
    assert mw["p_less"] < 0.05
    y = [1, 1, 1, 0, 0, 0]
    scores = [0.9, 0.8, 0.7, 0.3, 0.2, 0.1]
    assert abs(auroc(y, scores) - 1.0) < 1e-12
    assert abs(auroc(y, [1 - s for s in scores]) - 0.0) < 1e-12


def test_frozen_predicate_pass_and_fail():
    assert "lower 2PL discrimination" in FROZEN_PREDICATE
    a = [0.2, 0.25, 0.3, 0.22, 0.18, 0.28] + [1.4, 1.5, 1.6, 1.7, 1.55, 1.45]
    y = [1] * 6 + [0] * 6
    near = [True, True, True, True, False, False] + [False] * 6
    got = evaluate_frozen_predicate(a, y, near)
    assert got["pass"] is True
    flipped = evaluate_frozen_predicate(a, [1 - t for t in y], near)
    assert flipped["pass"] is False
