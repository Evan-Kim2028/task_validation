"""Unit tests for verifier_defect_scan: channel bookkeeping, join
disagreement, flag accumulation, and per-cell stats on synthetic rows."""

import json
import math

from task_validation.evidence.verifier_defect_scan import (
    DISAGREE_EPS,
    acc_traj_row,
    cell_rate_var,
    cell_task_stats,
    channel_diff,
    defect_features,
    finalize_task,
    hack_features,
    json_channel_reward,
    new_task_acc,
    wilson,
    _flag_summary,
    _new_bundle,
    _bundle_add,
    FRONTIER_CELLS,
)


def _row(**kw):
    base = {
        "benchmark": "b",
        "task_name": "b/t1",
        "agent": "claude-code",
        "model": "claude-opus-4-6",
        "trial_id": "t1",
        "reward": 1.0,
        "reward_txt_value": 1.0,
        "parse_error": None,
        "in_scope": True,
        "mentions_answer_file": 0,
        "git_history_probe": 0,
        "network_fetch": 0,
    }
    base.update(kw)
    return base


def test_channel_diff_basic_and_none():
    assert channel_diff(1.0, 0.0) == 1.0
    assert channel_diff(0.5, 0.5) == 0.0
    assert channel_diff(None, 1.0) is None
    assert channel_diff(1.0, None) is None
    assert channel_diff(float("nan"), 1.0) is None
    assert channel_diff(float("inf"), 0.0) is None


def test_wilson_bounds():
    lo, hi = wilson(0, 0)
    assert lo is None and hi is None
    lo, hi = wilson(10, 10)
    assert lo > 0.5 and hi > 0.99
    lo, hi = wilson(0, 20)
    assert lo < 0.01 and hi < 0.3
    lo, hi = wilson(5, 10)
    assert lo < 0.5 < hi


def test_json_channel_reward():
    row = {"result": {"verifier_result": {"rewards": {"reward": 0.5}}}}
    assert json_channel_reward(row) == 0.5
    assert json_channel_reward({"result": None}) is None
    assert json_channel_reward({"result": {"verifier_result": None}}) is None
    assert json_channel_reward({"result": {"verifier_result": {"rewards": {"reward": "x"}}}}) is None


def test_acc_reward_channels():
    acc = new_task_acc()
    # reward.txt present and equal -> txt_present, no mismatch
    acc_traj_row(acc, _row(trial_id="a"), None)
    # reward.txt absent, result.json fallback
    acc_traj_row(acc, _row(trial_id="b", reward=0.0, reward_txt_value=None), None)
    # reward.txt unparseable -> parse_error mark, no reward at all
    acc_traj_row(
        acc,
        _row(
            trial_id="c",
            reward=None,
            reward_txt_value=None,
            parse_error="verifier/reward.txt: not a float",
        ),
        None,
    )
    # non-finite reward.txt
    acc_traj_row(acc, _row(trial_id="d", reward=float("nan"), reward_txt_value=float("nan")), None)
    # internal mismatch (should not occur on the real extract)
    acc_traj_row(acc, _row(trial_id="e", reward=0.0, reward_txt_value=1.0), None)
    assert acc["n_txt_present"] == 2
    assert acc["n_txt_absent"] == 1
    assert acc["n_txt_unparseable"] == 1
    assert acc["n_reward_from_json"] == 1
    assert acc["n_no_reward"] == 1
    assert acc["n_nonfinite_txt"] == 1
    assert acc["n_internal_mismatch"] == 1


def test_acc_join_disagreement():
    acc = new_task_acc()
    fmap = {
        "j1": {"json_reward": 0.0},
        "j2": {"json_reward": 1.0},
        "j3": {"json_reward": 0.5},
        "j4": {"json_reward": None},
    }
    # txt=1 vs json=0 -> disagree, diff 1.0
    d = acc_traj_row(acc, _row(trial_id="j1", reward=1.0, reward_txt_value=1.0), fmap["j1"])
    assert d == 1.0
    # agree
    d = acc_traj_row(acc, _row(trial_id="j2", reward=1.0, reward_txt_value=1.0), fmap["j2"])
    assert d is None
    # sub-epsilon diff counts as agree at 1e-9, material threshold 1e-6
    acc_traj_row(
        acc, _row(trial_id="j3", reward=0.5, reward_txt_value=0.5), fmap["j3"]
    )
    # txt present, json missing
    acc_traj_row(acc, _row(trial_id="j4", reward=1.0, reward_txt_value=1.0), fmap["j4"])
    # not in funnel map at all
    acc_traj_row(acc, _row(trial_id="zz"), None)
    assert acc["n_joined"] == 4
    assert acc["n_join_both"] == 3
    assert acc["n_join_disagree"] == 1
    assert acc["n_join_txt_only"] == 1
    assert acc["join_pairs"][(1.0, 0.0)] == 1


