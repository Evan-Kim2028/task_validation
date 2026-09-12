"""Fixture tests for the non-LLM validity footprint. No network."""

from __future__ import annotations

from pathlib import Path

from task_validation.evidence.footprint import (
    COMBINED_FEATURES,
    CURATED_FEATURES,
    FEATURE_NAMES,
    FROZEN_PREDICATE,
    LABEL_KEYS,
    RANK_FEATURES,
    TRANSFER_POPS,
    auroc_ci,
    binomial_ci,
    empty_features,
    empty_labels,
    evaluate_frozen_predicate,
    execution_gate_flag,
    fit_logit,
    fit_ranker,
    layout_static_features,
    predict_logit,
    score_ranker,
    sens_spec,
    solve_rate_band,
    static_lopo_matrix,
    swe_static_features,
    transfer_coverage,
    youden_threshold,
)
from task_validation.sampling.judge_bound import rogan_gladen


def _harbor_task(
    root: Path,
    name: str,
    *,
    instruction: str = "Write a parser for empty input.\n",
    tests: str = "def test_pin():\n    assert get_annotation() == 'secret-token'\n",
    solution: str = "#!/bin/bash\necho hi\n",
    toml: str | None = None,
    judge: bool = False,
) -> Path:
    d = root / name
    (d / "environment").mkdir(parents=True)
    (d / "solution").mkdir()
    (d / "tests").mkdir()
    (d / "instruction.md").write_text(instruction, encoding="utf-8")
    (d / "tests" / "test_outputs.py").write_text(tests, encoding="utf-8")
    (d / "solution" / "solve.sh").write_text(solution, encoding="utf-8")
    (d / "environment" / "Dockerfile").write_text("FROM x\n", encoding="utf-8")
    (d / "task.toml").write_text(
        toml
        or (
            "[verifier]\ntimeout_sec = 120\n"
            "[environment]\nmemory_mb = 2048\ncpus = 2\n"
            'network_mode = "no-network"\n'
        ),
        encoding="utf-8",
    )
    if judge:
        (d / "tests" / "native_judge.py").write_text(
            "import os\nJUDGE_MODELS = os.environ['JUDGE_MODELS']\n",
            encoding="utf-8",
        )
    return d


def test_frozen_predicate_written_before_compute():
    assert "4 of 5" in FROZEN_PREDICATE
    assert "3 of 5" in FROZEN_PREDICATE
    assert "verifier" in FROZEN_PREDICATE
    assert "spec" in FROZEN_PREDICATE
    assert TRANSFER_POPS == ("swe", "swe_verified", "swe_pro", "tb21", "harbor_index")
    assert "solve_rate" not in RANK_FEATURES
    assert "p_invalid" not in RANK_FEATURES
    assert "p_logistic" not in RANK_FEATURES
    assert "exec_fail" in COMBINED_FEATURES
    assert "solve_risk" in COMBINED_FEATURES
    assert all(not n.endswith("_missing") for n in CURATED_FEATURES)


def test_empty_features_explicit_nulls():
    feats = empty_features()
    assert set(feats) == set(FEATURE_NAMES)
    assert all(v is None for v in feats.values())
    labels = empty_labels()
    assert set(labels) == set(LABEL_KEYS)
    assert all(v["value"] is None for v in labels.values())


def test_layout_extracts_pins_resources_judge(tmp_path: Path):
    d = _harbor_task(tmp_path, "demo")
    f = layout_static_features(d)
    assert f["instruction_chars"] == float(len("Write a parser for empty input.\n"))
    assert f["test_file_count"] >= 1
    assert f["assertion_count"] >= 1
    assert f["literal_pins_absent"] >= 1
    assert f["solution_size"] > 0
    assert f["resource_memory_mb"] == 2048.0
    assert f["timeout_sec"] == 120.0
    assert f["network_isolated"] == 1.0
    assert f["judge_verifier"] == 0.0
    assert f["reference_pass"] is None
    jdir = _harbor_task(tmp_path, "judged", judge=True)
    jf = layout_static_features(jdir)
    assert jf["judge_verifier"] == 1.0


