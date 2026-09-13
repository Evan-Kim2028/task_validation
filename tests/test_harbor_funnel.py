"""Tiny-fixture tests for doc 45 stage-1 aggregation (harbor_funnel.py)."""

from task_validation.evidence.harbor_funnel import (
    FRONTIER_CELLS,
    aggregate_stage1,
    select_stage1_trials,
    stage1_record,
)


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
