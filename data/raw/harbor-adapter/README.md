---
pretty_name: Harbor Adapters — Agent Trajectories
license: other
language:
  - en
size_categories:
  - 100K<n<1M
tags:
  - agent
  - agent-trajectories
  - llm-evaluation
  - terminal-bench
  - rollouts
configs:
  - config_name: manifest
    default: true
    data_files:
      - split: full
        path: harbor_adapters.manifest.parquet
  - config_name: trajectories
    data_files:
      - split: full
        path: data/harbor_adapters/**/*.parquet
---

# Harbor Adapters — Agent Trajectories

> Complete agent execution trajectories from a large-scale agentic evaluation —
> every `(agent × model × task)` rollout with its full step log, tool calls,
> model output, and verifier scoring.

Each trajectory is a single (agent, model) run on one task: the agent's steps and
tool calls, the model's outputs, the environment's responses, and the verifier's
reward. Start from the manifest to filter down, then pull only the trajectories
you need.

| config | what it covers |
|---|---|
| **`manifest`** | one row per cell; metadata only, no trajectory bytes. Filter here first. |
| **`trajectories`** | one row per trial; the full trial directory as `.tar.gz` archive bytes. |

---

## 🚀 Quick Start

```python
from datasets import load_dataset

# 1. browse the catalog (no trajectory bytes)
cat = load_dataset("kendx/Harbor-Adapter", "manifest", split="full")

# 2. stream the trajectories
traj = load_dataset("kendx/Harbor-Adapter", "trajectories",
                    split="full", streaming=True)
row = next(iter(traj))          # {'trial_id', 'archive' (bytes), 'archive_sha256'}
```

---

## 📦 Repository Layout

```
harbor_adapters.manifest.parquet     # catalog: one row per cell, with its trial_ids
data/
└── harbor_adapters/<benchmark>/NNNNN.parquet   # trajectories: trial_id + archive bytes
```

A **cell** is one `(benchmark, task, model, agent)` combination, i.e. one row of
the manifest. Each cell keeps up to its 5 most recent trials.

---

## 🗂️ Schema

### Manifest (One Row per Cell)

| column | type | description | example |
|---|---|---|---|
| `benchmark` | string | the benchmark the task belongs to | `swebench-verified` |
| `task_name` | string | the task that was evaluated | `astropy__astropy-12907` |
| `agent` | string | the agent scaffold that drove the model | `claude-code` |
| `model` | string | the model under evaluation (canonical name) | `claude-opus-4-6` |
| `trial_ids` | list&lt;string&gt; | the trials in this cell, each an independent attempt at the task | `["783f7182-…", …]` |

### Trajectory (One Row per Trial)

| column | type | description |
|---|---|---|
| `trial_id` | string | unique ID of one trial, a single independent attempt at the task |
| `archive` | binary | the complete trial directory, packed as a gzipped tarball (`.tar.gz` bytes) |
| `archive_sha256` | string | SHA-256 checksum of the `archive` bytes |

---

## 🔧 Usage

Filter the manifest first, then fetch only the trajectories you need. The manifest
carries no archive bytes, so scanning it is cheap; the `data/` shards are large, so
pull just the benchmark folder and rows you want.

### 1. Browse the Catalog

The manifest is one row per cell (`benchmark`, `task_name`, `agent`, `model`,
`trial_ids`). Read it with pandas over `hf://` without downloading any trajectory
bytes:

```python
import pandas as pd

REPO = "hf://datasets/kendx/Harbor-Adapter"
m = pd.read_parquet(f"{REPO}/harbor_adapters.manifest.parquet")

print(m.benchmark.nunique(), "benchmarks")
print(m.model.value_counts().head())                 # cells per model
sub = m[(m.benchmark == "swebench-verified") & (m.agent == "claude-code")]
print(sub[["task_name", "model", "trial_ids"]].head())
```

The manifest is also exposed as the default `manifest` config:

```python
from datasets import load_dataset
cat = load_dataset("kendx/Harbor-Adapter", "manifest", split="full")
```

### 2. Resolve a Cell to Its Trial IDs

Each manifest row lists up to five `trial_ids`, most recent first:

```python
row = m[(m.benchmark == "gso") & (m.model == "gpt-5.4") & (m.agent == "codex")].iloc[0]
trial_ids = row["trial_ids"]          # e.g. ["6434b333-…", "1b90…", …]
latest = trial_ids[0]                  # most recent trial for this cell
```

### 3. Fetch the Trajectories for a Slice

Read only the relevant benchmark folder and filter to the trial IDs you want.
DuckDB pushes the filter down so only matching row groups are scanned:

```python
import duckdb

ids = "', '".join(trial_ids)
df = duckdb.sql(f"""
    SELECT trial_id, archive, archive_sha256
    FROM '{REPO}/data/harbor_adapters/gso/*.parquet'
    WHERE trial_id IN ('{ids}')
""").df()
```

Equivalent with pandas, reading one benchmark folder:

```python
df = pd.read_parquet(f"{REPO}/data/harbor_adapters/swebench-verified/")
df = df[df.trial_id.isin(trial_ids)]
```

### 4. Stream a Whole Subset

To iterate every trajectory without downloading it all at once, use the
`trajectories` config in streaming mode:

```python
from datasets import load_dataset

ds = load_dataset("kendx/Harbor-Adapter", "trajectories", split="full", streaming=True)
for row in ds:
    trial_id, archive = row["trial_id"], row["archive"]
    ...                                # row also has archive_sha256
```

### 5. Verify and Unpack an Archive

`archive` is the gzipped tarball; `archive_sha256` is its checksum. Verify, then
unpack to the original trial directory:

```python
import io, hashlib, tarfile

rec = df.iloc[0]
assert hashlib.sha256(rec["archive"]).hexdigest() == rec["archive_sha256"]

tar = tarfile.open(fileobj=io.BytesIO(rec["archive"]), mode="r:gz")
tar.extractall(f"./{rec['trial_id']}")   # -> result.json, config.json, agent/, verifier/, …
```

### 6. Read Reward and Tokens From an Archive

Token usage lives in `result.json` under `agent_result`, and the final reward is
written to `verifier/reward.txt`. Read them straight from the in-memory tarball:

```python
import io, json, tarfile

tar = tarfile.open(fileobj=io.BytesIO(rec["archive"]), mode="r:gz")
members = {m.name.split("/", 1)[-1]: m for m in tar.getmembers() if m.isfile()}

result = json.load(tar.extractfile(members["result.json"]))
ar = result["agent_result"]
print(ar["n_input_tokens"], ar["n_output_tokens"], ar["n_cache_tokens"])

reward = tar.extractfile(members["verifier/reward.txt"]).read().decode().strip()
print(reward)
```

---

## 📁 Inside Each Trajectory Archive

Each tarball unpacks to one trial directory:

- `result.json` — reward, token usage, cost, timings, and the run config
- `config.json` — task, agent, environment, and verifier configuration
- `agent/trajectory.json` — standardized step-by-step trajectory (`steps`, `final_metrics`)
- `agent/…` — the agent's native logs (terminal output, session records, per-command output)
- `verifier/` — scoring detail (`reward.txt`, `report.json` or `judgment.json`, test output)
