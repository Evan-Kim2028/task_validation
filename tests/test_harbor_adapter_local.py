import hashlib
import io
import json
import tarfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from task_validation.cli import main as cli_main
from task_validation.ingest.harbor_adapter_local import FUNNEL_KEYS, run_extract_local


def _tgz(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _result(task_name: str, agent: str, model: str, **kw) -> bytes:
    res = {
        "id": "x",
        "task_name": task_name,
        "started_at": "2026-04-14T11:19:53.702502Z",
        "finished_at": "2026-04-14T11:21:29.088552Z",
        "exception_info": kw.get("exception_info"),
        "agent_info": {"name": agent, "model_info": {"name": model}},
        "agent_result": {
            "n_input_tokens": 10,
            "n_cache_tokens": 4,
            "n_output_tokens": 6,
            "cost_usd": 0.01,
        },
        "verifier_result": {"rewards": {"reward": kw.get("reward")}},
    }
    return json.dumps(res).encode()


def _build_fixture(tmp_path: Path) -> dict:
    manifest = tmp_path / "manifest.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "benchmark": "codepde",
                    "task_name": "codepde/t1",
                    "agent": "terminus-2",
                    "model": "gpt-5.4",
                    "trial_ids": ["tid-other", "tid-in"],
                },
                {
                    "benchmark": "other-bench",
                    "task_name": "other-bench/t1",
                    "agent": "codex",
                    "model": "gpt-5.4",
                    "trial_ids": ["tid-foreign"],
                },
            ],
            schema=pa.schema(
                [
                    ("benchmark", pa.string()),
                    ("task_name", pa.string()),
                    ("agent", pa.string()),
                    ("model", pa.string()),
                    ("trial_ids", pa.list_(pa.string())),
                ]
            ),
        ),
        manifest,
    )
    adapters = tmp_path / "adapters.json"
    adapters.write_text(json.dumps({"adapters": [{"benchmark": "codepde"}]}))

    arch_in = _tgz(
        {
            "trial-in/result.json": _result("codepde/t1", "terminus-2", "gpt-5.4", reward=0.0),
            "trial-in/verifier/reward.txt": b"1.0\n",
            "trial-in/agent/stdout.log": b"hello",
        }
    )
    arch_out = _tgz(
        {
            "trial-out/result.json": _result(
                "codepde/t9",
                "openhands",
                "gpt-5-nano",
                reward=0.5,
                exception_info={"exception_type": "AgentTimeout"},
            ),
        }
    )
    shard = tmp_path / "dump" / "data" / "harbor_adapters" / "codepde" / "00000.parquet"
    shard.parent.mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "trial_id": "tid-in",
                    "archive": arch_in,
                    "archive_sha256": hashlib.sha256(arch_in).hexdigest(),
                },
                {
                    "trial_id": "tid-out",
                    "archive": arch_out,
                    "archive_sha256": hashlib.sha256(arch_out).hexdigest(),
                },
            ],
            schema=pa.schema(
                [
                    ("trial_id", pa.string()),
                    ("archive", pa.binary()),
                    ("archive_sha256", pa.string()),
                ]
            ),
        ),
        shard,
    )
    return {
        "dump": tmp_path / "dump",
        "manifest": manifest,
        "adapters": adapters,
        "out": tmp_path / "out",
        "arch_in_sha": hashlib.sha256(arch_in).hexdigest(),
    }


def test_extract_local_end_to_end_and_resume(tmp_path: Path):
    fx = _build_fixture(tmp_path)
    report = run_extract_local(
        dump_dir=fx["dump"],
        manifest_path=fx["manifest"],
        adapters_path=fx["adapters"],
        out_dir=fx["out"],
        workers=1,
    )
    assert report["n_shards"] == 1 and report["n_shards_processed"] == 1
    assert report["n_rows"] == 2 and report["n_in_scope"] == 1 and report["n_funnel_rows"] == 1
    assert report["rows_per_benchmark"] == {"codepde": 2}
    assert report["n_distinct_task_pairs"] == 2
    assert report["n_in_scope_pairs"] == 1

    trials = {
        r["trial_id"]: r
        for r in (json.loads(x) for x in (fx["out"] / "harbor_adapter_trials.jsonl").read_text().splitlines())
    }
    row = trials["tid-in"]
    assert row["benchmark"] == "codepde" and row["task_name"] == "codepde/t1"
    assert row["agent"] == "terminus-2" and row["model"] == "gpt-5.4"
    assert row["trial_index"] == 1
    assert row["reward"] == 1.0  # verifier/reward.txt wins over result.json 0.0
    assert row["started_at"] == "2026-04-14T11:19:53.702502Z"
    assert row["finished_at"] == "2026-04-14T11:21:29.088552Z"
    assert row["n_input_tokens"] == 10 and row["n_cache_tokens"] == 4
    assert row["n_output_tokens"] == 6 and row["cost_usd"] == 0.01
    assert row["exception"] is False and row["error"] is None
    assert row["in_scope"] is True
    assert row["archive_sha256"] == fx["arch_in_sha"]
    assert row["shard"] == "data/harbor_adapters/codepde/00000.parquet"
    assert "result" not in row

    out_row = trials["tid-out"]
    assert out_row["in_scope"] is False
    assert out_row["task_name"] == "codepde/t9"  # fell back to result.json
    assert out_row["agent"] == "openhands" and out_row["model"] == "gpt-5-nano"
    assert out_row["trial_index"] is None
    assert out_row["reward"] == 0.5  # verifier_result fallback, no reward.txt
    assert out_row["exception"] is True

    funnel_lines = (fx["out"] / "harbor_funnel_rewards.jsonl").read_text().splitlines()
    assert len(funnel_lines) == 1
    frow = json.loads(funnel_lines[0])
    assert sorted(frow.keys()) == sorted(FUNNEL_KEYS)
    assert frow["trial_id"] == "tid-in" and frow["trial_index"] == 1
    assert frow["reward"] == 1.0 and frow["result"]["task_name"] == "codepde/t1"
    assert frow["shard"] == "data/harbor_adapters/codepde/00000.parquet"

    summary = json.loads((fx["out"] / "harbor_adapter_trials.summary.json").read_text())
    assert summary["n_rows"] == 2 and summary["n_in_scope"] == 1

    # Resume: part file exists, shard is skipped, outputs identical.
    before = (fx["out"] / "harbor_adapter_trials.jsonl").read_bytes()
    report2 = run_extract_local(
        dump_dir=fx["dump"],
        manifest_path=fx["manifest"],
        adapters_path=fx["adapters"],
        out_dir=fx["out"],
        workers=1,
    )
    assert report2["n_shards_processed"] == 0 and report2["n_shards_done_before"] == 1
    assert (fx["out"] / "harbor_adapter_trials.jsonl").read_bytes() == before
    assert (fx["dump"] / "data" / "harbor_adapters" / "codepde" / "00000.parquet").is_file()


def test_cli_subcommand(tmp_path: Path):
    fx = _build_fixture(tmp_path)
    rc = cli_main(
        [
            "harbor-extract-local",
            "--dump-dir",
            str(fx["dump"]),
            "--manifest",
            str(fx["manifest"]),
            "--adapters",
            str(fx["adapters"]),
            "--out",
            str(fx["out"]),
            "--workers",
            "1",
        ]
    )
    assert rc == 0
    assert (fx["out"] / "harbor_adapter_trials.jsonl").is_file()
    assert (fx["out"] / "harbor_funnel_rewards.jsonl").is_file()
