from pathlib import Path

from task_validation.evidence.harbor_index_control import (
    build_trial_row,
    catalog_task,
    comparison_block,
    extract_failures,
    order_catalog,
    source_benchmark,
    summarize_rows,
    task_memory_mb,
)
from task_validation.evidence.tb21_pairs import tail_lines


def _row(**kwargs):
    base = dict(
        task_id="hle-dirac-fermion-tunneling",
        source_benchmark="hle",
        probe="oracle",
        intended="accept",
        reward=1.0,
        status="executed",
        elapsed_sec=12.0,
        memory_mb=2048,
        test_stdout_tail="ok",
    )
    base.update(kwargs)
    return build_trial_row(**base)


def test_source_prefix_first_hyphen_token():
    assert source_benchmark("hle-dirac-fermion-tunneling") == "hle"
    assert source_benchmark("gso-speedup-hf-datasets") == "gso"
    assert source_benchmark("swebenchverified-fix-annotate-xy-array-copy") == "swebenchverified"
    assert source_benchmark("swebenchpro-fix-file-suffix-chooser") == "swebenchpro"
    assert source_benchmark("gaia2-adapt-hard-1") == "gaia2"
    assert source_benchmark("gaia-compare-sciencedirect-domains") == "gaia"
    assert source_benchmark("bix-cpg-density-jackdaw") == "bix"
    assert source_benchmark("arcagi2-grid-transform-88e3") == "arcagi2"
    assert source_benchmark("algotune-optimize-lti-sim") == "algotune"
    assert source_benchmark("labbench-count-deg-in-pathway") == "labbench"
    assert source_benchmark("featurebench-add-feature-lightning-hooks") == "featurebench"
    assert source_benchmark("tb-dna-insert") == "tb"
    assert source_benchmark("scicode-dna-binding-site-scanner") == "scicode"
    assert source_benchmark("swtbenchverified-test-runserver-zero-address") == "swtbenchverified"
    assert source_benchmark("build-word2vec-pipeline") == "build"


def test_task_memory_mb_prefers_peak_of_env_and_verifier():
    assert task_memory_mb({"environment.memory_mb": "4096", "verifier.environment.memory_mb": "2048"}) == 4096
    assert task_memory_mb({"verifier.environment.memory_mb": "2048"}) == 2048
    assert task_memory_mb({"environment.memory": "2G"}) == 2048
    assert task_memory_mb({}) is None


def test_catalog_orders_smallest_memory_first(tmp_path: Path):
    def _mk(name: str, toml: str, solution: bool) -> Path:
        d = tmp_path / name
        d.mkdir()
        (d / "task.toml").write_text(toml, encoding="utf-8")
        if solution:
            (d / "solution").mkdir()
        return d

    heavy = _mk("gso-speedup-hf-datasets", "[environment]\nmemory_mb = 8192\n", False)
    light = _mk("arcagi2-grid-transform-88e3", "[environment]\nmemory_mb = 1024\n", True)
    mid = _mk("hle-dirac-fermion-tunneling", "[verifier.environment]\nmemory_mb = 2048\n", True)
    cat = [catalog_task(p) for p in (heavy, light, mid)]
    ordered = order_catalog(cat)
    assert [c["task_id"] for c in ordered] == [
        "arcagi2-grid-transform-88e3",
        "hle-dirac-fermion-tunneling",
        "gso-speedup-hf-datasets",
    ]
    assert ordered[0]["has_reference"] is True
    assert ordered[2]["has_reference"] is False
    assert ordered[1]["memory_mb"] == 2048


def test_timeout_never_fabricates_reward():
    row = _row(reward=0.0, status="timeout")
    assert row["status"] == "timeout"
    assert row["reward"] is None
    assert row["accepted"] is None


def test_infra_never_fabricates_reward():
    row = _row(reward=0.0, status="infra", stderr_tail="failed to pull image")
    assert row["status"] == "infra"
    assert row["reward"] is None
    assert row["accepted"] is None
    assert "failed to pull" in row["stderr_tail"]


def test_executed_zero_is_kept():
    row = _row(reward=0.0, status="executed")
    assert row["reward"] == 0.0
    assert row["accepted"] is False


def test_no_reference_row():
    row = _row(probe="oracle", status="no_reference", reward=None, elapsed_sec=0.0, test_stdout_tail="")
    assert row["status"] == "no_reference"
    assert row["reward"] is None
    assert row["accepted"] is None
    assert row["intended"] == "accept"


def test_nop_intended_reject():
    row = _row(probe="nop", intended="reject", reward=0.0, status="executed")
    assert row["intended"] == "reject"
    assert row["accepted"] is False


def test_stdout_tail_is_last_40_lines():
    text = "\n".join(f"L{i}" for i in range(50))
    row = _row(test_stdout_tail=tail_lines(text, 40))
    assert row["test_stdout_tail"].startswith("L10")
    assert row["test_stdout_tail"].endswith("L49")
    assert len(row["test_stdout_tail"].splitlines()) == 40


