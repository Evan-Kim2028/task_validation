"""Trajectory and verifier feature extractor for the Harbor-Adapter dump.

Reads the same local snapshot layout as `harbor_adapter_local`
(`data/harbor_adapters/<benchmark>/<NNNNN>.parquet`, one row per trial with
`trial_id`, a gzipped trial-directory `archive`, and `archive_sha256`) and
emits one flat feature row per trial:

* trajectory stats from `agent/trajectory.json` (ATIF: a list of steps with
  roles, tool calls, and observations; a top-level {"steps": [...]} object is
  also accepted),
* verifier stats from `verifier/report.json` (pytest-style only),
  `verifier/test-stdout.txt`, and `verifier/reward.txt`,
* cheat/shortcut regex signals over the assistant-authored text only
  (assistant message text plus serialized tool-call arguments; observations,
  system prompts, and user text are never scanned),
* `hit_timeout` from `result.json` `exception_info` or a timeout line in
  `trial.log`.

Malformed or missing members never fail a shard; the per-trial errors are
recorded in `parse_error`. Memory and resume semantics match
`harbor_adapter_local`: one shard per worker via `ParquetFile.iter_batches`,
one JSONL part per shard under `<out>/shards/` (atomic tmp + rename), and a
rerun skips finished shards. The dump is opened read-only.

The final concatenation pass writes `harbor_adapter_traj.jsonl` (one row per
trial), `harbor_adapter_task_traj.jsonl` (per (benchmark, task_name) means
and rates across all trials, across the six frontier cells of
`adapters54.json`, and per cell, plus the top 3 failed test names and the
fraction of failing trials sharing the single most common failed test, the
hidden-requirement signature), and `harbor_adapter_traj.summary.json`.

Remote host, venv with only pyarrow installed:

    PYTHONPATH=src python -m task_validation.ingest.harbor_adapter_traj \
        --dump-dir /path/to/harbor-adapter-dump \
        --manifest /path/to/harbor_adapters.manifest.parquet \
        --adapters /path/to/adapters54.json \
        --out /path/to/harbor_traj --workers 4
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import tarfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from task_validation.ingest import harbor_adapter_local as _local
from task_validation.ingest.harbor_adapter import FRONTIER_CELLS

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = _local.DEFAULT_MANIFEST
DEFAULT_ADAPTERS = _local.DEFAULT_ADAPTERS
DEFAULT_OUT = REPO_ROOT / "data" / "gold" / "harbor_adapter_traj"

SHARD_GLOB = _local.SHARD_GLOB
TRIALS_NAME = "harbor_adapter_traj.jsonl"
TASKS_NAME = "harbor_adapter_task_traj.jsonl"
SUMMARY_NAME = "harbor_adapter_traj.summary.json"

_BATCH_ROWS = 16

# Trial-archive members this extractor reads. Archives hold one enclosing
# trial directory, so members are matched on the path under that directory.
_RESULT = "result.json"
_CONFIG = "config.json"
_TRIAL_LOG = "trial.log"
_TRAJECTORY = "agent/trajectory.json"
_REPORT = "verifier/report.json"
_REWARD_TXT = "verifier/reward.txt"
_TEST_STDOUT = "verifier/test-stdout.txt"
_WANTED = frozenset(
    {_RESULT, _CONFIG, _TRIAL_LOG, _TRAJECTORY, _REPORT, _REWARD_TXT, _TEST_STDOUT}
)
_JSON_MEMBERS = {_RESULT: "result", _CONFIG: "config", _TRAJECTORY: "trajectory", _REPORT: "report"}

# Cheat and shortcut signals, all counted over assistant text only.
_ANSWER_FILE_RE = re.compile(
    r"/tests/|reward\.txt|solution/|expected[_-]?output", re.IGNORECASE
)
_GIT_PROBE_RE = re.compile(r"\bgit\s+(?:log|show)\b|\bgit\s+diff\s+HEAD~")
_NETWORK_RE = re.compile(r"\b(?:curl|wget)\b|\bpip3?\s+download\b", re.IGNORECASE)
_TIMEOUT_RE = re.compile(r"timed?[ _-]?out|deadline[ _-]?exceeded", re.IGNORECASE)

_ASSISTANT_ROLES = frozenset({"agent", "assistant"})
_FAILED_OUTCOMES = frozenset({"failed", "error"})
_MAX_FAILED_NAMES = 50

# Per-worker scope loaded once by _init_worker: {"pairs", "meta", "cells"}.
_SCOPE: dict | None = None


def load_frontier_cells(adapters_path: Path) -> tuple[tuple[str, str], ...]:
    """Frontier (agent, model) cells from adapters54.json; paper fallback."""
    try:
        data = json.loads(Path(adapters_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return FRONTIER_CELLS
    cells = data.get("frontier_cells")
    out = []
    if isinstance(cells, list):
        for c in cells:
            if isinstance(c, dict) and c.get("agent") and c.get("model"):
                out.append((c["agent"], c["model"]))
    return tuple(out) or FRONTIER_CELLS


def _init_worker(manifest_path: str, adapters_path: str) -> None:
    global _SCOPE
    scope = _local.load_scope(Path(manifest_path), Path(adapters_path))
    scope["cells"] = load_frontier_cells(Path(adapters_path))
    _SCOPE = scope


def _rel_name(member_name: str) -> str:
    """Path under the enclosing trial directory for a tar member."""
    rel = member_name.lstrip("./")
    if rel in _WANTED:
        return rel
    return rel.split("/", 1)[-1] if "/" in rel else rel


def _empty_payload() -> dict:
    return {
        "result": None,
        "config": None,
        "trajectory": None,
        "report": None,
        "reward_txt": None,
        "test_stdout_bytes": None,
        "trial_log": None,
        "has_report_json": False,
    }


def _extract_trial(archive: bytes) -> tuple[dict, str | None]:
    """Parse one trial tar.gz into member payloads; never raises."""
    payload = _empty_payload()
    try:
        tar = tarfile.open(fileobj=io.BytesIO(archive), mode="r:*")
    except (tarfile.TarError, OSError, EOFError) as e:
        return payload, f"tar open: {e}"
    errs: list[str] = []
    try:
        for member in tar:
            if not member.isfile():
                continue
            rel = _rel_name(member.name)
            if rel not in _WANTED:
                continue
            fobj = tar.extractfile(member)
            if fobj is None:
                continue
            try:
                data = fobj.read()
            except (OSError, EOFError) as e:
                errs.append(f"{rel}: read: {e}")
                continue
            if rel in _JSON_MEMBERS:
                if rel == _REPORT:
                    payload["has_report_json"] = True
                try:
                    payload[_JSON_MEMBERS[rel]] = json.loads(data)
                except ValueError as e:
                    errs.append(f"{rel}: {e}")
            elif rel == _REWARD_TXT:
                payload["reward_txt"] = data.decode("utf-8", "replace").strip()
            elif rel == _TEST_STDOUT:
                payload["test_stdout_bytes"] = len(data)
            elif rel == _TRIAL_LOG:
                payload["trial_log"] = data.decode("utf-8", "replace")
    except (tarfile.TarError, OSError, EOFError) as e:
        errs.append(f"tar read: {e}")
    return payload, "; ".join(errs) or None


def _text_of(v) -> str:
    """Flatten a message/content field that may be str, dict, or parts list."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for k in ("text", "content", "message"):
            if isinstance(v.get(k), str):
                return v[k]
        return ""
    if isinstance(v, list):
        return "\n".join(s for s in (_text_of(i) for i in v) if s)
    return str(v)