def test_swe_static_keeps_stored_cheap_and_computes_from_text():
    stored = swe_static_features(
        {
            "task_id": "astropy__x",
            "features": {
                "stmt_chars": 100.0,
                "stmt_lines": 4.0,
                "test_n_files": 2.0,
                "patch_n_changed_lines": 9.0,
                "test_only_id_frac": 0.4,
            },
        }
    )
    assert stored["instruction_chars"] == 100.0
    assert stored["test_file_count"] == 2.0
    assert stored["solution_size"] == 9.0
    assert stored["assertion_count"] is None
    rec = {
        "problem_statement": "The parser crashes on empty input.",
        "patch": "diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-x\n+y\n",
        "test_patch": (
            "diff --git a/test_a.py b/test_a.py\n@@ -0,0 +1,3 @@\n"
            "+def test_get_annotation():\n+    assert get_annotation() == 'secret'\n"
        ),
        "FAIL_TO_PASS": '["test_get_annotation"]',
        "PASS_TO_PASS": "[]",
    }
    f = swe_static_features(rec)
    assert f["assertion_count"] >= 1
    assert f["literal_pins_absent"] >= 1
    assert f["test_only_id_frac"] > 0.0
    assert f["judge_verifier"] == 0.0


def test_execution_gate_null_pass_fail():
    assert execution_gate_flag(empty_features()) is None
    assert execution_gate_flag({"reference_pass": 1.0, "nop_reject": 1.0, "environment_failure": 0.0}) == 0.0
    assert execution_gate_flag({"reference_pass": 0.0, "nop_reject": 1.0, "environment_failure": 0.0}) == 1.0
    assert execution_gate_flag({"reference_pass": 1.0, "nop_reject": 0.0, "environment_failure": 0.0}) == 1.0
    assert execution_gate_flag({"judge_verifier": 1.0, "reference_pass": 0.0}) is None
    assert execution_gate_flag({"environment_failure": 1.0, "reference_pass": 1.0, "nop_reject": 1.0}) == 1.0


def test_solve_rate_band():
    assert solve_rate_band(None) is None
    assert solve_rate_band(0.0) == "never"
    assert solve_rate_band(0.01, near_constant=True) == "never"
    assert solve_rate_band(0.15) == "low"
    assert solve_rate_band(0.5) == "mid"
    assert solve_rate_band(0.9) == "high"


def test_logit_separates_and_auroc_held_out():
    Xtr = [[float(i), 0.1] for i in range(20)] + [[float(30 + i), 0.1] for i in range(20)]
    ytr = [0] * 20 + [1] * 20
    model = fit_logit(Xtr, ytr, l2=0.1)
    Xte = [[5.0, 0.1], [8.0, 0.1], [35.0, 0.1], [40.0, 0.1]]
    yte = [0, 0, 1, 1]
    p = predict_logit(model, Xte)
    cell = auroc_ci(yte, p, seed=1)
    assert cell["auroc"] is not None and cell["auroc"] >= 0.99
    assert cell["ci95"] is not None


def test_binomial_ci_and_sens_spec():
    ci = binomial_ci(0, 10)
    assert ci["p"] == 0.0
    assert ci["lo"] == 0.0
    assert ci["hi"] > 0.0
    ss = sens_spec([1, 1, 0, 0], [1, 0, 0, 0])
    assert ss["sens"] == 0.5
    assert ss["spec"] == 1.0
    assert ss["sens_ci"]["lo"] <= 0.5 <= ss["sens_ci"]["hi"]


def test_youden_and_rogan_gladen_cover():
    y = [0, 0, 0, 0, 1, 1, 1, 1]
    scores = [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9]
    thr = youden_threshold(y, scores)
    assert thr["youden"] > 0.5
    pred = [1 if s >= thr["threshold"] else 0 for s in scores]
    ss = sens_spec(y, pred)
    rg = rogan_gladen(0.5, ss["sens"], ss["spec"], n_sens=4, n_spec=4, n_boot=80, seed="toy")
    assert rg.ucb95 >= rg.p_hat - 1e-12
    assert 0.5 <= rg.ucb95 <= 1.0


def _toy_row(pop, tid, y_spec, y_ver, score_feat, repo="r"):
    feats = empty_features()
    feats["instruction_chars"] = float(score_feat)
    feats["test_only_id_frac"] = float(score_feat) / 100.0
    feats["reference_pass"] = 0.0 if y_ver else 1.0
    feats["nop_reject"] = 1.0
    feats["environment_failure"] = 0.0
    labels = empty_labels()
    labels["openai_2024_conservative"] = {
        "value": y_spec if pop == "swe" else None,
        "provenance": "toy",
        "construct": "spec_invalid",
    }
    labels["aba_major"] = {
        "value": y_spec if pop != "swe" else None,
        "provenance": "toy",
        "construct": "spec_invalid",
    }
    labels["tb21_verifier_repair"] = {
        "value": y_ver if pop == "tb21" else None,
        "provenance": "toy",
        "construct": "verifier_invalid",
    }
    labels["opencompass_category"] = {
        "value": "overly_narrow_tests" if (pop == "swe_pro" and y_ver) else None,
        "provenance": "toy",
        "construct": "verifier_invalid",
    }
    labels["opencompass_repaired"] = {
        "value": 1 if pop == "swe_pro" and y_ver else (0 if pop == "swe_pro" else None),
        "provenance": "toy",
        "construct": "verifier_invalid",
    }
    labels["aba_construct"] = {
        "value": "verifier_invalid" if y_ver else "spec_invalid",
        "provenance": "toy",
        "construct": "mixed",
    }
    labels["our_diagnosis_invalid"] = {
        "value": y_ver if pop == "eval_tasks" else None,
        "provenance": "toy",
        "construct": "verifier_invalid",
    }
    labels["srs100_verifier_invalid"] = {
        "value": y_ver if pop == "swe" else None,
        "provenance": "toy",
        "construct": "verifier_invalid",
    }
    return {
        "population": pop,
        "task_id": tid,
        "repository": repo,
        "features": feats,
        "labels": labels,
    }


