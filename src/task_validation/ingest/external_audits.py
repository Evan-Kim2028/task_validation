"""Load external audit IDs for *evaluation only*. Never as predictors."""

from __future__ import annotations

import json
import re
from pathlib import Path


def parse_june_kim_claims(claims_md: Path) -> list[str]:
    text = claims_md.read_text(encoding="utf-8", errors="replace")
    raw = re.findall(r"`(instance_[^`]+)`", text)
    prefixes = []
    for s in raw:
        s = s.replace("…", "").replace("...", "").rstrip()
        if s.startswith("instance_"):
            prefixes.append(s)
    # unique preserving order
    seen = set()
    out = []
    for p in prefixes:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def match_prefixes(task_ids: list[str], prefixes: list[str]) -> dict[str, str]:
    """Map full task_id -> matched prefix."""
    hits = {}
    for tid in task_ids:
        for p in prefixes:
            if tid.startswith(p) or p.rstrip("-") in tid:
                hits[tid] = p
                break
    return hits


def enrichment(ranked_ids: list[str], positive: set[str], ks: tuple[float, ...]) -> list[dict]:
    n = len(ranked_ids)
    n_pos = len(positive)
    base = n_pos / n if n else 0.0
    rows = []
    for frac in ks:
        k = max(1, int(round(frac * n)))
        head = ranked_ids[:k]
        hit = sum(1 for i in head if i in positive)
        rate = hit / k
        rows.append(
            {
                "top_frac": frac,
                "k": k,
                "n_positive_in_head": hit,
                "precision": rate,
                "base_rate": base,
                "enrichment": (rate / base) if base else None,
            }
        )
    return rows
