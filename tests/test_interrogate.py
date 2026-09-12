from pathlib import Path

from task_validation.evidence.interrogate import (
    ProbeSpec,
    apply_probe,
    discrimination_rates,
    probe_catalog,
    task_kind,
)


def _hello(tmp: Path) -> Path:
    task = tmp / "hello-world"
    (task / "environment").mkdir(parents=True)
    (task / "solution").mkdir()
    (task / "tests").mkdir()
    (task / "instruction.md").write_text(
        "Create a file called `/app/hello.txt` with `Hello, world!` as the content.\n",
        encoding="utf-8",
    )
    (task / "solution" / "solve.sh").write_text(
        "#!/bin/bash\nprintf 'Hello, world!\\n' > /app/hello.txt\n",
        encoding="utf-8",
    )
    (task / "environment" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    return task


def _week(tmp: Path) -> Path:
    task = tmp / "week-hours"
    (task / "environment").mkdir(parents=True)
    (task / "solution").mkdir()
    (task / "tests").mkdir()
    (task / "instruction.md").write_text("Repair the timesheet under `/app/`.\n", encoding="utf-8")
    (task / "environment" / "clock.py").write_text("broken = True\n", encoding="utf-8")
    (task / "environment" / "timesheet.py").write_text("broken = True\n", encoding="utf-8")
    (task / "solution" / "clock.py").write_text("broken = False\n", encoding="utf-8")
    (task / "solution" / "timesheet.py").write_text("broken = False\n", encoding="utf-8")
    (task / "solution" / "solve.sh").write_text(
        "#!/bin/bash\ncp /solution/clock.py /app/clock.py\ncp /solution/timesheet.py /app/timesheet.py\n",
        encoding="utf-8",
    )
    return task


def test_hello_kind_and_catalog_includes_spec_probes(tmp_path: Path):
    task = _hello(tmp_path)
    assert task_kind(task) == "hello-world"
    ids = {p.probe_id for p in probe_catalog(task)}
    assert {"reference", "preserve_echo", "alter_output", "break_case", "strip_spaces", "nop"} <= ids
    observe = [p for p in probe_catalog(task) if p.intended == "observe"]
    assert observe and observe[0].probe_id == "strip_spaces"


def test_hello_equivalent_and_wrong_output(tmp_path: Path):
    task = _hello(tmp_path)
    apply_probe(task, ProbeSpec("preserve_echo", "preserve", "accept", "oracle", "hello_echo", ""))
    text = (task / "solution" / "solve.sh").read_text(encoding="utf-8")
    assert "echo 'Hello, world!'" in text
    apply_probe(task, ProbeSpec("alter_output", "alter_output", "reject", "oracle", "hello_goodbye", ""))
    text = (task / "solution" / "solve.sh").read_text(encoding="utf-8")
    assert "Goodbye" in text


def test_drop_last_copy_leaves_one_required_file(tmp_path: Path):
    task = _week(tmp_path)
    apply_probe(task, ProbeSpec("remove_required", "remove_required", "reject", "oracle", "drop_last_apply", ""))
    text = (task / "solution" / "solve.sh").read_text(encoding="utf-8")
    assert "clock.py" in text
    assert "timesheet.py" not in text


def test_drop_last_install_line(tmp_path: Path):
    from task_validation.evidence.interrogate import drop_last_apply

    text = (
        "#!/bin/bash\n"
        "install -D -m 0644 a.py /app/a.py\n"
        "install -D -m 0644 b.py /app/b.py\n"
    )
    out = drop_last_apply(text)
    assert "a.py" in out
    assert "b.py" not in out


def test_complete_packages_skips_harness_fixtures(tmp_path: Path):
    from task_validation.evidence.interrogate import complete_packages

    def _pkg(d: Path) -> None:
        (d / "environment").mkdir(parents=True)
        (d / "solution").mkdir()
        (d / "tests").mkdir()
        (d / "instruction.md").write_text("x\n", encoding="utf-8")
        (d / "task.toml").write_text("[task]\nname='t'\n", encoding="utf-8")
        (d / "environment" / "Dockerfile").write_text("FROM x\n", encoding="utf-8")
        (d / "tests" / "test.sh").write_text("echo 0\n", encoding="utf-8")
        (d / "solution" / "solve.sh").write_text("#!/bin/bash\n", encoding="utf-8")

    real = tmp_path / "tasks" / "real-one"
    planted = tmp_path / "scripts" / "checks" / "test-tasks" / "fail-static-canary"
    _pkg(real)
    _pkg(planted)
    found = {p.name for p in complete_packages(tmp_path)}
    assert "real-one" in found
    assert "fail-static-canary" not in found


def test_week_marks_equivalent_and_boundary_unavailable(tmp_path: Path):
    task = _week(tmp_path)
    by = {p.family: p for p in probe_catalog(task)}
    assert by["preserve_equivalent"].availability == "unavailable"
    assert by["alter_output"].availability == "unavailable"
    assert by["break_boundary"].availability == "unavailable"
    assert by["revert_gold"].availability == "runnable"


def test_revert_replaces_solution_with_env(tmp_path: Path):
    task = _week(tmp_path)
    ids = {p.probe_id for p in probe_catalog(task)}
    assert "revert_gold" in ids
    apply_probe(task, ProbeSpec("revert_gold", "revert_gold", "reject", "oracle", "revert_env", ""))
    assert (task / "solution" / "clock.py").read_text(encoding="utf-8") == "broken = True\n"


def test_rates_uncollapsed_and_observe_excluded():
    trials = [
        {"family": "reference", "intended": "accept", "reward": 1.0},
        {"family": "preserve", "intended": "accept", "reward": 1.0},
        {"family": "preserve", "intended": "accept", "reward": 0.0},
        {"family": "nop", "intended": "reject", "reward": 0.0},
        {"family": "alter_output", "intended": "reject", "reward": 1.0},
        {"family": "observe", "intended": "observe", "reward": 1.0},
        {"family": "nop", "intended": "reject", "reward": None},
    ]
    r = discrimination_rates(trials)
    assert r["correct_accept_rate"] == 1.0
    assert r["legitimate_variant_accept_rate"] == 0.5
    assert r["false_accept_rate"] == 0.5
    assert r["incorrect_reject_rate"] == 0.5
    assert r["false_reject_rate"] == (1 / 3)
    assert r["n_negative"] == 2
    assert r["n_failed_to_execute"] == 1
    assert r["interrogable"] is True
    assert "score" not in r