def _steps_of(traj) -> list | None:
    if isinstance(traj, list):
        return traj
    if isinstance(traj, dict):
        for k in ("steps", "trajectory", "messages", "events"):
            if isinstance(traj.get(k), list):
                return traj[k]
    return None


def _parse_ts(v) -> datetime | None:
    if not isinstance(v, str) or not v.strip():
        return None
    s = v.strip()
    try:
        return datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _tool_call_text(step: dict) -> str:
    """Assistant-authored tool-call content: function names plus arguments."""
    tc = step.get("tool_calls")
    calls = tc if isinstance(tc, list) else [tc] if isinstance(tc, dict) else []
    parts: list[str] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        fn = call.get("function")
        fn = fn if isinstance(fn, dict) else {}
        name = call.get("function_name") or call.get("name") or fn.get("name")
        if isinstance(name, str):
            parts.append(name)
        args = call.get("arguments", call.get("args", fn.get("arguments")))
        if isinstance(args, str):
            parts.append(args)
        elif args is not None:
            try:
                parts.append(json.dumps(args, ensure_ascii=False))
            except (TypeError, ValueError):
                parts.append(str(args))
    return "\n".join(parts)


def _obs_text(obs) -> str:
    if obs is None:
        return ""
    if isinstance(obs, dict):
        res = obs.get("results")
        if isinstance(res, list):
            return "\n".join(
                _text_of(r.get("content") if isinstance(r, dict) else r) for r in res
            )
        return _text_of(obs)
    if isinstance(obs, list):
        return "\n".join(_text_of(r) for r in obs)
    return _text_of(obs)


