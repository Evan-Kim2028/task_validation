"""2x2 sample of SWE-bench 2024 labels × static OOF risk. Does not run Docker."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _bucket(y: int, p: float, median: float) -> str:
    risk = "low" if p <= median else "high"
    lab = "invalid" if y else "valid"
    return f"{lab}_{risk}"


def sample_2x2(
    oof_path: Path,
    *,
    n_per_cell: int = 5,
    salt: str = "swe-2x2-v0",
    extra: int = 2,
) -> dict:
    """Stratify on conservative Y and OOF logistic risk. Diversify repos.

    extra: spare IDs per cell if a later Docker pull fails.
    Total default 5*4=20, plus 2*4=8 spare = 28 listed, run 20.
    """
    rows = []
    with oof_path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            rows.append(rec)
    def median(xs: list[float]) -> float:
        s = sorted(xs)
        return s[len(s) // 2]

    p_valid = [float(r["p_logistic"]) for r in rows if int(r["y"]) == 0]
    p_invalid = [float(r["p_logistic"]) for r in rows if int(r["y"]) == 1]
    med_valid = median(p_valid) if p_valid else 0.5
    med_invalid = median(p_invalid) if p_invalid else 0.5
    cells: dict[str, list[dict]] = {
        "valid_low": [],
        "valid_high": [],
        "invalid_low": [],
        "invalid_high": [],
    }
    for r in rows:
        y = int(r["y"])
        p = float(r["p_logistic"])
        cut = med_invalid if y else med_valid
        cells[_bucket(y, p, cut)].append(r)

    def pick(cell: str, items: list[dict], n: int) -> list[dict]:
        keyed = []
        for r in items:
            h = hashlib.sha256(f"{salt}:{cell}:{r['task_id']}".encode()).hexdigest()
            keyed.append((h, r))
        keyed.sort(key=lambda t: t[0])
        chosen: list[dict] = []
        seen_repo: set[str] = set()
        # First pass: unique repos
        for _, r in keyed:
            repo = r.get("repository") or r["task_id"].split("__")[0]
            if repo in seen_repo:
                continue
            chosen.append(r)
            seen_repo.add(repo)
            if len(chosen) >= n:
                return chosen
        # Fill
        have = {c["task_id"] for c in chosen}
        for _, r in keyed:
            if r["task_id"] in have:
                continue
            chosen.append(r)
            if len(chosen) >= n:
                break
        return chosen

    n_list = n_per_cell + extra
    selected: dict[str, list[dict]] = {}
    run_ids: list[str] = []
    spare_ids: list[str] = []
    for name, items in cells.items():
        picked = pick(name, items, n_list)
        selected[name] = [
            {
                "task_id": r["task_id"],
                "repository": r.get("repository"),
                "y": int(r["y"]),
                "p_logistic": float(r["p_logistic"]),
                "cell": name,
            }
            for r in picked
        ]
        run_ids.extend([r["task_id"] for r in picked[:n_per_cell]])
        spare_ids.extend([r["task_id"] for r in picked[n_per_cell:]])

    return {
        "design": "2x2 valid/invalid × low/high OOF logistic risk",
        "y": "openai_2024_conservative",
        "static_score": "grouped OOF logistic p_logistic",
        "median_p_logistic_valid": med_valid,
        "median_p_logistic_invalid": med_invalid,
        "n_per_cell_run": n_per_cell,
        "n_per_cell_listed": n_list,
        "salt": salt,
        "n_population": len(rows),
        "cell_sizes_population": {k: len(v) for k, v in cells.items()},
        "run_ids": run_ids,
        "spare_ids": spare_ids,
        "cells": selected,
        "executed": False,
        "minimum_suite": ["reference", "base_revert", "nop"],
        "do_not_invent_boundary": True,
        "note": (
            "n=20 is a directional probe, not a decision-grade retain-tail. "
            "Gold vs base is how SWE-bench is built; it may not separate 2024 fairness labels. "
            "That null is a Reconsider trigger, not a retune trigger."
        ),
    }
