from pathlib import Path

from task_validation.evidence.tb21_pairs import (
    build_trial_row,
    classify_task,
    heavy_skip_reason,
    intended_for_probe,
    ordered_task_ids,
    parse_memory_mb,
    resource_values_changed,
    sort_key,
    summarize_rows,
    tail_lines,
)


def _toml(memory: str | None = "2G", memory_mb: int | None = None, extra: str = "") -> str:
    mem_line = f'memory = "{memory}"\n' if memory else ""
    mb_line = f"memory_mb = {memory_mb}\n" if memory_mb is not None else ""
    return (
        "[verifier]\ntimeout_sec = 900.0\n"
        "[agent]\ntimeout_sec = 900.0\n"
        "[environment]\n"
        "cpus = 1\n"
        f"{mem_line}{mb_line}"
        "gpus = 0\n"
        f"{extra}"
    )


def _task(root: Path, name: str, *, instruction: str = "do x\n", tests: str = "assert 1\n", solution: str = "#!/bin/bash\n", dockerfile: str = "FROM x\n", toml: str | None = None) -> Path:
    d = root / name
    (d / "environment").mkdir(parents=True)
    (d / "solution").mkdir()
    (d / "tests").mkdir()
    (d / "instruction.md").write_text(instruction, encoding="utf-8")
    (d / "tests" / "test_outputs.py").write_text(tests, encoding="utf-8")
    (d / "solution" / "solve.sh").write_text(solution, encoding="utf-8")
    (d / "environment" / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    (d / "task.toml").write_text(toml or _toml(), encoding="utf-8")
    return d


def _row(**kwargs):
    base = dict(
        task_id="demo",
        version="pre",
        commit="abc",
        probe="oracle",
        reward=1.0,
        status="executed",
        elapsed_sec=10.0,
        test_stdout_tail="ok",
        change_class="test_fix",
        change_classes=["test_fix"],
        files_differ_list=["tests/test_outputs.py"],
    )
    base.update(kwargs)
    return build_trial_row(**base)


def test_instruction_is_misspec(tmp_path: Path):
    pre = _task(tmp_path / "pre", "t")
    post = _task(tmp_path / "post", "t", instruction="do y\n")
    rec = classify_task(pre, post)
    assert rec["change_classes"] == ["misspec"]
    assert rec["change_class"] == "misspec"
    assert rec["files_differ"] == ["instruction.md"]


def test_tests_dir_is_test_fix(tmp_path: Path):
    pre = _task(tmp_path / "pre", "t")
    post = _task(tmp_path / "post", "t", tests="assert 2\n")
    rec = classify_task(pre, post)
    assert rec["change_classes"] == ["test_fix"]
    assert rec["change_class"] == "test_fix"


def test_solution_is_solution_fix(tmp_path: Path):
    pre = _task(tmp_path / "pre", "t")
    post = _task(tmp_path / "post", "t", solution="#!/bin/bash\necho 1\n")
    rec = classify_task(pre, post)
    assert rec["change_classes"] == ["solution_fix"]
    assert rec["change_class"] == "solution_fix"


def test_dockerfile_is_docker_env(tmp_path: Path):
    pre = _task(tmp_path / "pre", "t")
    post = _task(tmp_path / "post", "t", dockerfile="FROM y\n")
    rec = classify_task(pre, post)
    assert rec["change_classes"] == ["docker_env"]
    assert rec["change_class"] == "docker_env"


def test_toml_only_is_resource_timeout(tmp_path: Path):
    pre = _task(tmp_path / "pre", "t", toml=_toml(memory="2G"))
    post = _task(tmp_path / "post", "t", toml=_toml(memory=None, memory_mb=2048))
    rec = classify_task(pre, post)
    assert rec["files_differ"] == ["task.toml"]
    assert rec["change_classes"] == ["resource_timeout"]
    assert rec["change_class"] == "resource_timeout"
    assert rec["resource_only"] is True


def test_real_memory_bump_with_other_class(tmp_path: Path):
    pre = _task(tmp_path / "pre", "t", toml=_toml(memory="4G"), instruction="old\n")
    post = _task(tmp_path / "post", "t", toml=_toml(memory=None, memory_mb=8192), instruction="new\n")
    rec = classify_task(pre, post)
    assert "misspec" in rec["change_classes"]
    assert "resource_timeout" in rec["change_classes"]


def test_schema_only_toml_does_not_add_resource_when_tests_changed(tmp_path: Path):
    pre = _task(tmp_path / "pre", "t", toml=_toml(memory="2G"), tests="a\n")
    post = _task(tmp_path / "post", "t", toml=_toml(memory=None, memory_mb=2048), tests="b\n")
    rec = classify_task(pre, post)
    assert rec["change_classes"] == ["test_fix"]
    assert "resource_timeout" not in rec["change_classes"]


def test_ignores_gitignore_and_readme(tmp_path: Path):
    pre = _task(tmp_path / "pre", "t")
    post = _task(tmp_path / "post", "t")
    (post / ".gitignore").write_text("*\n", encoding="utf-8")
    (post / "README.md").write_text("hi\n", encoding="utf-8")
    rec = classify_task(pre, post)
    assert rec["no_change"] is True
    assert rec["change_classes"] == []
    assert rec["change_class"] == "none"


def test_multiple_classes(tmp_path: Path):
    pre = _task(tmp_path / "pre", "t")
    post = _task(
        tmp_path / "post",
        "t",
        instruction="new\n",
        tests="new\n",
        solution="new\n",
        dockerfile="FROM z\n",
        toml=_toml(memory=None, memory_mb=8192, extra="cpus = 4\n"),
    )
    rec = classify_task(pre, post)
    assert rec["change_classes"] == ["test_fix", "solution_fix", "misspec", "docker_env", "resource_timeout"]
    assert rec["change_class"] == "test_fix"


def test_parse_memory_units():
    assert parse_memory_mb({"environment.memory": "2G"}) == 2048
    assert parse_memory_mb({"environment.memory_mb": "8192"}) == 8192
    assert parse_memory_mb({"environment.memory": "4Gi"}) == 4096
    assert resource_values_changed(
        {"environment.memory": "4G"},
        {"environment.memory_mb": "8192"},
    )
    assert not resource_values_changed(
        {"environment.memory": "2G"},
        {"environment.memory_mb": "2048"},
    )


def test_sort_priority_order():
    items = [
        {"task_id": "r", "change_classes": ["resource_timeout"]},
        {"task_id": "m", "change_classes": ["misspec"]},
        {"task_id": "t", "change_classes": ["test_fix", "misspec"]},
        {"task_id": "d", "change_classes": ["docker_env"]},
        {"task_id": "s", "change_classes": ["solution_fix"]},
        {"task_id": "n", "change_classes": []},
    ]
    ranked = sorted(items, key=sort_key)
    assert [x["task_id"] for x in ranked] == ["s", "t", "m", "d", "r", "n"]
    by = {x["task_id"]: x for x in items}
    assert ordered_task_ids(by) == ["s", "t", "m", "d", "r", "n"]


def test_heavy_skip_gpu_and_memory(tmp_path: Path):
    gpu = _task(tmp_path, "gpu", toml=_toml(memory="2G", extra="gpus = 1\n"))
    fat = _task(tmp_path, "fat", toml=_toml(memory=None, memory_mb=32768))
    ok = _task(tmp_path, "ok", toml=_toml(memory="8G"))
    assert heavy_skip_reason(gpu) == "gpu=1"
    assert heavy_skip_reason(fat) == "memory_mb=32768>16384"
    assert heavy_skip_reason(ok) is None


def test_timeout_never_becomes_reward_zero():
    row = _row(reward=0.0, status="timeout", probe="oracle")
    assert row["status"] == "timeout"
    assert row["reward"] is None
    assert row["accepted"] is None
    assert row["intended"] == "accept"


def test_executed_zero_is_kept():
    row = _row(reward=0.0, status="executed", probe="oracle")
    assert row["reward"] == 0.0
    assert row["accepted"] is False


def test_nop_intended_reject():
    assert intended_for_probe("nop") == "reject"
    row = _row(probe="nop", reward=0.0, status="executed")
    assert row["intended"] == "reject"
    assert row["accepted"] is False


def test_row_stdout_tail_passthrough():
    text = "\n".join(f"L{i}" for i in range(50))
    row = _row(test_stdout_tail=tail_lines(text, 40))
    assert row["test_stdout_tail"].startswith("L10")
    assert row["test_stdout_tail"].endswith("L49")
    assert len(row["test_stdout_tail"].splitlines()) == 40


def test_summary_separated_pre_false_reject():
    cls = {
        "demo": {
            "files_differ": ["tests/a.py"],
            "change_classes": ["test_fix"],
            "change_class": "test_fix",
            "resource_only": False,
            "no_change": False,
        }
    }
    rows = [
        _row(version="pre", probe="oracle", reward=0.0),
        _row(version="pre", probe="nop", reward=0.0),
        _row(version="post", probe="oracle", reward=1.0),
        _row(version="post", probe="nop", reward=0.0),
    ]
    s = summarize_rows(rows, cls, wall_clock_total=12.5)
    t = s["tasks"]["demo"]
    assert t["false_reject_pre"] is True
    assert t["false_reject_post"] is False
    assert t["false_accept_pre"] is False
    assert t["false_accept_post"] is False
    assert t["separated"] is True
    assert s["n_separated"] == 1
    assert s["n_pairs_diffable"] == 1
    assert s["wall_clock_total"] == 12.5


def test_summary_false_accept_pre():
    cls = {
        "demo": {
            "files_differ": ["tests/a.py"],
            "change_classes": ["test_fix"],
            "change_class": "test_fix",
            "resource_only": False,
            "no_change": False,
        }
    }
    rows = [
        _row(version="pre", probe="oracle", reward=1.0),
        _row(version="pre", probe="nop", reward=1.0),
        _row(version="post", probe="oracle", reward=1.0),
        _row(version="post", probe="nop", reward=0.0),
    ]
    t = summarize_rows(rows, cls, wall_clock_total=1)["tasks"]["demo"]
    assert t["false_accept_pre"] is True
    assert t["false_accept_post"] is False
    assert t["separated"] is True


def test_resource_only_pre_oracle_pass_not_separated_or_clean():
    cls = {
        "demo": {
            "files_differ": ["task.toml"],
            "change_classes": ["resource_timeout"],
            "change_class": "resource_timeout",
            "resource_only": True,
            "no_change": False,
        }
    }
    rows = [
        _row(version="pre", probe="oracle", reward=1.0, change_class="resource_timeout", change_classes=["resource_timeout"]),
        _row(version="pre", probe="nop", reward=0.0, change_class="resource_timeout", change_classes=["resource_timeout"]),
        _row(version="post", probe="oracle", reward=1.0, change_class="resource_timeout", change_classes=["resource_timeout"]),
        _row(version="post", probe="nop", reward=0.0, change_class="resource_timeout", change_classes=["resource_timeout"]),
    ]
    s = summarize_rows(rows, cls, wall_clock_total=3)
    t = s["tasks"]["demo"]
    assert t["false_reject_pre"] is False
    assert t["separated"] is False
    assert t["counterfactual_reproducible"] is False
    assert t["pre_oracle_pass"] is True
    assert s["n_separated"] == 0
    assert s["n_resource_not_reproducible"] == 1
    assert s["n_no_change"] == 0


def test_timeout_is_not_false_reject():
    cls = {
        "demo": {
            "files_differ": ["tests/a.py"],
            "change_classes": ["test_fix"],
            "change_class": "test_fix",
            "resource_only": False,
            "no_change": False,
        }
    }
    rows = [
        _row(version="pre", probe="oracle", reward=None, status="timeout"),
        _row(version="pre", probe="nop", reward=0.0),
        _row(version="post", probe="oracle", reward=1.0),
        _row(version="post", probe="nop", reward=0.0),
    ]
    t = summarize_rows(rows, cls, wall_clock_total=1)["tasks"]["demo"]
    assert t["false_reject_pre"] is None
    assert t["separated"] is False
    assert t["timeout"] is True


def test_infra_and_no_change_counts():
    cls = {
        "a": {
            "files_differ": [],
            "change_classes": [],
            "change_class": "none",
            "resource_only": False,
            "no_change": True,
        },
        "b": {
            "files_differ": ["tests/a.py"],
            "change_classes": ["test_fix"],
            "change_class": "test_fix",
            "resource_only": False,
            "no_change": False,
        },
    }
    rows = [
        _row(task_id="b", version="pre", probe="oracle", reward=None, status="infra"),
        _row(task_id="b", version="pre", probe="nop", reward=None, status="infra"),
        _row(task_id="b", version="post", probe="oracle", reward=1.0),
        _row(task_id="b", version="post", probe="nop", reward=0.0),
    ]
    s = summarize_rows(rows, cls, wall_clock_total=9)
    assert s["n_no_change"] == 1
    assert s["n_infra"] == 1
    assert s["n_pairs_diffable"] == 0
    assert s["n_tasks"] == 2
