from pathlib import Path

from task_validation.evidence.swe_exec import (
    classify_status,
    collect_rows,
    join_labels,
    parse_elapsed,
    parse_instance_report,
    pass_frac,
    phi_coefficient,
    summarize,
)
from task_validation.evidence import swe_exec as swe_exec_mod


def _report(iid: str, *, resolved: bool, f2p_ok=None, f2p_bad=None, p2p_ok=None, p2p_bad=None, infra=False):
    return {
        iid: {
            "patch_is_None": False,
            "patch_exists": True,
            "patch_successfully_applied": True,
            "resolved": resolved,
            "infra_failure": infra,
            "tests_status": {
                "FAIL_TO_PASS": {
                    "success": list(f2p_ok or []),
                    "failure": list(f2p_bad or []),
                },
                "PASS_TO_PASS": {
                    "success": list(p2p_ok or []),
                    "failure": list(p2p_bad or []),
                },
            },
        }
    }


def test_parse_instance_report_lists_and_resolved():
    iid = "django__django-17029"
    parsed = parse_instance_report(
        _report(iid, resolved=True, f2p_ok=["t_f2p"], p2p_ok=["t_p2p"], p2p_bad=[]),
        iid,
    )
    assert parsed["resolved"] is True
    assert parsed["fail_to_pass_success"] == ["t_f2p"]
    assert parsed["fail_to_pass_failure"] == []
    assert parsed["pass_to_pass_success"] == ["t_p2p"]
    wrapped = _report(iid, resolved=True, f2p_ok=["t_f2p"], p2p_ok=["t_p2p"])
    assert swe_exec_mod.tests_status_lists(wrapped[iid])["fail_to_pass_success"] == ["t_f2p"]
    assert pass_frac(["a"], ["b"]) == 0.5


def test_classify_timeout_infra_executed():
    parsed = parse_instance_report(
        _report("x", resolved=False, f2p_bad=["t"]), "x"
    )
    assert classify_status(parsed, log_text="Test runtime: 12.00 seconds") == "executed"
    assert (
        classify_status(parsed, test_output="Timeout error: 1800 seconds exceeded.")
        == "timeout"
    )
    assert (
        classify_status(None, log_text="Image not found locally, attempting to pull...")
        == "infra"
    )
    infra_parsed = parse_instance_report(
        {"y": {"resolved": False, "infra_failure": True, "infra_failure_reason": "oom"}},
        "y",
    )
    assert classify_status(infra_parsed) == "infra"


def test_parse_elapsed_underscores():
    assert parse_elapsed("Test runtime: 12.34 seconds") == 12.34
    assert parse_elapsed("Test runtime: 1_234.50 seconds") == 1234.5
    assert parse_elapsed("no runtime") is None


def test_join_labels_compact_oof_raters():
    labels = join_labels(
        "django__django-17029",
        cells={"django__django-17029": {"cell": "valid_low", "p_logistic": 0.3, "task_id": "django__django-17029"}},
        compact={
            "django__django-17029": {
                "human_validity_label": "valid",
                "human_severity": {
                    "underspecified": 1.0,
                    "false_negative": 0.0,
                    "other_major_issues": 0.0,
                    "filter_out": False,
                },
                "n_raters": 3,
                "repository": "django",
            }
        },
        oof={"django__django-17029": {"p_logistic": 0.36, "y": 0}},
        raters={
            "django__django-17029": {
                "openai_2024_conservative": 0,
                "majority_invalid": 0,
                "votes": [0, 0, 0],
                "n_raters": 3,
                "n_material_votes": 0,
            }
        },
    )
    assert labels["cell"] == "valid_low"
    assert labels["p_logistic"] == 0.36
    assert labels["human_validity_label"] == "valid"
    assert labels["openai_2024_conservative"] == 0
    assert labels["underspecified"] == 1.0


def _row(iid, treatment, rep, **kw):
    base = {
        "instance_id": iid,
        "treatment": treatment,
        "rep": rep,
        "status": "executed",
        "elapsed_sec": 10.0,
        "error_tail": None,
        "resolved": False,
        "fail_to_pass_success": [],
        "fail_to_pass_failure": ["f2p"],
        "pass_to_pass_success": ["p2p"],
        "pass_to_pass_failure": [],
        "cell": "valid_low",
        "p_logistic": 0.2,
        "human_validity_label": "valid",
        "openai_2024_conservative": 0,
        "majority_invalid": 0,
    }
    base.update(kw)
    return base


