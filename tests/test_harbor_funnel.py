"""Tiny-fixture tests for doc 45 stage-1 aggregation (harbor_funnel.py)."""

import json

from task_validation.evidence.harbor_funnel import (
    BENCHMARK_FAMILIES,
    FRONTIER_CELLS,
    _fit_logit_fast,
    _pos_weighted_mean_auroc,
    aggregate_stage1,
    benchmark_family,
    frontier_failed_test_stats,
    join_task_traj,
    select_stage1_trials,
    stage1_record,
    within_group_concordance,
)
from task_validation.evidence.footprint import fit_logit
from task_validation.evidence.irt import auroc


def _row(benchmark, task, cell_idx, trial_index, reward, trial_id=None):
    agent, model = FRONTIER_CELLS[cell_idx]
    return {
        "benchmark": benchmark,
        "task_name": task,
        "agent": agent,
        "model": model,
        "trial_index": trial_index,
        "trial_id": trial_id or f"{task}-{cell_idx}-{trial_index}",
        "reward": reward,
        "n_input_tokens": 100,
        "n_cache_tokens": 0,
        "n_output_tokens": 10,
        "cost_usd": 0.01,
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:01:00Z",
        "exception": False,
        "in_scope": True,
    }


def test_selects_six_cells_and_caps_three_trials():
    rows = []
    for c in range(6):
        for ti in range(5):  # 5 stored trials per cell; only 3 may be used
            rows.append(_row("b1", "t1", c, ti, 0.0))
    # A non-frontier cell must be ignored entirely.
    rows.append({**_row("b1", "t1", 0, 0, 0.0), "agent": "openhands"})

    selected = select_stage1_trials(rows)
    assert len(selected) == 18
    per_cell = {}
    for r in selected:
        key = (r["agent"], r["model"])
        per_cell[key] = per_cell.get(key, 0) + 1
    assert len(per_cell) == 6
    assert all(v == 3 for v in per_cell.values())
    # Earliest = lowest trial_index per cell.
    for c in range(6):
        agent, model = FRONTIER_CELLS[c]
        idxs = sorted(
            r["trial_index"] for r in selected
            if (r["agent"], r["model"]) == (agent, model)
        )
        assert idxs == [0, 1, 2]


def test_solve_rate_and_stage1_threshold():
    # 6 successes over 18 -> rate exactly 1/3 -> survived.
    rows = [
        _row("b1", "hard", c, ti, 1.0 if c in (0, 1) else 0.0)
        for c in range(6)
        for ti in range(3)
    ]
    rec = stage1_record("b1", "hard", rows)
    assert rec["n_frontier_trials"] == 18
    assert rec["frontier_n_succ"] == 6
    assert abs(rec["frontier_solve_rate"] - 6 / 18) < 1e-9
    assert rec["survived_stage1"] is True
    assert rec["survived_stage1_n_succ_le6"] is True

    # 7 successes over 18 -> 0.389 > 1/3 -> not survived.
    rows = [
        _row("b1", "easy", c, ti, 1.0 if c in (0, 1) or (c == 2 and ti == 0) else 0.0)
        for c in range(6)
        for ti in range(3)
    ]
    rec = stage1_record("b1", "easy", rows)
    assert rec["frontier_n_succ"] == 7
    assert rec["survived_stage1"] is False


def test_partial_coverage_flags():
    # Only 4 cells present, 2 trials each -> n_cells_ge3 = 0, not full_18.
    rows = [
        _row("b1", "sparse", c, ti, 0.0)
        for c in range(4)
        for ti in range(2)
    ]
    rec = stage1_record("b1", "sparse", rows)
    assert rec["n_frontier_trials"] == 8
    assert rec["n_cells_ge1"] == 4
    assert rec["n_cells_ge3"] == 0
    assert rec["full_18"] == 0.0
    # 0 successes out of 8 -> rate 0 <= 1/3 -> survived by rate rule.
    assert rec["survived_stage1"] is True

    # 3 trials in all six cells but not full 18 is impossible (3x6=18);
    # check ge3 flag on a 18-trial task.
    rows = [
        _row("b1", "full", c, ti, 0.0)
        for c in range(6)
        for ti in range(3)
    ]
    rec = stage1_record("b1", "full", rows)
    assert rec["n_cells_ge3"] == 6
    assert rec["full_18"] == 1.0


def test_aggregate_and_all_trials_rate():
    rows = []
    # task hard: 18 frontier trials, 2 successes, plus 3 non-frontier successes.
    for c in range(6):
        for ti in range(3):
            rows.append(_row("b1", "hard", c, ti, 1.0 if ti == 0 and c < 2 else 0.0))
    for k in range(3):
        rows.append({**_row("b1", "hard", 0, k, 1.0), "agent": "openhands", "model": "x"})
    recs = aggregate_stage1(rows)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["n_frontier_trials"] == 18
    assert rec["frontier_n_succ"] == 2
    assert rec["n_all_trials"] == 21
    assert rec["all_trials_n_succ"] == 5
    assert abs(rec["all_trials_solve_rate"] - 5 / 21) < 1e-9
    assert rec["survived_stage1"] is True