def test_lopo_matrix_never_scores_train_population():
    rows = []
    for pop in TRANSFER_POPS:
        for i in range(12):
            y = 1 if i >= 6 else 0
            rows.append(_toy_row(pop, f"{pop}-{i}", y, y, 10 + 40 * y, repo=f"{pop}-r{i%3}"))
    mat = static_lopo_matrix(rows, "spec")
    grid = mat["rows_train_cols_test"]
    for tr in TRANSFER_POPS:
        cell = grid[tr][tr]
        assert cell["auroc"] is None
        assert cell["reason"] == "train_population_excluded"
        for te in TRANSFER_POPS:
            if te == tr:
                continue
            other = grid[tr][te]
            assert other.get("reason") != "train_population_excluded"
            if other.get("auroc") is not None:
                assert 0.0 <= other["auroc"] <= 1.0


def test_lopo_drops_shared_task_ids_from_train():
    rows = []
    for i in range(12):
        y = 1 if i >= 6 else 0
        rows.append(_toy_row("swe", f"shared-{i}", y, 0, 10 + 40 * y, repo="swe"))
        rows.append(_toy_row("swe_verified", f"shared-{i}", y, 0, 10 + 40 * y, repo="ver"))
    for i in range(12):
        y = 1 if i >= 6 else 0
        rows.append(_toy_row("swe_pro", f"pro-{i}", y, 0, 10 + 40 * y, repo="pro"))
    mat = static_lopo_matrix(rows, "spec")
    cell = mat["rows_train_cols_test"]["swe"]["swe_verified"]
    assert cell.get("n_overlap_dropped") == 12
    assert cell.get("n_train") == 0 or cell.get("reason") == "train_unusable_after_id_exclusion"


def test_ranker_top_feature_tracks_signal():
    rows = [_toy_row("swe", f"t{i}", 1 if i >= 10 else 0, 0, 5 + 50 * (i >= 10)) for i in range(20)]
    y = [1 if i >= 10 else 0 for i in range(20)]
    model = fit_ranker(rows, y)
    scores = score_ranker(model, rows)
    assert auroc_ci(y, scores, seed=2)["auroc"] >= 0.9
    top = max(model["coef_map"].items(), key=lambda kv: abs(kv[1]))[0]
    assert "instruction_chars" in top or "test_only_id_frac" in top
    model2 = fit_ranker(rows, y, CURATED_FEATURES, missing_indicators=False)
    scores2 = score_ranker(model2, rows)
    assert len(scores2) == 20
    assert not any(n.endswith("_missing") for n in model2["feature_names"])


def test_evaluate_predicate_counts_covers():
    cov = []
    for i, pop in enumerate(TRANSFER_POPS):
        cov.append({"construct": "verifier", "population": pop, "covers": i < 4})
        cov.append({"construct": "spec", "population": pop, "covers": i < 3})
    pred = evaluate_frozen_predicate(cov)
    assert pred["verifier_hits"] == 4
    assert pred["spec_hits"] == 3
    assert pred["pass"] is True
    assert pred["written_before_computing"] is True
    cov[0]["covers"] = False
    pred2 = evaluate_frozen_predicate(cov)
    assert pred2["verifier_pass"] is False
    assert pred2["pass"] is False


def test_transfer_coverage_uses_other_pops_only():
    rows = []
    for pop in TRANSFER_POPS:
        for i in range(16):
            y = 1 if i >= 8 else 0
            rows.append(_toy_row(pop, f"{pop}-{i}", y, y, 8 + 30 * y))
    cov = transfer_coverage(rows, "spec")
    assert len(cov) == 5
    for cell in cov:
        assert cell["n_cal"] > 0
        assert cell["population"] not in (None,)
        assert cell["n_held"] == 16
        assert "ucb95" in cell
        assert "srs_n100_ucb95" in cell