def test_acc_join_subepsilon_and_material():
    acc = new_task_acc()
    fmap = {"k": {"json_reward": 1.0 - 1e-8}}  # diff 1e-8: >1e-9, <1e-6
    acc_traj_row(acc, _row(trial_id="k", reward=1.0, reward_txt_value=1.0), fmap["k"])
    assert acc["n_join_disagree"] == 1
    assert acc["n_join_disagree_material"] == 0


def test_flag_accumulation():
    acc = new_task_acc()
    # flagged solved
    acc_traj_row(acc, _row(trial_id="a", reward=1.0, mentions_answer_file=2), None)
    # flagged unsolved
    acc_traj_row(acc, _row(trial_id="b", reward=0.0, mentions_answer_file=1), None)
    # unflagged solved
    acc_traj_row(acc, _row(trial_id="c", reward=1.0, mentions_answer_file=0), None)
    # flag field missing entirely (trajectory unparsed)
    acc_traj_row(acc, _row(trial_id="d", reward=1.0, mentions_answer_file=None), None)
    fs = _flag_summary(acc["all"]["flags"]["mentions_answer_file"])
    assert fs["n_obs"] == 3
    assert fs["n_pos"] == 2
    assert fs["p_flag"] == 2 / 3
    assert fs["p_solved_given_flag"] == 0.5
    assert fs["p_solved_given_noflag"] == 1.0
    assert fs["n_solved_flag_obs"] == 2
    assert fs["p_flag_given_solved"] == 0.5
    assert fs["p_flag_given_unsolved"] == 1.0


def test_frontier_bundle_split():
    acc = new_task_acc()
    frontier_agent, frontier_model = FRONTIER_CELLS[0]
    acc_traj_row(
        acc,
        _row(trial_id="f", agent=frontier_agent, model=frontier_model, network_fetch=3),
        None,
    )
    acc_traj_row(
        acc,
        _row(trial_id="nf", agent="other", model="other-model", network_fetch=0),
        None,
    )
    assert acc["all"]["n"] == 2
    assert acc["frontier"]["n"] == 1
    assert acc["frontier"]["flags"]["network_fetch"]["n_pos"] == 1
    assert acc["all"]["flags"]["network_fetch"]["n_pos"] == 1


def test_finalize_and_feature_maps():
    acc = new_task_acc()
    acc_traj_row(acc, _row(trial_id="a", git_history_probe=1), {"json_reward": 0.0})
    rec = finalize_task(("b", "b/t1"), acc)
    assert rec["n_trials"] == 1
    assert rec["n_join_disagree"] == 1
    assert rec["join_disagree_rate"] == 1.0
    assert rec["flags_all"]["git_history_probe"]["p_flag"] == 1.0
    df = defect_features(rec)
    assert df["def_disagree_rate"] == 1.0
    assert df["def_n_disagree"] == 1.0
    hf = hack_features(rec)
    assert hf["hack_git_rate_all"] == 1.0
    assert hf["hack_ans_rate_frontier"] is not None
    # missing task -> all-None feature maps
    assert all(v is None for v in defect_features(None).values())
    assert all(v is None for v in hack_features(None).values())


def test_cell_rate_var_and_task_stats():
    assert cell_rate_var([0.0]) is None
    assert cell_rate_var([0.0, 1.0]) == 0.25
    task_cells = {
        ("b", "t1"): {
            ("terminus-2", "m1"): [3, 3, 3],
            ("terminus-2", "m2"): [3, 3, 0],
            ("codex", "m3"): [2, 2, 1],
        }
    }
    stats = cell_task_stats(task_cells)[("b", "t1")]
    assert stats["n_cells"] == 3
    assert abs(stats["pooled_solve_rate"] - 0.5) < 1e-9
    rates = [1.0, 0.0, 0.5]
    m = sum(rates) / 3
    assert abs(stats["cell_rate_var"] - sum((r - m) ** 2 for r in rates) / 3) < 1e-9
    assert stats["cell_rate_spread"] == 1.0
    assert stats["terminus_model_var"] is not None  # two terminus cells


def test_partial_counts():
    acc = new_task_acc()
    acc_traj_row(acc, _row(trial_id="p", reward=0.4, reward_txt_value=0.4), None)
    assert acc["all"]["n_partial"] == 1
    assert acc["all"]["n_solved"] == 0
