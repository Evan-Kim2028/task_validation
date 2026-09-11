"""Deeper Harbor static evidence. Still no Docker."""

from __future__ import annotations

from pathlib import Path

from task_validation.evidence.diffstats import identifiers
from task_validation.ingest.harbor_task import _parse_toml_lite, _read


def harbor_cheap_features(task_dir: Path) -> dict[str, float | int | bool | str | None]:
    instruction = _read(task_dir / "instruction.md") or ""
    toml_text = _read(task_dir / "task.toml") or ""
    fields = _parse_toml_lite(toml_text)
    env_df = _read(task_dir / "environment" / "Dockerfile") or ""
    test_df = _read(task_dir / "tests" / "Dockerfile") or ""
    test_sh = _read(task_dir / "tests" / "test.sh") or ""
    solve = _read(task_dir / "solution" / "solve.sh") or ""
    test_py = []
    tests_root = task_dir / "tests"
    if tests_root.is_dir():
        test_py = [p.read_text(encoding="utf-8", errors="replace") for p in tests_root.rglob("test*.py")]
    tests_blob = "\n".join(test_py)
    env_py_names = set()
    env_root = task_dir / "environment"
    if env_root.is_dir():
        env_py_names = {p.name for p in env_root.rglob("*.py")}
    sol_root = task_dir / "solution"
    sol_py_names = {p.name for p in sol_root.rglob("*.py")} if sol_root.is_dir() else set()
    stmt_ids = identifiers(instruction)
    test_ids = identifiers(tests_blob)
    overlap = (len(stmt_ids & test_ids) / len(test_ids)) if test_ids else 0.0
    only = (len(test_ids - stmt_ids) / len(test_ids)) if test_ids else 0.0
    solution_in_env_df = any(name in env_df for name in ("solution", "solve.sh")) if env_df else False
    tests_copied_into_env = "COPY tests" in env_df or "/tests" in env_df
    return {
        "instruction_chars": len(instruction),
        "n_test_py": len(test_py),
        "n_env_py": len(env_py_names),
        "n_sol_py": len(sol_py_names),
        "sol_env_name_overlap": len(sol_py_names & env_py_names),
        "separate_verifier": fields.get("verifier.environment_mode") == "separate",
        "has_tests_dockerfile": bool(test_df),
        "has_solve_sh": bool(solve),
        "test_stmt_id_overlap": overlap,
        "test_only_id_frac": only,
        "env_copies_solution": solution_in_env_df,
        "env_copies_tests": tests_copied_into_env,
        "test_sh_mentions_nobody": "nobody" in test_sh or "setpriv" in test_sh,
        "test_sh_default_reward_zero": "echo 0" in test_sh or "echo 0 >" in test_sh,
        "dockerfile_has_user": "USER " in env_df,
        "allow_network": "network" in toml_text.lower() and "isolated" not in toml_text.lower(),
        "canary_in_instruction": "harbor-canary" in instruction,
        "canary_in_tests": "harbor-canary" in tests_blob,
    }
