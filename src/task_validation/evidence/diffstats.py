"""Unified-diff and identifier helpers. No Docker."""

from __future__ import annotations

import json
import re

IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
STOP = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "from",
    "not",
    "are",
    "was",
    "were",
    "have",
    "has",
    "had",
    "but",
    "you",
    "all",
    "can",
    "def",
    "class",
    "return",
    "import",
    "from",
    "test",
    "assert",
    "self",
    "none",
    "true",
    "false",
    "int",
    "str",
    "list",
    "dict",
    "print",
}


def parse_json_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
        return [str(parsed)]
    return [str(value)]


def identifiers(text: str) -> set[str]:
    found = set()
    for tok in IDENT_RE.findall(text or ""):
        low = tok.lower()
        if low in STOP or len(tok) < 3:
            continue
        found.add(tok)
    return found


def diff_stats(diff: str) -> dict[str, int]:
    files: set[str] = set()
    hunks = 0
    plus = 0
    minus = 0
    for line in (diff or "").splitlines():
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 4:
                name = parts[-1]
                files.add(name[2:] if name.startswith("b/") else name)
        elif line.startswith("@@"):
            hunks += 1
        elif line.startswith("+") and not line.startswith("+++"):
            plus += 1
        elif line.startswith("-") and not line.startswith("---"):
            minus += 1
    return {
        "n_files": len(files),
        "n_hunks": hunks,
        "n_plus": plus,
        "n_minus": minus,
        "n_changed_lines": plus + minus,
    }


def file_hunks(diff: str) -> dict[str, int]:
    """Count hunks per file in a unified diff."""
    current = None
    counts: dict[str, int] = {}
    for line in (diff or "").splitlines():
        if line.startswith("diff --git"):
            parts = line.split()
            current = parts[-1][2:] if len(parts) >= 4 and parts[-1].startswith("b/") else (parts[-1] if parts else None)
            if current and current not in counts:
                counts[current] = 0
        elif line.startswith("@@") and current:
            counts[current] = counts.get(current, 0) + 1
    return counts
