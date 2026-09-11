"""Verifier-discrimination mutants. Cheap, no frontier model.

SWE-bench: count gold-patch hunks as the mutant menu (execution later).
Harbor: each solution file that differs from the environment copy is one mutant.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from task_validation.evidence.diffstats import file_hunks


def swe_mutant_menu(patch: str) -> dict[str, object]:
    hunks = file_hunks(patch or "")
    n = sum(hunks.values())
    return {
        "n_file_targets": len(hunks),
        "n_hunk_mutants": n,
        "files": sorted(hunks),
        "executed": False,
        "kill_rate": None,
    }


def harbor_file_mutants(task_dir: Path) -> list[dict[str, str]]:
    """Pairs of (environment file, solution file) that differ."""
    env = task_dir / "environment"
    sol = task_dir / "solution"
    if not env.is_dir() or not sol.is_dir():
        return []
    env_by_name: dict[str, Path] = {p.name: p for p in env.rglob("*") if p.is_file()}
    mutants = []
    for sp in sol.rglob("*"):
        if not sp.is_file() or sp.name in {"solve.sh"}:
            continue
        ep = env_by_name.get(sp.name)
        if ep is None:
            continue
        s = sp.read_bytes()
        e = ep.read_bytes()
        if s == e:
            continue
        mutants.append(
            {
                "solution": str(sp.relative_to(task_dir)),
                "environment": str(ep.relative_to(task_dir)),
                "sol_sha": hashlib.sha256(s).hexdigest()[:12],
                "env_sha": hashlib.sha256(e).hexdigest()[:12],
            }
        )
    return mutants