def _traj_stats(traj) -> dict:
    """Step counts, char totals, time span, and cheat signals for one ATIF."""
    out = {
        "n_steps": None,
        "n_tool_calls": None,
        "n_assistant_messages": None,
        "total_observation_chars": None,
        "total_assistant_chars": None,
        "first_step_at": None,
        "last_step_at": None,
        "agent_wall_sec": None,
        "mentions_answer_file": None,
        "git_history_probe": None,
        "network_fetch": None,
    }
    steps = _steps_of(traj)
    if steps is None:
        return out
    n_tool_calls = n_assistant = obs_chars = asst_chars = 0
    asst_texts: list[str] = []
    stamps: list[tuple[datetime, str]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        role = step.get("source") or step.get("role") or ""
        msg = _text_of(step.get("message")) or _text_of(step.get("content"))
        tc = step.get("tool_calls")
        n_tool_calls += len(tc) if isinstance(tc, list) else int(isinstance(tc, dict))
        if role in _ASSISTANT_ROLES:
            n_assistant += 1
            asst_chars += len(msg)
            if msg:
                asst_texts.append(msg)
            tc_text = _tool_call_text(step)
            if tc_text:
                asst_texts.append(tc_text)
        obs = step.get("observation")
        if obs is None:
            obs = step.get("observations")
        obs_chars += len(_obs_text(obs))
        ts = step.get("timestamp") or step.get("time") or step.get("created_at")
        dt = _parse_ts(ts)
        if dt is not None:
            stamps.append((dt, str(ts)))
    if stamps:
        if any(dt.tzinfo is not None for dt, _ in stamps):
            stamps = [
                (dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc), raw)
                for dt, raw in stamps
            ]
        first, last = min(stamps), max(stamps)
        out["first_step_at"] = first[1]
        out["last_step_at"] = last[1]
        out["agent_wall_sec"] = (last[0] - first[0]).total_seconds()
    asst = "\n".join(asst_texts)
    out.update(
        {
            "n_steps": len(steps),
            "n_tool_calls": n_tool_calls,
            "n_assistant_messages": n_assistant,
            "total_observation_chars": obs_chars,
            "total_assistant_chars": asst_chars,
            "mentions_answer_file": len(_ANSWER_FILE_RE.findall(asst)),
            "git_history_probe": len(_GIT_PROBE_RE.findall(asst)),
            "network_fetch": len(_NETWORK_RE.findall(asst)),
        }
    )
    return out


