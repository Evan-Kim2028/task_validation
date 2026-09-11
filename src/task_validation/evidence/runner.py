"""Cheap Harbor execution runner. Oracle, nop, determinism, file-revert mutants.

Does not call a frontier model. Requires Harbor + Docker on the machine.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from task_validation.evidence.harbor_static import harbor_cheap_features
from task_validation.evidence.independence import CheckResult
from task_validation.evidence.mutation import harbor_file_mutants


def _run_harbor(task_dir: Path, agent: str, jobs_out: Path, name: str, timeout: int) -> dict:
    jobs_out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    cmd = [
        "harbor",
        "run",
        "-p",
        str(task_dir),
        "--agent",
        agent,
        "--env",
        "docker",
        "--yes",
        "-n",
        "1",
        "--job-name",
        name,
        "-o",
        str(jobs_out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    elapsed = time.monotonic() - t0
    reward = _latest_reward(jobs_out, name)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "elapsed_sec": elapsed,
        "reward": reward,
        "stderr_tail": (proc.stderr or "")[-800:],
    }


def _latest_reward(jobs_out: Path, job_name: str) -> float | None:
    matches = list(jobs_out.glob(f"{job_name}/*/verifier/reward.txt"))
    if not matches:
        matches = list(jobs_out.glob("*/verifier/reward.txt"))
    if not matches:
        return None
    newest = max(matches, key=lambda p: p.stat().st_mtime)
    try:
        return float(newest.read_text(encoding="utf-8").strip().split()[0])
    except ValueError:
        return None


def run_static_execution_mutation(
    task_dir: Path,
    work_root: Path,
    *,
    timeout: int = 180,
    n_oracle: int = 2,
    run_mutants: bool = True,
    max_mutants: int = 4,
) -> dict:
    task_dir = task_dir.resolve()
    slug = task_dir.name
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    jobs_out = work_root / "jobs"
    checks: list[CheckResult] = []
    static = harbor_cheap_features(task_dir)
    checks.append(
        CheckResult(
            "static_package",
            "static",
            bool(static.get("has_solve_sh") or static.get("n_sol_py")),
            dict(static),
        )
    )
    oracles = []
    for i in range(n_oracle):
        res = _run_harbor(task_dir, "oracle", jobs_out, f"{slug}-oracle-{stamp}-{i}", timeout)
        oracles.append(res)
        checks.append(
            CheckResult(
                f"oracle_{i}",
                "official_verifier",
                res["reward"] == 1.0 if res["reward"] is not None else None,
                res,
            )
        )
    nop = _run_harbor(task_dir, "nop", jobs_out, f"{slug}-nop-{stamp}", timeout)
    checks.append(
        CheckResult(
            "nop",
            "official_verifier",
            nop["reward"] == 0.0 if nop["reward"] is not None else None,
            nop,
        )
    )
    det = None
    if len(oracles) >= 2 and all(o["reward"] is not None for o in oracles):
        det = all(o["reward"] == oracles[0]["reward"] for o in oracles)
        checks.append(CheckResult("oracle_deterministic", "oracle_derived", det, {"rewards": [o["reward"] for o in oracles]}))

    mutant_rows = []
    kills = 0
    tested = 0
    if run_mutants:
        mutants = harbor_file_mutants(task_dir)
        if not mutants:
            # hello-world style: only solve.sh. Corrupt it.
            solve = task_dir / "solution" / "solve.sh"
            if solve.is_file():
                mutants = [{"solution": "solution/solve.sh", "kind": "wrong_output"}]
        for i, mut in enumerate(mutants[:max_mutants]):
            mdir = work_root / "mutants" / slug / f"m{i}"
            if mdir.exists():
                shutil.rmtree(mdir)
            shutil.copytree(task_dir, mdir, ignore=shutil.ignore_patterns("__pycache__", ".git"))
            target = mdir / mut["solution"]
            if mut.get("kind") == "wrong_output" and target.name == "solve.sh":
                target.write_text("#!/bin/bash\nprintf 'Goodbye, world!\\n' > /app/hello.txt\n", encoding="utf-8")
            elif "environment" in mut:
                src = task_dir / mut["environment"]
                if src.is_file() and target.is_file():
                    target.write_bytes(src.read_bytes())
            tested += 1
            res = _run_harbor(mdir, "oracle", jobs_out, f"{slug}-mut{i}-{stamp}", timeout)
            killed = res["reward"] == 0.0
            if killed:
                kills += 1
            mutant_rows.append(
                {
                    "mutant_id": f"{slug}-m{i}",
                    "mutation_type": mut.get("kind") or "revert_env_file",
                    "solution": mut.get("solution"),
                    "verifier_reward": res["reward"],
                    "killed": killed,
                    "elapsed_sec": res["elapsed_sec"],
                    "runtime": res["elapsed_sec"],
                }
            )
            checks.append(
                CheckResult(
                    f"mutant_{i}",
                    "mutation",
                    killed,
                    mutant_rows[-1],
                )
            )
    kill_rate = (kills / tested) if tested else None
    return {
        "task_id": slug,
        "path": str(task_dir),
        "static": static,
        "oracle": oracles,
        "nop": nop,
        "deterministic": det,
        "mutants": mutant_rows,
        "mutation_kill_rate": kill_rate,
        "n_mutants_tested": tested,
        "n_mutants_killed": kills,
        "checks": [c.to_dict() for c in checks],
        "wrong_impl_accepted_rate": (1.0 - kill_rate) if kill_rate is not None else None,
    }
