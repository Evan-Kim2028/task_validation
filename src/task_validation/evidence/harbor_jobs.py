"""Attach existing Harbor job rewards. Does not launch Docker."""

from __future__ import annotations

from pathlib import Path


def _reward(path: Path) -> float | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        return float(text.split()[0])
    except ValueError:
        return None


def collect_job_outcomes(jobs_root: Path) -> dict[str, dict[str, float | None]]:
    """Map task slug -> latest oracle/nop/cheat reward.

    Job directory names usually contain 'oracle', 'nop', or 'cheat'.
    Nested path is jobs/<job>/<task>__<id>/verifier/reward.txt.
    """
    jobs_root = Path(jobs_root)
    best: dict[str, dict[str, tuple[float, float | None]]] = {}
    if not jobs_root.is_dir():
        return {}
    for reward_path in jobs_root.glob("*/*/verifier/reward.txt"):
        task_dir = reward_path.parents[1].name
        slug = task_dir.split("__")[0]
        job_name = reward_path.parents[2].name.lower()
        mtime = reward_path.stat().st_mtime
        value = _reward(reward_path)
        kind = None
        if "cheat" in job_name or "hack" in job_name:
            kind = "cheat"
        elif "oracle" in job_name:
            kind = "oracle"
        elif "nop" in job_name:
            kind = "nop"
        if kind is None:
            continue
        slot = best.setdefault(slug, {})
        prev = slot.get(kind)
        if prev is None or mtime >= prev[0]:
            slot[kind] = (mtime, value)
    out: dict[str, dict[str, float | None]] = {}
    for slug, kinds in best.items():
        out[slug] = {k: v[1] for k, v in kinds.items()}
    return out
