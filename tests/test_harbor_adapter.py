from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from task_validation.ingest.harbor_adapter import (
    FRONTIER_CELLS,
    parse_manifest,
)


def _write_manifest(path: Path, rows: list[dict]) -> None:
    table = pa.Table.from_pylist(
        rows,
        schema=pa.schema(
            [
                ("benchmark", pa.string()),
                ("task_name", pa.string()),
                ("agent", pa.string()),
                ("model", pa.string()),
                ("trial_ids", pa.list_(pa.string())),
            ]
        ),
    )
    pq.write_table(table, path)


def test_parse_manifest_filters_cells_and_caps_trials(tmp_path: Path):
    manifest = tmp_path / "manifest.parquet"
    cell_agent, cell_model = FRONTIER_CELLS[0]
    _write_manifest(
        manifest,
        [
            {
                "benchmark": "codepde",
                "task_name": "codepde/t1",
                "agent": cell_agent,
                "model": cell_model,
                "trial_ids": ["t1", "t2", "t3", "t4", "t5"],
            },
            {
                "benchmark": "codepde",
                "task_name": "codepde/t1",
                "agent": "openhands",  # not a frontier harness
                "model": "gpt-5.4",
                "trial_ids": ["x1", "x2", "x3"],
            },
            {
                "benchmark": "codepde",
                "task_name": "codepde/t1",
                "agent": "codex",
                "model": "gpt-5-mini",  # not a frontier model
                "trial_ids": ["y1"],
            },
            {
                "benchmark": "ds-1000",  # not one of the 54 paper adapters
                "task_name": "ds-1000/t9",
                "agent": cell_agent,
                "model": cell_model,
                "trial_ids": ["z1", "z2", "z3"],
            },
            {
                "benchmark": "sldbench",
                "task_name": "sldbench/t2",
                "agent": "terminus-2",
                "model": "gpt-5.4",
                "trial_ids": ["s1"],  # short cell: fewer than 3 stored
            },
        ],
    )
    rows = parse_manifest(manifest, ["codepde", "sldbench"])
    assert sorted(r["trial_id"] for r in rows) == ["s1", "t1", "t2", "t3"]
    t1 = [r for r in rows if r["task_name"] == "codepde/t1"]
    assert [r["trial_index"] for r in t1] == [0, 1, 2]
    assert all(r["agent"] == cell_agent and r["model"] == cell_model for r in t1)
    short = [r for r in rows if r["task_name"] == "sldbench/t2"]
    assert short[0]["agent"] == "terminus-2" and short[0]["model"] == "gpt-5.4"


def test_parse_manifest_empty_when_no_benchmarks(tmp_path: Path):
    manifest = tmp_path / "manifest.parquet"
    _write_manifest(
        manifest,
        [
            {
                "benchmark": "codepde",
                "task_name": "codepde/t1",
                "agent": FRONTIER_CELLS[0][0],
                "model": FRONTIER_CELLS[0][1],
                "trial_ids": ["t1"],
            }
        ],
    )
    assert parse_manifest(manifest, ["sldbench"]) == []