def test_summarize_signal_crosstab_and_reference_fail():
    rows = [
        _row("a", "gold", 0, resolved=True, fail_to_pass_success=["f2p"], fail_to_pass_failure=[]),
        _row("a", "empty", 0, resolved=False),
        _row("a", "gold", 1, resolved=True, fail_to_pass_success=["f2p"], fail_to_pass_failure=[]),
        _row(
            "b",
            "gold",
            0,
            resolved=False,
            fail_to_pass_failure=["test_gold_miss"],
            openai_2024_conservative=1,
            majority_invalid=1,
            human_validity_label="invalid",
            cell="invalid_high",
        ),
        _row(
            "b",
            "empty",
            0,
            resolved=False,
            openai_2024_conservative=1,
            majority_invalid=1,
            human_validity_label="invalid",
            cell="invalid_high",
        ),
        _row(
            "b",
            "gold",
            1,
            resolved=True,
            fail_to_pass_success=["f2p"],
            fail_to_pass_failure=[],
            openai_2024_conservative=1,
            majority_invalid=1,
        ),
    ]
    summary = summarize(rows, ["a", "b"])
    assert summary["n_gold_pass"] == 1
    assert summary["n_empty_fail"] == 2
    assert summary["n_reference_fails_own_verifier"] == 1
    assert summary["reference_fail_tests"]["b"] == ["test_gold_miss"]
    assert summary["n_flaky"] == 1
    assert summary["instances"]["a"]["gold_resolved"] is True
    assert summary["instances"]["a"]["empty_resolved"] is False
    assert summary["instances"]["a"]["gold_f2p_pass_frac"] == 1.0
    assert summary["instances"]["a"]["empty_f2p_fail_frac"] == 1.0
    assert summary["instances"]["a"]["p2p_break_on_gold"] is False
    assert summary["instances"]["a"]["determinism"] is True
    assert summary["instances"]["b"]["determinism"] is False
    tab = summary["crosstab_signal_vs_conservative"]
    assert tab["signal_and_valid"] == 1
    assert tab["no_signal_and_invalid"] == 1
    assert tab["n"] == 2
    assert summary["expected_null"] is True


def test_phi_null_when_balanced():
    # no association
    assert phi_coefficient(1, 1, 1, 1) == 0.0
    assert phi_coefficient(4, 0, 0, 0) is None


def test_collect_rows_from_fixture_logs(tmp_path: Path):
    iid = "django__django-17029"
    gold_dir = tmp_path / "tv-gold" / "tv-gold" / iid
    gold_dir.mkdir(parents=True)
    (gold_dir / "report.json").write_text(
        json_dumps(
            _report(iid, resolved=True, f2p_ok=["t1"], p2p_ok=["p1"])
        ),
        encoding="utf-8",
    )
    (gold_dir / "run_instance.log").write_text(
        "Test runtime: 8.50 seconds\n", encoding="utf-8"
    )
    empty_dir = tmp_path / "tv-empty" / "tv-empty" / iid
    empty_dir.mkdir(parents=True)
    (empty_dir / "report.json").write_text(
        json_dumps(_report(iid, resolved=False, f2p_bad=["t1"], p2p_ok=["p1"])),
        encoding="utf-8",
    )
    (empty_dir / "run_instance.log").write_text(
        "Skipping model patch for django__django-17029 (--no-patch mode)\n"
        "Test runtime: 7.00 seconds\n",
        encoding="utf-8",
    )
    cells = {iid: {"task_id": iid, "cell": "valid_low", "p_logistic": 0.3}}
    compact = {iid: {"human_validity_label": "valid", "human_severity": {}, "repository": "django"}}
    oof = {iid: {"p_logistic": 0.3}}
    raters = {iid: {"openai_2024_conservative": 0, "majority_invalid": 0, "votes": [0, 0, 0]}}
    rows = collect_rows(
        tmp_path,
        run_ids=[iid],
        cells=cells,
        compact=compact,
        oof=oof,
        raters=raters,
        treatment_runs=(("gold", "tv-gold", 0), ("empty", "tv-empty", 0), ("gold", "tv-gold-rep", 1)),
    )
    by = {(r["treatment"], r["rep"]): r for r in rows}
    assert by[("gold", 0)]["resolved"] is True
    assert by[("gold", 0)]["status"] == "executed"
    assert by[("gold", 0)]["elapsed_sec"] == 8.5
    assert by[("empty", 0)]["resolved"] is False
    assert by[("empty", 0)]["fail_to_pass_failure"] == ["t1"]
    assert ("gold", 1) not in by
    summary = summarize(rows, [iid])
    assert summary["n_gold_pass"] == 1
    assert summary["n_empty_fail"] == 1
    assert summary["n_infra"] == 0
    assert summary["instances"][iid]["signal_gold_pass_empty_fail"] is True
    assert summary["instances"][iid]["determinism"] is None


def json_dumps(obj) -> str:
    import json

    return json.dumps(obj)