def test_zero_frontier_trials_not_survived():
    rows = [{**_row("b1", "norun", 0, 0, 0.0), "agent": "openhands"}]
    rec = stage1_record("b1", "norun", rows)
    assert rec["n_frontier_trials"] == 0
    assert rec["frontier_solve_rate"] is None
    assert rec["survived_stage1"] is False
    assert rec["survived_stage1_n_succ_le6"] is False


# --- Doc 54: join, family grouping, streaming stats -------------------------


def _label(benchmark, task, s1=False, funnel=False):
    return {
        "benchmark": benchmark,
        "task_name": task,
        "index_task_id": f"idx-{task}" if funnel else None,
        "survived_stage1": s1,
        "survived_funnel": funnel,
        "survived_2_to_4": (funnel if s1 else None),
    }


def _traj_task(benchmark, task, frontier=None):
    return {
        "benchmark": benchmark,
        "task_name": task,
        "in_scope": True,
        "n_trials": 30,
        "frontier": frontier or {"n_trials": 18, "n_steps_mean": 5.0},
    }


def test_join_task_traj_coverage():
    labels = [
        _label("b1", "t1", s1=True),
        _label("b1", "t2"),
        _label("b2", "t3", s1=True, funnel=True),
    ]
    traj = [
        _traj_task("b1", "t1"),
        _traj_task("b2", "t3"),
        _traj_task("b9", "out-of-scope"),  # no label row: must not join
        _traj_task("b2", "t3"),  # duplicate key: counted, last wins
    ]
    joined, cov = join_task_traj(labels, traj)
    assert len(joined) == 3
    assert cov["n_matched"] == 2
    assert cov["n_unmatched_labels"] == 1
    assert cov["unmatched_label_keys"] == ["b1|t2"]
    assert cov["n_task_traj_not_in_labels"] == 1
    assert cov["n_duplicate_task_traj_keys"] == 1
    assert abs(cov["match_rate"] - 2 / 3) < 1e-9
    by_key = {(r["benchmark"], r["task_name"]): r for r in joined}
    assert by_key[("b1", "t1")]["traj"]["frontier"]["n_steps_mean"] == 5.0
    assert by_key[("b1", "t2")]["traj"] is None


def test_benchmark_family_grouping():
    assert benchmark_family("swebench-verified") == "swe_family"
    assert benchmark_family("swe-lancer") == "swe_family"
    assert benchmark_family("multi-swe-bench") == "swe_family"
    assert benchmark_family("terminal-bench") == "terminal_family"
    assert benchmark_family("skillsbench") == "terminal_family"
    assert benchmark_family("compilebench") == "terminal_family"
    assert benchmark_family("aime") == "math_qa_family"
    assert benchmark_family("arc-agi-2") == "math_qa_family"
    # Everything else folds by benchmark.
    assert benchmark_family("gaia") == "gaia"
    assert benchmark_family("dacode") == "dacode"
    # Families are disjoint and every member maps back.
    seen = set()
    for _fam, members in BENCHMARK_FAMILIES:
        assert not (members & seen)
        seen |= members
        for b in members:
            assert benchmark_family(b) == _fam


def test_frontier_failed_test_stats(tmp_path):
    agent, model = FRONTIER_CELLS[0]
    agent2, model2 = FRONTIER_CELLS[1]
    rows = [
        # task t1: 4 frontier trials, 3 failing; all 3 contain test_a
        {"benchmark": "b1", "task_name": "t1", "agent": agent, "model": model,
         "in_scope": True, "n_tests_failed": 2, "failed_test_names": ["test_a", "test_b"]},
        {"benchmark": "b1", "task_name": "t1", "agent": agent2, "model": model2,
         "in_scope": True, "n_tests_failed": 1, "failed_test_names": ["test_a"]},
        {"benchmark": "b1", "task_name": "t1", "agent": agent, "model": model,
         "in_scope": True, "n_tests_failed": 1, "failed_test_names": ["test_a"]},
        {"benchmark": "b1", "task_name": "t1", "agent": agent, "model": model,
         "in_scope": True, "n_tests_failed": 0, "failed_test_names": []},
        # non-frontier cell: ignored entirely
        {"benchmark": "b1", "task_name": "t1", "agent": "openhands", "model": "x",
         "in_scope": True, "n_tests_failed": 3, "failed_test_names": ["test_z"]},
        # out of scope: ignored
        {"benchmark": "b1", "task_name": "t9", "agent": agent, "model": model,
         "in_scope": False, "n_tests_failed": 2, "failed_test_names": ["test_q"]},
        # task t2: failing but not in `pairs` when filtered
        {"benchmark": "b1", "task_name": "t2", "agent": agent, "model": model,
         "in_scope": True, "n_tests_failed": 1, "failed_test_names": ["test_c"]},
    ]
    p = tmp_path / "traj.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))

    stats = frontier_failed_test_stats(p)
    s = stats[("b1", "t1")]
    assert s["n_frontier_trials_seen"] == 4
    assert s["n_failing_frontier_trials"] == 3
    assert s["n_distinct_failed_tests"] == 2
    assert s["top_failed_test"] == "test_a"
    assert abs(s["top_failed_share"] - 1.0) < 1e-9  # 3 of 3 failing contain test_a
    assert stats[("b1", "t2")]["top_failed_test"] == "test_c"
    assert ("b1", "t9") not in stats

    only_t1 = frontier_failed_test_stats(p, pairs={("b1", "t1")})
    assert set(only_t1) == {("b1", "t1")}


