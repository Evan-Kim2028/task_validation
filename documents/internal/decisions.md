# Decisions (working log)

ADRs in `documents/adrs/` are the frozen ones. This file is the running list.

- 2026-09-11 Repo name `task_validation` (user's phrase). Not EvalQA as the repo name. EvalQA-Gold is the dataset name inside the repo.
- 2026-09-11 Documents live in `documents/`, not `docs/`, as requested.
- 2026-09-11 Stdlib-only Python. No scipy/pandas runtime dependency. Tests use pytest if present, or `python3 -m pytest` with PYTHONPATH=src.
- 2026-09-11 Hybrid UCB computed from SRS arm only until HT on the union is simulated at 2,000 replicates.
- 2026-09-11 Approach A for the first human slice (protocol is the reference standard).
- 2026-09-11 Do not copy `eval_tasks/jobs/` into this tree.
- 2026-09-11 Compact gold committed; full notes JSONL gitignored; 3-rater CSV gitignored; ensemble CSV kept under `data/raw/` if present.
- 2026-09-11 Skip `scripts/checks/test-tasks` and `hello-world` in the human queue.
- 2026-09-11 Sealed calibration is 5 valid + 5 invalid SWE-bench 2024 labels, hashed pick, not the reviewer's first slice.
