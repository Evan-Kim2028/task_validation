"""Harbor-Adapter stage-1 reward fetcher.

Reconstructs the Harbor-Index (arXiv 2609.04298) stage-1 filter input from the
public `kendx/Harbor-Adapter` dataset: for each of the 6 frontier cells in
paper appendix H.1, up to 3 trials per candidate task, reading `result.json`
and `verifier/reward.txt` out of each trial archive.

Fetch granularity is the whole parquet shard. The trajectories split stores
`archive` bytes inside `data/harbor_adapters/<benchmark>/NNNNN.parquet` files
that have one row group and no page offset index, so a single trial cannot be
range-read (evidence: documents/48). The fetcher therefore downloads one shard
at a time, extracts only the needed trials, deletes the shard, and appends
rows to the output JSONL. It is resume-aware: trial_ids already present in the
output are skipped and completed shards are recorded in a state file. A hard
byte budget stops the run cleanly when exceeded.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import time
from pathlib import Path

HF_REPO = "kendx/Harbor-Adapter"
HF_BASE_URL = (
    f"https://huggingface.co/datasets/{HF_REPO}/resolve/main/"
)
TRAJECTORY_PREFIX = "data/harbor_adapters"

# Paper appendix H.1: three leading model families x two harness
# configurations (native harness + Terminus-2), 3 valid trials per pair.
FRONTIER_CELLS = (
    ("claude-code", "claude-opus-4-6"),
    ("terminus-2", "claude-opus-4-6"),
    ("codex", "gpt-5.4"),
    ("terminus-2", "gpt-5.4"),
    ("gemini-cli", "gemini-3.1-pro-preview"),
    ("terminus-2", "gemini-3.1-pro-preview"),
)
TRIALS_PER_CELL = 3
DEFAULT_BYTE_BUDGET = 40 * 1024**3

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = REPO_ROOT / "data" / "raw" / "harbor-adapter" / "harbor_adapters.manifest.parquet"
DEFAULT_ADAPTERS = REPO_ROOT / "data" / "raw" / "harbor-adapter" / "adapters54.json"
DEFAULT_INDEX = REPO_ROOT / "data" / "raw" / "harbor-adapter" / "trial_shards.jsonl"
DEFAULT_OUT = REPO_ROOT / "data" / "gold" / "harbor_funnel_rewards.jsonl"
DEFAULT_WORK = REPO_ROOT / "data" / "raw" / "harbor-adapter" / "shards"

RESULT_MEMBER = "result.json"
REWARD_MEMBER = "verifier/reward.txt"


def load_adapter_benchmarks(adapters_path: Path) -> list[str]:
    """Manifest benchmark slugs for the 54 paper adapters (Table 5)."""
    data = json.loads(Path(adapters_path).read_text(encoding="utf-8"))
    return sorted(a["benchmark"] for a in data["adapters"])


def parse_manifest(
    manifest_path: Path,
    benchmarks: list[str],
    cells: tuple[tuple[str, str], ...] = FRONTIER_CELLS,
    per_cell: int = TRIALS_PER_CELL,
) -> list[dict]:
    """Build the stage-1 worklist: one row per needed trial.

    Keeps the first `per_cell` trial_ids of each frontier cell row for each
    (benchmark, task_name) in `benchmarks`. Cell rows missing from the
    manifest contribute nothing; short trial lists contribute what they have.
    """
    import pyarrow.parquet as pq

    table = pq.read_table(
        Path(manifest_path),
        columns=["benchmark", "task_name", "agent", "model", "trial_ids"],
    )
    wanted = set(benchmarks)
    cell_set = set(cells)
    out: list[dict] = []
    for row in table.to_pylist():
        if row["benchmark"] not in wanted or (row["agent"], row["model"]) not in cell_set:
            continue
        for rank, trial_id in enumerate(list(row["trial_ids"] or [])[:per_cell]):
            out.append(
                {
                    "benchmark": row["benchmark"],
                    "task_name": row["task_name"],
                    "agent": row["agent"],
                    "model": row["model"],
                    "trial_index": rank,
                    "trial_id": trial_id,
                }
            )
    return out


def list_shards(benchmarks: list[str]) -> list[dict]:
    """HF paths and byte sizes for the trajectory shards in scope."""
    from huggingface_hub import HfApi

    wanted = set(benchmarks)
    out = []
    for entry in HfApi().list_repo_tree(
        HF_REPO, TRAJECTORY_PREFIX, repo_type="dataset", recursive=True
    ):
        if not entry.path.endswith(".parquet"):
            continue
        if entry.path.split("/")[2] in wanted:
            out.append({"path": entry.path, "bytes": int(entry.size or 0)})
    return sorted(out, key=lambda d: d["path"])


def build_trial_index(shards: list[dict], index_path: Path) -> dict[str, str]:
    """Map trial_id -> shard path by reading only the trial_id column.

    One small HTTP range read per shard. Cached as JSONL so a resume does not
    rescan. Returns the full map (cached rows plus fresh reads merged).
    """
    import fsspec
    import pyarrow.parquet as pq

    index_path = Path(index_path)
    cached: dict[str, str] = {}
    done_shards: set[str] = set()
    if index_path.is_file():
        with index_path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec = json.loads(line)
                done_shards.add(rec["shard"])
                for tid in rec["trial_ids"]:
                    cached[tid] = rec["shard"]
    pending = [s for s in shards if s["path"] not in done_shards]
    if not pending:
        return cached
    fs = fsspec.filesystem("https")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a", encoding="utf-8") as fh:
        for i, shard in enumerate(pending):
            url = HF_BASE_URL + shard["path"]
            with fs.open(url) as f:
                col = pq.ParquetFile(f).read(columns=["trial_id"])
            ids = col.column(0).to_pylist()
            fh.write(json.dumps({"shard": shard["path"], "trial_ids": ids}) + "\n")
            for tid in ids:
                cached[tid] = shard["path"]
            if i % 50 == 0:
                fh.flush()
                print(
                    f"[harbor_adapter] index {i + 1}/{len(pending)} shards",
                    flush=True,
                )
    return cached


def extract_reward_row(archive: bytes) -> dict:
    """Pull result.json and verifier/reward.txt out of one trial tar.gz."""
    tar = tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz")
    result = None
    reward = None
    for member in tar:
        if not member.isfile():
            continue
        name = member.name.split("/", 1)[-1] if "/" in member.name else member.name
        if name == RESULT_MEMBER:
            result = json.loads(tar.extractfile(member).read())
        elif name == REWARD_MEMBER:
            raw = tar.extractfile(member).read().decode("utf-8", "replace").strip()
            try:
                reward = float(raw)
            except ValueError:
                reward = None
    return {"result": result, "reward": reward}


def _load_done_trials(out_path: Path) -> set[str]:
    done: set[str] = set()
    if Path(out_path).is_file():
        with Path(out_path).open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    done.add(json.loads(line)["trial_id"])
    return done


def _load_state(state_path: Path) -> dict:
    if Path(state_path).is_file():
        return json.loads(Path(state_path).read_text(encoding="utf-8"))
    return {"bytes_downloaded": 0, "shards_done": [], "n_rows": 0}


def _save_state(state_path: Path, state: dict) -> None:
    Path(state_path).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def run_fetch(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    adapters_path: Path = DEFAULT_ADAPTERS,
    index_path: Path = DEFAULT_INDEX,
    out_path: Path = DEFAULT_OUT,
    work_dir: Path = DEFAULT_WORK,
    budget_bytes: int = DEFAULT_BYTE_BUDGET,
    dry_run: bool = False,
) -> dict:
    """Download shards one at a time; extract needed trials; stop at budget."""
    benchmarks = load_adapter_benchmarks(adapters_path)
    worklist = parse_manifest(manifest_path, benchmarks)
    needed = {r["trial_id"] for r in worklist}
    shards = list_shards(benchmarks)
    total_scope = sum(s["bytes"] for s in shards)
    report = {
        "n_benchmarks": len(benchmarks),
        "n_needed_trials": len(needed),
        "n_shards_scope": len(shards),
        "scope_bytes": total_scope,
        "budget_bytes": budget_bytes,
    }
    if dry_run:
        return report

    trial_to_shard = build_trial_index(shards, index_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    state_path = out_path.with_suffix(".state.json")
    state = _load_state(state_path)
    done_trials = _load_done_trials(out_path)
    done_shards = set(state["shards_done"])

    by_shard: dict[str, set[str]] = {}
    for r in worklist:
        if r["trial_id"] in done_trials:
            continue
        shard = trial_to_shard.get(r["trial_id"])
        if shard is None:
            continue
        by_shard.setdefault(shard, set()).add(r["trial_id"])
    cell_of = {r["trial_id"]: r for r in worklist}

    order = [
        s
        for s in shards
        if s["path"] in by_shard and s["path"] not in done_shards
    ]
    order.sort(key=lambda s: (-len(by_shard[s["path"]]) / max(s["bytes"], 1), s["path"]))
    report["n_shards_to_fetch"] = len(order)
    report["bytes_to_fetch"] = sum(s["bytes"] for s in order)

    from huggingface_hub import hf_hub_download
    import pandas as pd

    t0 = time.monotonic()
    for shard in order:
        path, size = shard["path"], shard["bytes"]
        if state["bytes_downloaded"] + size > budget_bytes:
            report["stopped"] = "byte_budget"
            break
        local = Path(
            hf_hub_download(
                HF_REPO,
                path,
                repo_type="dataset",
                local_dir=work_dir,
            )
        )
        state["bytes_downloaded"] += int(local.stat().st_size)
        try:
            df = pd.read_parquet(local)
            want = by_shard[path]
            with out_path.open("a", encoding="utf-8") as fh:
                for rec in df.itertuples(index=False):
                    if rec.trial_id not in want or rec.trial_id in done_trials:
                        continue
                    digest = hashlib.sha256(rec.archive).hexdigest()
                    if digest != rec.archive_sha256:
                        continue
                    row = dict(cell_of[rec.trial_id])
                    row.update(extract_reward_row(rec.archive))
                    row["archive_sha256"] = rec.archive_sha256
                    row["shard"] = path
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    done_trials.add(rec.trial_id)
                    state["n_rows"] += 1
        finally:
            local.unlink(missing_ok=True)
        done_shards.add(path)
        state["shards_done"] = sorted(done_shards)
        _save_state(state_path, state)
        print(
            f"[harbor_adapter] {path} done; bytes={state['bytes_downloaded']} "
            f"rows={state['n_rows']} elapsed={time.monotonic() - t0:.0f}s",
            flush=True,
        )
    else:
        report["stopped"] = "complete"
    report["bytes_downloaded"] = state["bytes_downloaded"]
    report["n_rows"] = state["n_rows"]
    report["n_shards_done"] = len(done_shards)
    _save_state(state_path, state)
    return report