# --- Doc 54 correction: within-benchmark concordance ------------------------


def test_within_group_concordance_exact():
    # Hand-computed. g1: pos 0.9 vs negs 0.5, 0.1 -> 2/2 concordant.
    # g2: pos 0.2 vs neg 0.8 -> 0/1. g3: pos 0.5 vs neg 0.5 -> tie, 0.5/1.
    # Within = (2 + 0 + 0.5) / (2 + 1 + 1) = 0.625.
    y =      [1,   0,   0,   1,   0,   1,   0]
    scores = [0.9, 0.5, 0.1, 0.2, 0.8, 0.5, 0.5]
    groups = ["g1", "g1", "g1", "g2", "g2", "g3", "g3"]
    out = within_group_concordance(y, scores, groups)
    assert out["n_pairs"] == 4
    assert abs(out["concordant_pair_equivalents"] - 2.5) < 1e-12
    assert abs(out["value"] - 0.625) < 1e-12
    # The pooled AUROC is a different statistic: 7/12 here.
    assert abs(auroc(y, scores) - 7 / 12) < 1e-9


def test_within_group_concordance_removes_group_identity_credit():
    # g1 scores sit above g2 scores throughout, so the pooled AUROC earns
    # cross-benchmark credit: 12/16 = 0.75. Inside each benchmark the
    # ranking is g1 perfect (3/3) and g2 reversed (0/3): 3/6 = 0.5.
    y =      [1,   1,   1,   0,   1,   0,   0,   0]
    scores = [0.9, 0.85, 0.8, 0.7, 0.3, 0.6, 0.55, 0.5]
    groups = ["g1"] * 4 + ["g2"] * 4
    out = within_group_concordance(y, scores, groups)
    assert out["n_pairs"] == 6
    assert abs(out["value"] - 0.5) < 1e-12
    assert abs(auroc(y, scores) - 0.75) < 1e-9


def test_within_group_concordance_single_class_groups():
    # No group has both classes -> no within-group pairs -> undefined.
    out = within_group_concordance([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1],
                                   ["g1", "g1", "g2", "g2"])
    assert out["n_pairs"] == 0
    assert out["value"] is None
    # Missing scores are skipped, not counted.
    out = within_group_concordance([1, 0, 0], [0.9, None, 0.1],
                                   ["g1", "g1", "g1"])
    assert out["n_pairs"] == 1
    assert out["value"] == 1.0


def test_pos_weighted_mean_auroc_exact():
    # g1: pos 0.9 vs negs 0.5, 0.1 -> AUROC 1.0, weight 1 positive.
    # g2: pos 0.2 vs neg 0.8 -> AUROC 0.0, weight 1 positive.
    # Positives-weighted mean = (1.0 * 1 + 0.0 * 1) / 2 = 0.5.
    y =      [1,   0,   0,   1,   0]
    scores = [0.9, 0.5, 0.1, 0.2, 0.8]
    groups = ["g1", "g1", "g1", "g2", "g2"]
    assert abs(_pos_weighted_mean_auroc(y, scores, groups) - 0.5) < 1e-12


def test_fit_logit_fast_matches_stdlib():
    # Same model class: coefficients and scores agree with fit_logit.
    import random as _r

    rng = _r.Random(7)
    X = [[rng.gauss(0, 1), rng.gauss(1, 2), rng.uniform(0, 1)] for _ in range(300)]
    y = [1 if row[0] + 0.3 * row[1] + rng.gauss(0, 1) > 1.0 else 0 for row in X]
    m_slow = fit_logit(X, y)
    m_fast = _fit_logit_fast(X, y)
    assert m_fast["ok"] and m_slow["ok"]
    assert abs(m_fast["intercept"] - m_slow["intercept"]) < 1e-6
    for a, b in zip(m_fast["coef"], m_slow["coef"]):
        assert abs(a - b) < 1e-6
