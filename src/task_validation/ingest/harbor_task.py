"""Ingest Harbor / Terminal-Bench style task directories.

This adapter reads local files. It does not run Docker. Oracle, nop, and
cheat outcomes are attached later from a jobs index when present.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from task_validation.schema import EvidenceVector, GoldRow

CANARY_RE = re.compile(
    r"harbor-canary GUID\s+([0-9a-fA-F-]{36})",
    re.IGNORECASE,
)


def _read(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_toml_lite(text: str) -> dict[str, str]:
    """Tiny TOML key=value scraper. Avoids a tomllib dependency on comments."""
    out: dict[str, str] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        out[f"{section}.{key}" if section else key] = val
    return out


def discover_tasks(root: Path) -> list[Path]:
    found = []
    for toml_path in sorted(root.rglob("task.toml")):
        if any(p in toml_path.parts for p in (".git", "jobs", "tb-ref", "vendor")):
            continue
        found.append(toml_path.parent)
    return found


def ingest_task(task_dir: Path, *, source_root: Path) -> GoldRow:
    rel = task_dir.relative_to(source_root) if source_root in task_dir.parents or task_dir == source_root else Path(task_dir.name)
    toml_text = _read(task_dir / "task.toml") or ""
    fields = _parse_toml_lite(toml_text)
    instruction = _read(task_dir / "instruction.md") or ""
    canary = None
    m = CANARY_RE.search(instruction) or CANARY_RE.search(toml_text)
    if m:
        canary = m.group(1)
    has_solution = (task_dir / "solution").is_dir()
    has_tests = (task_dir / "tests").is_dir()
    has_env = (task_dir / "environment").is_dir()
    test_files = list((task_dir / "tests").rglob("test*.py")) if has_tests else []
    name = fields.get("task.name") or task_dir.name
    return GoldRow(
        task_id=str(rel).replace("\\", "/"),
        benchmark="eval_tasks",
        benchmark_version="local",
        provenance="PENDING_HUMAN",
        language="python",
        repository=None,
        domain=fields.get("metadata.category") or fields.get("metadata.subcategory"),
        human_validity_label="pending",
        human_label_provenance="PENDING_HUMAN",
        human_severity=None,
        n_raters=0,
        difficulty=fields.get("metadata.expert_time_estimate_hours"),
        evidence=EvidenceVector(
            oracle_pass=None,
            nop_fail=None,
            environment_builds=None,
            static_checks={
                "has_instruction": bool(instruction),
                "has_task_toml": bool(toml_text),
                "has_solution": has_solution,
                "has_tests": has_tests,
                "has_environment": has_env,
                "n_test_py": len(test_files),
                "canary_guid": canary,
                "environment_mode": fields.get("verifier.environment_mode"),
                "separate_verifier": fields.get("verifier.environment_mode") == "separate",
            },
        ),
        artifacts={
            "path": str(task_dir),
            "relpath": str(rel),
            "instruction_chars": len(instruction),
            "instruction_preview": instruction[:400],
            "category": fields.get("metadata.category"),
            "subcategory": fields.get("metadata.subcategory"),
            "description": fields.get("task.description"),
        },
    )


def ingest_tree(root: Path) -> list[GoldRow]:
    root = root.resolve()
    return [ingest_task(d, source_root=root) for d in discover_tasks(root)]


def write_jsonl(rows: list[GoldRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")
