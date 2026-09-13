import json
import tarfile
from pathlib import Path

import pytest

from task_validation.evidence import generator_gate as gg
from task_validation.evidence.tb21_pairs import append_jsonl, load_existing_rows
from task_validation.sampling.estimators import hypergeometric_upper


TASK_TOML = '[task]\nname = "{name}"\n\n[verifier]\ntimeout_sec = 60\n'


def _mk_task(root: Path, name: str, *, reference: bool = True) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "task.toml").write_text(TASK_TOML.format(name=name), encoding="utf-8")
    (d / "environment").mkdir()
    (d / "environment" / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (d / "tests").mkdir()
    (d / "tests" / "test.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if reference:
        (d / "solution").mkdir()
        (d / "solution" / "solve.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    return d


def _tar_of(stage: Path, tar_path: Path, members: list[str]) -> Path:
    for member in members:
        _mk_task(stage, member)
    with tarfile.open(tar_path, "w") as tf:
        for member in members:
            tf.add(stage / member, arcname=member)
    return tar_path


def _fake_root(tmp_path: Path) -> Path:
    """Two on-disk Harbor task dirs plus one task living inside a tar."""
    root = tmp_path / "gen"
    _mk_task(root, "alpha-task")
    _mk_task(root, "beta-task")
    _tar_of(tmp_path / "tarsrc", root / "tasks-0.tar", ["gamma-task"])
    return root


class FakeRunner:
    """Stands in for run_gate_trial; never touches harbor or docker."""

    def __init__(self, rewards: dict | None = None):
        self.calls: list[tuple[str, str, str]] = []
        self.rewards = rewards or {}

    def __call__(self, task_dir, agent, jobs_out, name):
        self.calls.append((str(task_dir), agent, name))
        reward = self.rewards.get((Path(task_dir).name, agent), 1.0 if agent == "oracle" else 0.0)
        return {
            "status": "executed",
            "reward": reward,
            "elapsed_sec": 0.01,
            "stderr_tail": "",
            "test_stdout_tail": "ok",
            "skip_reason": None,
        }


class FakeMaintenance:
    def __init__(self):
        self.rm_calls: list[str] = []
        self.prunes = 0

    def rm_task_containers(self, task_dir):
        self.rm_calls.append(str(task_dir))
        return []

    def prune(self):
        self.prunes += 1
        return {"image_bytes": 1024, "builder_bytes": 2048}


def test_enumerate_tasks_finds_dirs_and_tar_members(tmp_path: Path):
    root = _fake_root(tmp_path)
    entries = gg.enumerate_tasks(root)
    by_id = {e["task_id"]: e for e in entries}
    assert sorted(by_id) == ["alpha-task", "beta-task", "gamma-task"]
    assert by_id["alpha-task"]["kind"] == "dir"
    assert by_id["gamma-task"]["kind"] == "tar"
    assert by_id["gamma-task"]["member"] == "gamma-task"
    # Enumeration reads member names only: nothing is unpacked.
    assert not (tmp_path / "gen-gate-extract").exists()


def test_sampling_deterministic_and_prefix_stable(tmp_path: Path):
    root = _fake_root(tmp_path)
    out = tmp_path / "manifest.json"
    extract = tmp_path / "extract"
    m2 = gg.sample_generator(
        name="fake", root=root, n=2, seed="s0", out_path=out, extract_dir=extract
    )
    assert m2["N"] == 3
    assert m2["n"] == 2
    assert m2["seed"] == "s0"
    assert len(m2["ids"]) == 2
    for tid, meta in m2["tasks"].items():
        assert Path(meta["path"]).is_dir()
        assert len(meta["sha256"]) == 64

    # Re-running at the same n returns the frozen manifest unchanged.
    again = gg.sample_generator(
        name="fake", root=root, n=2, seed="s0", out_path=out, extract_dir=extract
    )
    assert again["ids"] == m2["ids"]

    # Growing to n=3 with the same seed keeps the frozen prefix.
    m3 = gg.sample_generator(
        name="fake", root=root, n=3, seed="s0", out_path=out, extract_dir=extract
    )
    assert m3["ids"][:2] == m2["ids"]
    assert m3["n"] == 3


def test_sampling_rejects_seed_change_and_shrink(tmp_path: Path):
    root = _fake_root(tmp_path)
    out = tmp_path / "manifest.json"
    extract = tmp_path / "extract"
    gg.sample_generator(name="fake", root=root, n=2, seed="s0", out_path=out, extract_dir=extract)
    with pytest.raises(ValueError, match="frozen under seed"):
        gg.sample_generator(name="fake", root=root, n=3, seed="other", out_path=out, extract_dir=extract)
    with pytest.raises(ValueError, match="refusing to shrink"):
        gg.sample_generator(name="fake", root=root, n=1, seed="s0", out_path=out, extract_dir=extract)


def test_tar_task_extracted_only_when_sampled(tmp_path: Path):
    root = _fake_root(tmp_path)
    extract = tmp_path / "extract"
    out = tmp_path / "manifest.json"
    m = gg.sample_generator(
        name="fake", root=root, n=3, seed="s0", out_path=out, extract_dir=extract
    )
    meta = m["tasks"]["gamma-task"]
    assert meta["source"] == "tar"
    assert Path(meta["path"]).is_dir()
    assert (Path(meta["path"]) / "task.toml").is_file()
    assert meta["path"].startswith(str(extract))
    # Only the sampled member was unpacked: the tar itself is untouched and no
    # extra task dirs exist under the extract root.
    extracted = {p.name for p in extract.rglob("task.toml")}
    assert extracted == {"task.toml"}
    assert len(list(extract.rglob("task.toml"))) == 1


def test_manifest_ids_cover_full_population(tmp_path: Path):
    root = _fake_root(tmp_path)
    ids = [e["task_id"] for e in gg.enumerate_tasks(root)]
    drawn = gg.draw_sample_ids(ids, 2, "s0")
    assert len(drawn) == 2
    assert len(set(drawn)) == 2
    assert set(drawn) <= set(ids)
    with pytest.raises(ValueError):
        gg.draw_sample_ids(ids, 4, "s0")


def _run_manifest(tmp_path: Path, ids: list[str], N: int) -> Path:
    tasks = {}
    for tid in ids:
        d = _mk_task(tmp_path / "tasks", tid)
        tasks[tid] = {
            "path": str(d),
            "sha256": gg.dir_sha256(d),
            "source": "dir",
        }
    manifest = {
        "design": gg.DESIGN,
        "generator": "fake",
        "root": str(tmp_path / "tasks"),
        "N": N,
        "n": len(ids),
        "seed": "s0",
        "ids": ids,
        "tasks": tasks,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_run_gate_writes_rows_and_certificate(tmp_path: Path):
    manifest_path = _run_manifest(tmp_path, ["alpha-task", "beta-task"], N=100)
    out = tmp_path / "rows.jsonl"
    runner = FakeRunner()
    maint = FakeMaintenance()
    summary = gg.run_gate(
        manifest_path=manifest_path,
        out_path=out,
        jobs_dir=tmp_path / "jobs",
        concurrency=2,
        k=2,
        trial_runner=runner,
        maintenance=maint,
    )
    rows = load_existing_rows(out)
    assert len(rows) == 8  # 2 tasks x 2 probes x 2 reps
    assert len(runner.calls) == 8
    assert {r["status"] for r in rows} == {"executed"}
    assert all(r["label_protocol"] == gg.PROTOCOL for r in rows)
    assert all(r["grade"] == "A" for r in rows)
    assert all(r["verifier_kind"] == "execution" for r in rows)

    cert = json.loads(gg.certificate_path_for(out).read_text())
    assert cert["complete"] is True
    assert cert["k_invalid"] == 0
    assert cert["n"] == 2
    assert cert["N"] == 100
    assert cert["method"] == "hypergeometric-one-sided"
    assert cert["ucb95"] == pytest.approx(hypergeometric_upper(0, 2, 100, alpha=0.05))
    assert cert["label_protocol"] == gg.PROTOCOL
    assert cert["adjudicator"] == "machine"
    assert summary["n_invalid"] == 0
    assert summary["n_valid"] == 2
    assert maint.rm_calls and maint.prunes >= 0


def test_run_gate_resume_skips_terminal_trials(tmp_path: Path):
    manifest_path = _run_manifest(tmp_path, ["alpha-task", "beta-task"], N=100)
    out = tmp_path / "rows.jsonl"
    # Pre-seed one finished trial; resume must not re-run it.
    append_jsonl(
        out,
        gg.build_trial_row(
            task_id="alpha-task",
            probe="oracle",
            rep=0,
            reward=1.0,
            status="executed",
            elapsed_sec=0.5,
        ),
    )
    runner = FakeRunner()
    gg.run_gate(
        manifest_path=manifest_path,
        out_path=out,
        jobs_dir=tmp_path / "jobs",
        concurrency=2,
        k=2,
        trial_runner=runner,
        maintenance=FakeMaintenance(),
    )
    assert len(runner.calls) == 7
    assert len(load_existing_rows(out)) == 8
    cert = json.loads(gg.certificate_path_for(out).read_text())
    assert cert["k_invalid"] == 0
    assert cert["complete"] is True


def test_invalid_verdict_and_infra_exclusion(tmp_path: Path):
    manifest_path = _run_manifest(tmp_path, ["alpha-task", "beta-task", "gamma-task"], N=100)
    out = tmp_path / "rows.jsonl"

    def runner(task_dir, agent, jobs_out, name):
        name_ = Path(task_dir).name
        if name_ == "gamma-task":
            return {
                "status": "infra",
                "reward": None,
                "elapsed_sec": 1.0,
                "stderr_tail": "failed to pull image",
                "test_stdout_tail": "",
                "skip_reason": "environment_build_exceeded_cap",
            }
        reward = 1.0 if agent == "oracle" else 0.0
        if name_ == "beta-task" and agent == "nop":
            reward = 1.0  # nop false accept
        return {
            "status": "executed",
            "reward": reward,
            "elapsed_sec": 0.01,
            "stderr_tail": "",
            "test_stdout_tail": "",
            "skip_reason": None,
        }

    summary = gg.run_gate(
        manifest_path=manifest_path,
        out_path=out,
        jobs_dir=tmp_path / "jobs",
        concurrency=2,
        k=2,
        trial_runner=runner,
        maintenance=FakeMaintenance(),
    )
    cert = json.loads(gg.certificate_path_for(out).read_text())
    # beta-task is invalid; gamma-task is infra only, so unadjudicated.
    assert summary["n_invalid"] == 1
    assert summary["n_infra_tasks"] == 1
    assert cert["complete"] is False
    assert cert["decision"] == "incomplete"
    assert "gamma-task" in cert["unadjudicated"]
    assert cert["n_unadjudicated"] == 1


def test_certificate_ucb_matches_hypergeometric_upper(tmp_path: Path):
    manifest_path = _run_manifest(tmp_path, ["alpha-task", "beta-task", "gamma-task"], N=200)
    out = tmp_path / "rows.jsonl"

    def runner(task_dir, agent, jobs_out, name):
        name_ = Path(task_dir).name
        reward = 1.0 if agent == "oracle" else 0.0
        if name_ == "gamma-task" and agent == "oracle":
            reward = 0.0  # oracle fails own verifier once -> invalid
        return {
            "status": "executed",
            "reward": reward,
            "elapsed_sec": 0.01,
            "stderr_tail": "",
            "test_stdout_tail": "",
            "skip_reason": None,
        }

    gg.run_gate(
        manifest_path=manifest_path,
        out_path=out,
        jobs_dir=tmp_path / "jobs",
        concurrency=2,
        k=2,
        trial_runner=runner,
        maintenance=FakeMaintenance(),
    )
    cert = json.loads(gg.certificate_path_for(out).read_text())
    assert cert["complete"] is True
    assert cert["k_invalid"] == 1
    assert cert["p_hat"] == pytest.approx(1 / 3)
    assert cert["ucb95"] == pytest.approx(hypergeometric_upper(1, 3, 200, alpha=0.05))
    assert cert["method"] == "hypergeometric-one-sided"
    assert [f["unit_id"] for f in cert["flagged"]] == ["gamma-task"]


def test_parse_reclaimed_bytes():
    assert gg.parse_reclaimed_bytes("Total reclaimed space: 1.5GB") == 1_500_000_000
    assert gg.parse_reclaimed_bytes("Total reclaimed space: 512MiB") == 512 * 1024 * 1024
    assert gg.parse_reclaimed_bytes("Total reclaimed space: 0B") == 0
    assert gg.parse_reclaimed_bytes("nothing reclaimed") == 0


def test_slug_for():
    assert gg.slug_for("sub/dir task#1") == "sub-dir-task-1"
    assert gg.slug_for("alpha-task") == "alpha-task"
