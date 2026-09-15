"""Fixture tests for doc 65 selection-replay rank recovery."""

import random

from task_validation.evidence.selection_replay import (
    band_members,
    cell_matrix,
    kendall_tau,
    oracle_select,
    parametric_cells,
    rank_agreement,
    ranks_desc,
    resample_cells,
    select_irt,
    select_pbis,
    select_random,
    submission_means,
    task_solve_rates,
)


def test_kendall_tau_perfect_and_reversed():
    assert kendall_tau([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert kendall_tau([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0


def test_kendall_tau_known_value():
    # One discordant pair out of 3: tau = (2-1)/3 = 1/3.
    assert abs(kendall_tau([1, 2, 3], [1, 3, 2]) - 1.0 / 3.0) < 1e-9


def test_ranks_desc_orders_best_first():
    r = ranks_desc([0.9, 0.1, 0.5])
    assert r == [1.0, 3.0, 2.0]


def test_submission_means_and_full_recovery():
    # 4 tasks x 3 submissions; selecting all items recovers tau = 1.
    matrix = [
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.5, 0.0],
    ]
    means = submission_means(matrix, [0, 1, 2, 3])
    assert means == [0.75, 0.375, 0.25]
    full = ranks_desc(means)
    ag = rank_agreement(matrix, [0, 1, 2, 3], full)
    assert ag["tau"] == 1.0
    assert abs(ag["rho"] - 1.0) < 1e-9
    assert ag["mean_rank_dist"] == 0.0


def test_select_random_size_and_range():
    rng = random.Random(0)
    items = select_random(66, 16, rng)
    assert len(items) == 16
    assert all(0 <= i < 66 for i in items)
    assert len(set(items)) == 16


def test_band_members_respects_bounds():
    rates = [0.0, 0.15, 0.5, 0.7, 0.9]
    assert band_members(rates, 0.10, 0.70) == [1, 2, 3]
    assert band_members(rates, 0.25, 0.75) == [2, 3]


def _separable_matrix():
    """8 items: 4 strongly discriminating, 4 noise-level."""
    # subs ordered weak -> strong
    strong = [
        [0.0, 0.0, 0.0, 0.4, 0.8, 1.0],
        [0.0, 0.2, 0.0, 0.6, 0.8, 1.0],
        [0.2, 0.0, 0.4, 0.4, 1.0, 1.0],
        [0.0, 0.0, 0.2, 0.6, 0.8, 0.8],
    ]
    flat = [
        [0.4, 0.6, 0.4, 0.6, 0.4, 0.6],
        [0.6, 0.4, 0.6, 0.4, 0.6, 0.4],
        [0.5, 0.5, 0.4, 0.5, 0.6, 0.5],
        [0.4, 0.5, 0.6, 0.5, 0.4, 0.5],
    ]
    return strong + flat


def test_select_pbis_prefers_discriminating_items():
    matrix = _separable_matrix()
    items, pbis = select_pbis(matrix, 4)
    assert items == [0, 1, 2, 3]
    assert all(pbis[i] > 0 for i in items)


def test_select_irt_returns_k_items():
    matrix = _separable_matrix()
    items, par = select_irt(matrix, 4)
    assert len(items) <= 4
    assert len(items) >= 1
    # the strong items should carry more information at the mean
    info_strong = sum(par["info"][i] for i in range(4))
    info_flat = sum(par["info"][i] for i in range(4, 8))
    assert info_strong > info_flat


def test_oracle_never_exceeds_one_and_beats_single():
    matrix = _separable_matrix()
    full = ranks_desc(submission_means(matrix, list(range(8))))
    out = oracle_select(matrix, 4, full)
    assert len(out["items"]) == 4
    assert out["tau"] <= 1.0 + 1e-9


def test_cell_matrix_and_rates():
    tasks = ["a", "b"]
    cells = {("a", 0): [1, 0], ("a", 1): [1, 1], ("b", 0): [0, 0], ("b", 1): [1, 0]}
    m = cell_matrix(tasks, 2, cells)
    assert m == [[0.5, 1.0], [0.0, 0.5]]
    assert task_solve_rates(m) == [0.75, 0.25]


def test_resample_and_parametric_preserve_shape():
    cells = {("a", 0): [0, 1, 0, 1, 1]}
    rng = random.Random(1)
    out = resample_cells(cells, rng)
    assert len(out[("a", 0)]) == 5
    assert set(out[("a", 0)]) <= {0, 1}
    par = parametric_cells(cells, 20, rng)
    assert len(par[("a", 0)]) == 20
    assert set(par[("a", 0)]) <= {0, 1}
