"""Local-shard extractor for the Harbor-Adapter dump.

Reads a local snapshot of `kendx/Harbor-Adapter` (same layout as the Hub
repository: `data/harbor_adapters/<benchmark>/<NNNNN>.parquet`, one row per
trial with `trial_id`, a gzipped trial-directory `archive`, and
`archive_sha256`) and extracts one flat row per trial for every trial in
the dump, not only the stage-1 worklist. The dump is opened read-only;
nothing under --dump-dir is written or deleted.

Memory is bounded to one shard per worker: each worker reads one parquet
row group at a time via `ParquetFile.iter_batches` and never holds more
than one shard's data in flight. Resume is by shard: each shard produces
one JSONL part under `<out>/shards/` (atomic tmp + rename), so a rerun
skips finished shards. A final pass concatenates the parts into
`harbor_adapter_trials.jsonl`, writes `harbor_funnel_rewards.jsonl` for
the in-scope rows in the exact schema `harbor_adapter.run_fetch` produces
(so downstream code is unchanged), and records
`harbor_adapter_trials.summary.json` with per-benchmark row counts, the
in-scope count, and the number of distinct (benchmark, task_name) pairs.

Remote host, venv with only pyarrow installed:

    PYTHONPATH=src python -m task_validation.cli harbor-extract-local \
        --dump-dir /path/to/harbor-adapter-dump \
        --manifest /path/to/harbor_adapters.manifest.parquet \
        --adapters /path/to/adapters54.json \
        --out /path/to/harbor_extract --workers 4
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from task_validation.ingest.harbor_adapter import (
    RESULT_MEMBER,
    REWARD_MEMBER,
    load_adapter_benchmarks,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = REPO_ROOT / "data" / "raw" / "harbor-adapter" / "harbor_adapters.manifest.parquet"
DEFAULT_ADAPTERS = REPO_ROOT / "data" / "raw" / "harbor-adapter" / "adapters54.json"
DEFAULT_OUT = REPO_ROOT / "data" / "gold" / "harbor_adapter_local"

SHARD_GLOB = "data/harbor_adapters/**/*.parquet"
TRIALS_NAME = "harbor_adapter_trials.jsonl"
FUNNEL_NAME = "harbor_funnel_rewards.jsonl"
SUMMARY_NAME = "harbor_adapter_trials.summary.json"

# Exact field list written by harbor_adapter.run_fetch; the funnel file is a
# drop-in replacement for the network fetcher's output.
FUNNEL_KEYS = (
    "benchmark",
    "task_name",
    "agent",
    "model",
    "trial_index",
    "trial_id",
    "result",
    "reward",
    "archive_sha256",
    "shard",
)

_BATCH_ROWS = 32

# Per-worker scope loaded once by _init_worker: {"pairs": set of in-scope
# (benchmark, task_name), "meta": trial_id -> (benchmark, task_name, agent,
# model, trial_index)} covering the 54 paper adapters only.
_SCOPE: dict | None = None


def load_scope(manifest_path: Path, adapters_path: Path) -> dict:
    """In-scope (benchmark, task_name) pairs and per-trial manifest metadata.

    The 6,627 stage-1 candidates are the distinct (benchmark, task_name)
    pairs in the manifest whose benchmark is one of the 54 paper adapters.
    `meta` maps every manifest trial_id under those benchmarks to its row
    fields and its rank inside the row's trial_ids list, which is the
    `trial_index` the fetcher writes.
    """
    import pyarrow.parquet as pq

    benchmarks = set(load_adapter_benchmarks(Path(adapters_path)))
    table = pq.read_table(
        Path(manifest_path),
        columns=["benchmark", "task_name", "agent", "model", "trial_ids"],
    )
    pairs: set[tuple[str, str]] = set()
    meta: dict[str, tuple] = {}
    for row in table.to_pylist():
        if row["benchmark"] not in benchmarks:
            continue
        pairs.add((row["benchmark"], row["task_name"]))
        for rank, trial_id in enumerate(row["trial_ids"] or []):
            meta[trial_id] = (
                row["benchmark"],
                row["task_name"],
                row["agent"],
                row["model"],
                rank,
            )
    return {"pairs": pairs, "meta": meta}


def _init_worker(manifest_path: str, adapters_path: str) -> None:
    global _SCOPE
    _SCOPE = load_scope(Path(manifest_path), Path(adapters_path))


def _extract_trial(archive: bytes) -> tuple[dict | None, float | None, str | None]:
    """Parse one trial tar.gz into (result.json dict, reward, error)."""
    try:
        tar = tarfile.open(fileobj=io.BytesIO(archive), mode="r:*")
    except (tarfile.TarError, OSError, EOFError) as e:
        return None, None, f"tar open: {e}"
    result = None
    reward = None
    errs: list[str] = []
    try:
        for member in tar:
            if not member.isfile():
                continue
            name = member.name.split("/", 1)[-1] if "/" in member.name else member.name
            if name not in (RESULT_MEMBER, REWARD_MEMBER):
                continue
            fobj = tar.extractfile(member)
            if fobj is None:
                continue
            if name == RESULT_MEMBER:
                try:
                    result = json.loads(fobj.read())
                except (OSError, ValueError) as e:
                    errs.append(f"result.json: {e}")
            else:
                raw = fobj.read().decode("utf-8", "replace").strip()
                try:
                    reward = float(raw)
                except ValueError:
                    reward = None
    except (tarfile.TarError, OSError, EOFError) as e:
        errs.append(f"tar read: {e}")
    if reward is None and isinstance(result, dict):
        try:
            rv = result.get("verifier_result")
            rv = (rv if isinstance(rv, dict) else {}).get("rewards")
            rv = rv if isinstance(rv, dict) else {}
            if rv.get("reward") is not None:
                reward = float(rv["reward"])
        except (TypeError, ValueError):
            pass
    return result, reward, "; ".join(errs) or None


def _d(v) -> dict:
    return v if isinstance(v, dict) else {}


def _flatten_row(shard_benchmark: str, rel: str, rec: dict) -> dict:
    """One superset row per trial: flat fields plus the full result dict."""
    archive = rec["archive"]
    col_sha = rec.get("archive_sha256")
    if archive is None:
        digest = None
        result, reward, error = None, None, "archive null"
    else:
        digest = hashlib.sha256(archive).hexdigest()
        result, reward, error = _extract_trial(archive)
        if col_sha and col_sha != digest:
            error = (error + "; " if error else "") + "archive_sha256 mismatch"
    res = _d(result)
    agent_result = _d(res.get("agent_result"))
    meta = (_SCOPE or {}).get("meta", {}).get(rec["trial_id"])
    if meta is not None:
        benchmark, task_name, agent, model, trial_index = meta
    else:
        benchmark = shard_benchmark
        task_name = res.get("task_name")
        agent_info = _d(res.get("agent_info"))
        config_agent = _d(_d(res.get("config")).get("agent"))
        agent = agent_info.get("name") or config_agent.get("name")
        model = _d(agent_info.get("model_info")).get("name") or config_agent.get("model_name")
        trial_index = None
    in_scope = (benchmark, task_name) in (_SCOPE or {}).get("pairs", set())
    exception = res.get("exception_info") is not None or (result is None and error is not None)
    return {
        "benchmark": benchmark,
        "task_name": task_name,
        "agent": agent,
        "model": model,
        "trial_index": trial_index,
        "trial_id": rec["trial_id"],
        "reward": reward,
        "started_at": res.get("started_at"),
        "finished_at": res.get("finished_at"),
        "n_input_tokens": agent_result.get("n_input_tokens"),
        "n_cache_tokens": agent_result.get("n_cache_tokens"),
        "n_output_tokens": agent_result.get("n_output_tokens"),
        "cost_usd": agent_result.get("cost_usd"),
        "exception": exception,
        "error": error,
        "in_scope": in_scope,
        "archive_sha256": col_sha or digest,
        "shard": rel,
        "result": result,
    }


def _part_name(rel: str) -> str:
    p = Path(rel)
    return f"{p.parent.name}__{p.stem}.jsonl"


def process_shard(shard_path: str, rel: str, shards_dir: str) -> dict:
    """Extract every trial row of one shard into its JSONL part file."""
    part = Path(shards_dir) / _part_name(rel)
    if part.is_file():
        return {"shard": rel, "skipped": True}
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(shard_path)
    names = set(pf.schema_arrow.names)
    cols = [c for c in ("trial_id", "archive", "archive_sha256") if c in names]
    if "trial_id" not in cols or "archive" not in cols:
        raise ValueError(f"{rel}: expected trial_id/archive columns, has {sorted(names)}")
    benchmark = Path(rel).parent.name
    tmp = part.with_name(part.name + ".tmp")
    n = n_scope = 0
    with tmp.open("w", encoding="utf-8") as fh:
        for rg in range(pf.num_row_groups):
            for batch in pf.iter_batches(batch_size=_BATCH_ROWS, row_groups=[rg], columns=cols):
                for rec in batch.to_pylist():
                    row = _flatten_row(benchmark, rel, rec)
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    n += 1
                    n_scope += int(row["in_scope"])
    os.replace(tmp, part)
    return {"shard": rel, "skipped": False, "n_rows": n, "n_in_scope": n_scope}


def _concatenate(shards_dir: Path, out_dir: Path) -> dict:
    """Build harbor_adapter_trials.jsonl, the funnel file, and the summary."""
    trials_tmp = out_dir / (TRIALS_NAME + ".tmp")
    funnel_tmp = out_dir / (FUNNEL_NAME + ".tmp")
    per_benchmark: Counter[str] = Counter()
    pairs: set[tuple] = set()
    scope_pairs: set[tuple] = set()
    n_rows = n_scope = n_funnel = 0
    with trials_tmp.open("w", encoding="utf-8") as tf, funnel_tmp.open("w", encoding="utf-8") as ff:
        for part in sorted(shards_dir.glob("*.jsonl")):
            with part.open(encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    n_rows += 1
                    per_benchmark[row["benchmark"]] += 1
                    pairs.add((row["benchmark"], row["task_name"]))
                    tf.write(json.dumps({k: v for k, v in row.items() if k != "result"}, ensure_ascii=False) + "\n")
                    if row["in_scope"]:
                        n_scope += 1
                        scope_pairs.add((row["benchmark"], row["task_name"]))
                        ff.write(json.dumps({k: row.get(k) for k in FUNNEL_KEYS}, ensure_ascii=False) + "\n")
                        n_funnel += 1
    os.replace(trials_tmp, out_dir / TRIALS_NAME)
    os.replace(funnel_tmp, out_dir / FUNNEL_NAME)
    return {
        "n_rows": n_rows,
        "n_in_scope": n_scope,
        "n_funnel_rows": n_funnel,
        "rows_per_benchmark": dict(sorted(per_benchmark.items())),
        "n_distinct_task_pairs": len(pairs),
        "n_in_scope_pairs": len(scope_pairs),
    }


def _find_shards(dump_dir: Path) -> list[Path]:
    shards = sorted(dump_dir.glob(SHARD_GLOB))
    if not shards:
        shards = sorted(
            p
            for p in dump_dir.glob("**/*.parquet")
            if not any(part.startswith(".") for part in p.relative_to(dump_dir).parts)
        )
    return shards


def run_extract_local(
    *,
    dump_dir: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
    adapters_path: Path = DEFAULT_ADAPTERS,
    out_dir: Path = DEFAULT_OUT,
    workers: int = 4,
) -> dict:
    """Extract all trials from a local dump; resume at shard granularity."""
    dump_dir = Path(dump_dir)
    out_dir = Path(out_dir)
    shards_dir = out_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    shards = _find_shards(dump_dir)
    todo: list[tuple[Path, str]] = []
    n_skipped = 0
    for p in shards:
        rel = p.relative_to(dump_dir).as_posix()
        if (shards_dir / _part_name(rel)).is_file():
            n_skipped += 1
        else:
            todo.append((p, rel))
    report = {
        "n_shards": len(shards),
        "n_shards_done_before": n_skipped,
        "n_shards_processed": 0,
        "n_shards_failed": 0,
        "shard_errors": [],
    }

    def _collect(res: dict) -> None:
        report["n_shards_processed"] += 1
        print(
            f"[harbor_adapter_local] {res['shard']} done "
            f"rows={res.get('n_rows')} in_scope={res.get('n_in_scope')}",
            flush=True,
        )

    if not todo:
        pass
    elif workers <= 1:
        _init_worker(str(manifest_path), str(adapters_path))
        for p, rel in todo:
            try:
                _collect(process_shard(str(p), rel, str(shards_dir)))
            except Exception as e:  # shard stays unwritten; rerun retries
                report["n_shards_failed"] += 1
                report["shard_errors"].append({"shard": rel, "error": str(e)})
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(str(manifest_path), str(adapters_path)),
        ) as ex:
            futs = {ex.submit(process_shard, str(p), rel, str(shards_dir)): rel for p, rel in todo}
            for fut in as_completed(futs):
                try:
                    _collect(fut.result())
                except Exception as e:
                    report["n_shards_failed"] += 1
                    report["shard_errors"].append({"shard": futs[fut], "error": str(e)})

    summary = _concatenate(shards_dir, out_dir)
    report.update(summary)
    summary_path = out_dir / SUMMARY_NAME
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harbor-extract-local")
    parser.add_argument("--dump-dir", required=True, help="local Harbor-Adapter snapshot root")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--adapters", default=str(DEFAULT_ADAPTERS))
    parser.add_argument("--out", "--out-dir", dest="out", default=str(DEFAULT_OUT))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    report = run_extract_local(
        dump_dir=Path(args.dump_dir),
        manifest_path=Path(args.manifest),
        adapters_path=Path(args.adapters),
        out_dir=Path(args.out),
        workers=args.workers,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