def _num(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _report_stats(report) -> dict:
    """Test counts and failed test names from a pytest-style report.json."""
    out = {
        "n_tests_total": None,
        "n_tests_passed": None,
        "n_tests_failed": None,
        "failed_test_names": [],
    }
    if not isinstance(report, dict):
        return out
    tests = report.get("tests")
    summary = report.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    if not isinstance(tests, list) and not any(
        k in summary for k in ("total", "passed", "failed", "collected")
    ):
        return out
    counted_passed = counted_failed = None
    if isinstance(tests, list):
        names: list[str] = []
        seen: set[str] = set()
        n_passed = n_failed = 0
        for t in tests:
            if not isinstance(t, dict):
                continue
            oc = str(t.get("outcome") or t.get("status") or "").lower()
            if oc == "passed":
                n_passed += 1
            elif oc in _FAILED_OUTCOMES:
                n_failed += 1
                name = t.get("nodeid") or t.get("name") or t.get("id")
                if isinstance(name, str) and name not in seen:
                    seen.add(name)
                    names.append(name)
        counted_passed, counted_failed = n_passed, n_failed
        out["failed_test_names"] = names[:_MAX_FAILED_NAMES]
    out["n_tests_total"] = _num(summary.get("total"))
    if out["n_tests_total"] is None:
        out["n_tests_total"] = _num(summary.get("collected"))
    if out["n_tests_total"] is None and isinstance(tests, list):
        out["n_tests_total"] = len(tests)
    out["n_tests_passed"] = _num(summary.get("passed"))
    if out["n_tests_passed"] is None:
        out["n_tests_passed"] = counted_passed
    out["n_tests_failed"] = _num(summary.get("failed"))
    if out["n_tests_failed"] is None:
        out["n_tests_failed"] = counted_failed
    return out


def _exception_type(res: dict) -> str | None:
    info = res.get("exception_info")
    if isinstance(info, str):
        return info or None
    if isinstance(info, dict):
        for k in ("exception_type", "type", "exc_type", "error_type", "name"):
            v = info.get(k)
            if isinstance(v, str) and v:
                return v
    return None


def _traj_row(shard_benchmark: str, rel: str, rec: dict) -> dict:
    """One feature row per trial; member-level errors land in parse_error."""
    archive = rec["archive"]
    col_sha = rec.get("archive_sha256")
    if archive is None:
        digest = None
        payload, error = _empty_payload(), "archive null"
    else:
        digest = hashlib.sha256(archive).hexdigest()
        payload, error = _extract_trial(archive)
        if col_sha and col_sha != digest:
            error = (error + "; " if error else "") + "archive_sha256 mismatch"
    res = _local._d(payload["result"])
    config = _local._d(payload["config"])
    meta = (_SCOPE or {}).get("meta", {}).get(rec["trial_id"])
    if meta is not None:
        benchmark, task_name, agent, model, trial_index = meta
    else:
        benchmark = shard_benchmark
        task_name = res.get("task_name") or config.get("task_name")
        agent_info = _local._d(res.get("agent_info"))
        config_agent = _local._d(_local._d(res.get("config")).get("agent")) or _local._d(
            config.get("agent")
        )
        agent = agent_info.get("name") or config_agent.get("name")
        model = _local._d(agent_info.get("model_info")).get("name") or config_agent.get(
            "model_name"
        )
        trial_index = None
    in_scope = (benchmark, task_name) in (_SCOPE or {}).get("pairs", set())

    reward_txt_value = None
    if payload["reward_txt"] is not None:
        try:
            reward_txt_value = float(payload["reward_txt"])
        except ValueError:
            error = (error + "; " if error else "") + f"{_REWARD_TXT}: not a float"
    reward = reward_txt_value
    if reward is None:
        rv = _local._d(_local._d(res.get("verifier_result")).get("rewards"))
        if rv.get("reward") is not None:
            try:
                reward = float(rv["reward"])
            except (TypeError, ValueError):
                reward = None

    exception_type = _exception_type(res)
    hit_timeout = bool(exception_type and "timeout" in exception_type.lower())
    if not hit_timeout and payload["trial_log"]:
        hit_timeout = bool(_TIMEOUT_RE.search(payload["trial_log"]))

    row = {
        "benchmark": benchmark,
        "task_name": task_name,
        "agent": agent,
        "model": model,
        "trial_index": trial_index,
        "trial_id": rec["trial_id"],
        "reward": reward,
        "reward_txt_value": reward_txt_value,
        "reward_partial": bool(reward is not None and 0.0 < reward < 1.0),
        "hit_timeout": hit_timeout,
        "exception_type": exception_type,
        "has_report_json": payload["has_report_json"],
        "test_stdout_bytes": payload["test_stdout_bytes"],
        "parse_error": error,
        "in_scope": in_scope,
        "archive_sha256": col_sha or digest,
        "shard": rel,
    }
    row.update(_traj_stats(payload["trajectory"]))
    row.update(_report_stats(payload["report"]))
    return row


def process_shard(shard_path: str, rel: str, shards_dir: str) -> dict:
    """Extract every trial row of one shard into its JSONL part file."""
    part = Path(shards_dir) / _local._part_name(rel)
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
    n = n_scope = n_err = 0
    with tmp.open("w", encoding="utf-8") as fh:
        for rg in range(pf.num_row_groups):
            for batch in pf.iter_batches(
                batch_size=_BATCH_ROWS, row_groups=[rg], columns=cols
            ):
                for rec in batch.to_pylist():
                    row = _traj_row(benchmark, rel, rec)
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    n += 1
                    n_scope += int(row["in_scope"])
                    n_err += int(row["parse_error"] is not None)
    os.replace(tmp, part)
    return {
        "shard": rel,
        "skipped": False,
        "n_rows": n,
        "n_in_scope": n_scope,
        "n_parse_errors": n_err,
    }


# Streaming per-task aggregation state. Means and rates are kept as sums and
# counts so the final pass never holds more than one trial row in memory.
_MEAN_KEYS = (
    "reward",
    "n_steps",
    "n_tool_calls",
    "n_assistant_messages",
    "total_observation_chars",
    "total_assistant_chars",
    "agent_wall_sec",
    "n_tests_total",
    "n_tests_passed",
    "n_tests_failed",
    "test_stdout_bytes",
    "mentions_answer_file",
    "git_history_probe",
    "network_fetch",
)
_SIGNAL_KEYS = ("mentions_answer_file", "git_history_probe", "network_fetch")


def _new_acc() -> dict:
    return {"n": 0, "sums": Counter(), "counts": Counter(), "flags": Counter()}


def _acc_add(acc: dict, row: dict) -> None:
    acc["n"] += 1
    for k in _MEAN_KEYS:
        v = row.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            acc["sums"][k] += v
            acc["counts"][k] += 1
    if row.get("reward") == 1.0:
        acc["flags"]["solve"] += 1
    acc["flags"]["reward_partial"] += int(bool(row.get("reward_partial")))
    acc["flags"]["hit_timeout"] += int(bool(row.get("hit_timeout")))
    acc["flags"]["exception"] += int(row.get("exception_type") is not None)
    acc["flags"]["has_report_json"] += int(bool(row.get("has_report_json")))
    acc["flags"]["parse_error"] += int(row.get("parse_error") is not None)
    for k in _SIGNAL_KEYS:
        v = row.get(k)
        if v is not None and v > 0:
            acc["flags"][k + "_pos"] += 1


def _frac(num, den):
    return num / den if den else None


def _bundle(acc: dict) -> dict:
    """Means and rates for one accumulator (all trials, frontier, or a cell)."""
    n = acc["n"]
    b: dict = {"n_trials": n}
    for k in _MEAN_KEYS:
        b[k + "_mean"] = _frac(acc["sums"][k], acc["counts"][k])
    b["solve_rate"] = _frac(acc["flags"]["solve"], acc["counts"]["reward"])
    b["reward_partial_rate"] = _frac(acc["flags"]["reward_partial"], n)
    b["hit_timeout_rate"] = _frac(acc["flags"]["hit_timeout"], n)
    b["exception_rate"] = _frac(acc["flags"]["exception"], n)
    b["has_report_json_rate"] = _frac(acc["flags"]["has_report_json"], n)
    b["parse_error_rate"] = _frac(acc["flags"]["parse_error"], n)
    for k in _SIGNAL_KEYS:
        b[k + "_rate"] = _frac(acc["flags"][k + "_pos"], acc["counts"][k])
    return b


def _task_row(key: tuple, state: dict, cells: tuple, scope_pairs: set) -> dict:
    benchmark, task_name = key
    top = state["failed"].most_common(3)
    top_name = top[0][0] if top else None
    n_failing = state["n_failing"]
    share = None
    if top_name is not None and n_failing:
        # failed_test_names are per-trial deduped, so the counter value is the
        # number of failing trials containing that test.
        share = min(state["failed"][top_name] / n_failing, 1.0)
    return {
        "benchmark": benchmark,
        "task_name": task_name,
        "in_scope": key in scope_pairs,
        "n_trials": state["all"]["n"],
        "all": _bundle(state["all"]),
        "frontier": _bundle(state["frontier"]),
        "cells": [
            {"agent": agent, "model": model, **_bundle(state["cells"][i])}
            for i, (agent, model) in enumerate(cells)
        ],
        "n_failing_trials": n_failing,
        "top_failed_tests": [{"name": name, "n": c} for name, c in top],
        "top_failed_share_of_failing_trials": share,
    }


def _concatenate(shards_dir: Path, out_dir: Path, cells: tuple, scope_pairs: set) -> dict:
    """Build the trial JSONL, the per-task aggregation JSONL, and counts."""
    trials_tmp = out_dir / (TRIALS_NAME + ".tmp")
    tasks_tmp = out_dir / (TASKS_NAME + ".tmp")
    per_benchmark: Counter[str] = Counter()
    states: dict[tuple, dict] = {}
    cell_index = {c: i for i, c in enumerate(cells)}
    n_rows = n_scope = 0
    with trials_tmp.open("w", encoding="utf-8") as tf:
        for part in sorted(shards_dir.glob("*.jsonl")):
            with part.open(encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    n_rows += 1
                    n_scope += int(row.get("in_scope"))
                    per_benchmark[row["benchmark"]] += 1
                    tf.write(line if line.endswith("\n") else line + "\n")
                    key = (row["benchmark"], row.get("task_name"))
                    st = states.get(key)
                    if st is None:
                        st = {
                            "all": _new_acc(),
                            "frontier": _new_acc(),
                            "cells": [_new_acc() for _ in cells],
                            "failed": Counter(),
                            "n_failing": 0,
                        }
                        states[key] = st
                    _acc_add(st["all"], row)
                    ci = cell_index.get((row.get("agent"), row.get("model")))
                    if ci is not None:
                        _acc_add(st["cells"][ci], row)
                        _acc_add(st["frontier"], row)
                    for name in row.get("failed_test_names") or []:
                        st["failed"][name] += 1
                    if (row.get("n_tests_failed") or 0) > 0:
                        st["n_failing"] += 1
    n_tasks = 0
    with tasks_tmp.open("w", encoding="utf-8") as ff:
        for key in sorted(states, key=lambda k: (str(k[0]), str(k[1]))):
            rec = _task_row(key, states[key], cells, scope_pairs)
            ff.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_tasks += 1
    os.replace(trials_tmp, out_dir / TRIALS_NAME)
    os.replace(tasks_tmp, out_dir / TASKS_NAME)
    return {
        "n_rows": n_rows,
        "n_in_scope": n_scope,
        "n_tasks": n_tasks,
        "rows_per_benchmark": dict(sorted(per_benchmark.items())),
    }


def run_extract_traj(
    *,
    dump_dir: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
    adapters_path: Path = DEFAULT_ADAPTERS,
    out_dir: Path = DEFAULT_OUT,
    workers: int = 4,
) -> dict:
    """Extract trajectory features for all trials; resume at shard granularity."""
    dump_dir = Path(dump_dir)
    out_dir = Path(out_dir)
    shards_dir = out_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    shards = _local._find_shards(dump_dir)
    todo: list[tuple[Path, str]] = []
    n_skipped = 0
    for p in shards:
        rel = p.relative_to(dump_dir).as_posix()
        if (shards_dir / _local._part_name(rel)).is_file():
            n_skipped += 1
        else:
            todo.append((p, rel))
    report = {
        "n_shards": len(shards),
        "n_shards_done_before": n_skipped,
        "n_shards_processed": 0,
        "n_shards_failed": 0,
        "shard_errors": [],
        "n_parse_errors": 0,
    }

    def _collect(res: dict) -> None:
        report["n_shards_processed"] += 1
        report["n_parse_errors"] += res.get("n_parse_errors") or 0
        print(
            f"[harbor_adapter_traj] {res['shard']} done "
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

    scope = _SCOPE or _local.load_scope(Path(manifest_path), Path(adapters_path))
    cells = scope.get("cells") or load_frontier_cells(Path(adapters_path))
    summary = _concatenate(shards_dir, out_dir, cells, scope.get("pairs", set()))
    report.update(summary)
    summary_path = out_dir / SUMMARY_NAME
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harbor-extract-traj")
    parser.add_argument("--dump-dir", required=True, help="local Harbor-Adapter snapshot root")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--adapters", default=str(DEFAULT_ADAPTERS))
    parser.add_argument("--out", "--out-dir", dest="out", default=str(DEFAULT_OUT))
    parser.add_argument("--workers", type=int, default=4, help="one shard in memory per worker")
    args = parser.parse_args(argv)
    report = run_extract_traj(
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