def test_extract_failures_pytest_short_summary():
    stdout = """
E       AssertionError: pmars not found
E       assert []

/tests/test_outputs.py:76: AssertionError
=========================== short test summary info ============================
FAILED ../tests/test_outputs.py::test_pmars_works - AssertionError: pmars not...
FAILED ../tests/test_outputs.py::test_headless_no_x11 - subprocess.CalledProc...
ERROR collecting tests/harness.py
============================== 4 failed in 0.09s ===============================
"""
    rec = extract_failures(stdout)
    assert rec["failing_tests"] == [
        "../tests/test_outputs.py::test_pmars_works",
        "../tests/test_outputs.py::test_headless_no_x11",
        "tests/harness.py",
    ]
    assert rec["last_error_line"] == "E       assert []"


def test_reference_failure_attaches_tests_and_error():
    stdout = (
        "E       ImportError: No module named warehouse.jobs\n"
        "FAILED tests/harness.py::test_resume - ImportError\n"
    )
    row = _row(reward=0.0, status="executed", test_stdout_tail=stdout)
    assert row["accepted"] is False
    assert row["failing_tests"] == ["tests/harness.py::test_resume"]
    assert "ImportError" in row["last_error_line"]


def test_passing_oracle_omits_failure_fields():
    row = _row(reward=1.0, status="executed")
    assert "failing_tests" not in row
    assert "last_error_line" not in row


def test_summary_rates_and_counts():
    rows = [
        _row(task_id="arcagi2-a", source_benchmark="arcagi2", probe="oracle", reward=1.0),
        _row(task_id="arcagi2-a", source_benchmark="arcagi2", probe="nop", intended="reject", reward=0.0),
        _row(task_id="hle-b", source_benchmark="hle", probe="oracle", reward=0.0, test_stdout_tail="FAILED t.py::test_x - boom\nE   boom"),
        _row(task_id="hle-b", source_benchmark="hle", probe="nop", intended="reject", reward=0.0),
        _row(task_id="gso-c", source_benchmark="gso", probe="oracle", status="no_reference", reward=None, elapsed_sec=0),
        _row(task_id="gso-c", source_benchmark="gso", probe="nop", intended="reject", reward=1.0),
        _row(task_id="tb-d", source_benchmark="tb", probe="oracle", status="infra", reward=None, stderr_tail="failed to pull"),
        _row(task_id="tb-d", source_benchmark="tb", probe="nop", intended="reject", status="timeout", reward=None),
        _row(task_id="bix-e", source_benchmark="bix", probe="oracle", status="not_run", reward=None, elapsed_sec=0),
        _row(task_id="bix-e", source_benchmark="bix", probe="nop", intended="reject", status="not_run", reward=None, elapsed_sec=0),
    ]
    s = summarize_rows(
        rows,
        wall_clock_total=99.5,
        n_tasks=5,
        n_with_reference=4,
    )
    assert s["n_tasks"] == 5
    assert s["n_with_reference"] == 4
    assert s["n_run"] == 4
    assert s["correct_accept"] == 0.5
    assert s["incorrect_reject"] == 2 / 3
    assert s["n_reference_fails"] == 1
    assert s["n_nop_passes"] == 1
    assert s["n_infra"] == 1
    assert s["n_timeout"] == 1
    assert s["n_no_reference"] == 1
    assert s["n_not_run"] == 1
    assert s["wall_clock_total"] == 99.5
    assert s["not_run"] == ["bix-e"]
    hle = s["by_source"]["hle"]
    assert hle["n_reference_fails"] == 1
    assert hle["correct_accept"] == 0.0
    gso = s["by_source"]["gso"]
    assert gso["n_nop_passes"] == 1
    assert gso["incorrect_reject"] == 0.0
    assert "eval_tasks_pilot" in s["comparison"]


def test_comparison_block_pilot_and_optional_tb21(tmp_path: Path):
    missing = comparison_block(tmp_path / "nope.json")
    assert missing["eval_tasks_pilot"] == {
        "n_tasks": 16,
        "n_reference_fails": 2,
        "n_ab_false_accepts": 0,
        "source": "data/gold/harbor_outlier_diagnosis.json",
    }
    assert missing["tb21_pairs"] is None
    tb = tmp_path / "tb21_pairs.summary.json"
    tb.write_text(
        '{"n_tasks": 28, "n_trials": 6, "n_pairs_diffable": 1, "n_separated": 0,'
        ' "n_infra": 0, "n_timeout": 0, "wall_clock_total": 12.0,'
        ' "tasks": {"a": {"false_reject_pre": true, "false_accept_pre": false}}}',
        encoding="utf-8",
    )
    present = comparison_block(tb)
    assert present["tb21_pairs"]["n_tasks"] == 28
    assert present["tb21_pairs"]["n_trials"] == 6
    assert present["tb21_pairs"]["n_false_reject_pre"] == 1
    assert present["tb21_pairs"]["complete"] is False
