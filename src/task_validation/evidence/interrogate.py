"""Interrogate a verifier with controlled implementations.

Intended labels come from the task spec / reference, not from the tests.
Do not collapse the five rates. Observe-only and unavailable stay out of the rates.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from task_validation.evidence.mutation import harbor_file_mutants
from task_validation.evidence.runner import run_harbor_trial
from task_validation.ingest.harbor_task import _parse_toml_lite, _read, discover_tasks

_IGNORE = shutil.ignore_patterns("__pycache__", ".git", ".pytest_cache", "*.pyc")

TREATMENTS = (
    "reference",
    "preserve",
    "preserve_equivalent",
    "nop",
    "remove_required",
    "revert_gold",
    "alter_output",
    "break_boundary",
    "observe",
)


@dataclass(frozen=True)
class ProbeSpec:
    probe_id: str
    family: str
    intended: str  # accept | reject | observe | none
    agent: str  # oracle | nop | ""
    kind: str
    note: str
    availability: str = "runnable"  # runnable | observe | unavailable
    label_source: str = "reference_solution"
    unavailable_reason: str | None = None


def _mean(xs: list[float]) -> float | None:
    return (sum(xs) / len(xs)) if xs else None


def discrimination_rates(trials: list[dict]) -> dict:
    """Uncollapsed rates. Complements are reported separately on purpose."""

    def accepted(row: dict) -> bool | None:
        if row.get("availability") == "unavailable":
            return None
        r = row.get("reward")
        if r is None:
            return None
        return r == 1.0

    ref: list[float] = []
    preserve: list[float] = []
    pos: list[float] = []
    neg: list[float] = []
    n_exec = 0
    n_fail = 0
    n_unavail = 0
    n_observe = 0
    for row in trials:
        if row.get("availability") == "unavailable":
            n_unavail += 1
            continue
        if row.get("intended") == "observe":
            if row.get("reward") is not None:
                n_observe += 1
            else:
                n_fail += 1
            continue
        ok = accepted(row)
        if ok is None:
            n_fail += 1
            continue
        n_exec += 1
        bit = 1.0 if ok else 0.0
        if row["family"] == "reference":
            ref.append(bit)
        if row["family"].startswith("preserve"):
            preserve.append(bit)
        if row["intended"] == "accept":
            pos.append(bit)
        elif row["intended"] == "reject":
            neg.append(bit)
    return {
        "correct_accept": _mean(ref),
        "variant_accept": _mean(preserve),
        "incorrect_reject": _mean([1.0 - x for x in neg]),
        "false_accept": _mean(neg),
        "false_reject": _mean([1.0 - x for x in pos]),
        "correct_accept_rate": _mean(ref),
        "legitimate_variant_accept_rate": _mean(preserve),
        "incorrect_reject_rate": _mean([1.0 - x for x in neg]),
        "false_accept_rate": _mean(neg),
        "false_reject_rate": _mean([1.0 - x for x in pos]),
        "n_reference": len(ref),
        "n_preserve": len(preserve),
        "n_positive": len(pos),
        "n_negative": len(neg),
        "n_executed": n_exec,
        "n_failed_to_execute": n_fail,
        "n_unavailable": n_unavail,
        "n_observe": n_observe,
        "interrogable": len(pos) >= 1 and len(neg) >= 1,
    }


def task_kind(task_dir: Path) -> str:
    if task_dir.name == "hello-world":
        return "hello-world"
    inst = ""
    p = task_dir / "instruction.md"
    if p.is_file():
        inst = p.read_text(encoding="utf-8", errors="replace")
    if "hello.txt" in inst and "Hello, world!" in inst:
        return "hello-world"
    return "harbor"


def _unavailable(probe_id: str, family: str, reason: str) -> ProbeSpec:
    return ProbeSpec(
        probe_id=probe_id,
        family=family,
        intended="none",
        agent="",
        kind="unavailable",
        note=reason,
        availability="unavailable",
        label_source="unavailable",
        unavailable_reason=reason,
    )


def probe_catalog(task_dir: Path) -> list[ProbeSpec]:
    """Spec-grounded probes. No frontier model. No new tasks.

    Treatments that cannot be labeled from the instruction/reference are
    recorded as unavailable. They are not reverse-engineered from tests.
    """
    kind = task_kind(task_dir)
    solve = task_dir / "solution" / "solve.sh"
    has_solve = solve.is_file()
    probes: list[ProbeSpec] = []
    if has_solve:
        probes.append(
            ProbeSpec(
                "reference",
                "reference",
                "accept",
                "oracle",
                "none",
                "unmodified official solution",
                "runnable",
                "reference_solution",
            )
        )
        probes.append(
            ProbeSpec(
                "preserve_comments",
                "preserve",
                "accept",
                "oracle",
                "comments",
                "comment-only change to solve.sh",
                "runnable",
                "known_semantics",
            )
        )
    else:
        probes.append(_unavailable("reference", "reference", "no solution/solve.sh"))
        probes.append(_unavailable("preserve_comments", "preserve", "no solution/solve.sh"))
    probes.append(
        ProbeSpec(
            "nop",
            "nop",
            "reject",
            "nop",
            "none",
            "empty agent",
            "runnable",
            "known_semantics",
        )
    )
    if has_solve:
        probes.append(
            ProbeSpec(
                "remove_required",
                "remove_required",
                "reject",
                "oracle",
                "drop_last_apply",
                "omit a required solution apply, or write nothing",
                "runnable",
                "known_semantics",
            )
        )
    else:
        probes.append(_unavailable("remove_required", "remove_required", "no solution/solve.sh"))
    if harbor_file_mutants(task_dir):
        probes.append(
            ProbeSpec(
                "revert_gold",
                "revert_gold",
                "reject",
                "oracle",
                "revert_env",
                "replace solution files with environment copies",
                "runnable",
                "known_semantics",
            )
        )
    else:
        probes.append(
            _unavailable(
                "revert_gold",
                "revert_gold",
                "no differing environment/solution file pair",
            )
        )
    if kind == "hello-world":
        probes.extend(
            [
                ProbeSpec(
                    "preserve_echo",
                    "preserve_equivalent",
                    "accept",
                    "oracle",
                    "hello_echo",
                    "equivalent write of Hello, world!",
                    "runnable",
                    "instruction",
                ),
                ProbeSpec(
                    "alter_output",
                    "alter_output",
                    "reject",
                    "oracle",
                    "hello_goodbye",
                    "wrong required output",
                    "runnable",
                    "instruction",
                ),
                ProbeSpec(
                    "break_case",
                    "break_boundary",
                    "reject",
                    "oracle",
                    "hello_case",
                    "required string, wrong case",
                    "runnable",
                    "instruction",
                ),
                ProbeSpec(
                    "strip_spaces",
                    "observe",
                    "observe",
                    "oracle",
                    "hello_spaces",
                    "leading/trailing spaces; spec vs strip() is not labeled",
                    "observe",
                    "instruction",
                ),
            ]
        )
    else:
        probes.append(
            _unavailable(
                "preserve_equivalent",
                "preserve_equivalent",
                "no spec-grounded equivalent rewrite (would require reading tests)",
            )
        )
        probes.append(
            _unavailable(
                "alter_output",
                "alter_output",
                "required output not pinned in the instruction as a literal",
            )
        )
        probes.append(
            _unavailable(
                "break_boundary",
                "break_boundary",
                "no spec-grounded near-miss without reading tests",
            )
        )
        probes.append(
            _unavailable(
                "observe",
                "observe",
                "no spec-ambiguous probe constructed",
            )
        )
    return probes


def treatment_coverage(probes: list[ProbeSpec]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for spec in probes:
        slot = out.setdefault(
            spec.family,
            {"status": spec.availability, "n": 0, "unavailable_reason": spec.unavailable_reason},
        )
        slot["n"] += 1
        if spec.availability == "unavailable":
            slot["status"] = "unavailable"
        elif spec.availability == "observe" and slot["status"] != "unavailable":
            slot["status"] = "observe"
        elif spec.availability == "runnable" and slot["status"] not in {"unavailable", "observe"}:
            slot["status"] = "tested"
    for name in TREATMENTS:
        out.setdefault(name, {"status": "unavailable", "n": 0, "unavailable_reason": "not in catalog"})
    return out


def apply_probe(task_dir: Path, spec: ProbeSpec) -> None:
    solve = task_dir / "solution" / "solve.sh"
    if spec.kind in {"none", "unavailable"}:
        return
    if spec.kind == "comments":
        text = solve.read_text(encoding="utf-8") if solve.is_file() else "#!/bin/bash\n"
        if not text.endswith("\n"):
            text += "\n"
        text += "# behavior-preserving comment; no output change\n"
        _write_solve(solve, text)
        return
    if spec.kind == "hello_echo":
        _write_solve(solve, "#!/bin/bash\necho 'Hello, world!' > /app/hello.txt\n")
        return
    if spec.kind == "hello_goodbye":
        _write_solve(solve, "#!/bin/bash\nprintf 'Goodbye, world!\\n' > /app/hello.txt\n")
        return
    if spec.kind == "hello_case":
        _write_solve(solve, "#!/bin/bash\nprintf 'hello, world!\\n' > /app/hello.txt\n")
        return
    if spec.kind == "hello_spaces":
        _write_solve(solve, "#!/bin/bash\nprintf ' Hello, world! \\n' > /app/hello.txt\n")
        return
    if spec.kind in {"drop_last_cp", "drop_last_apply"}:
        raw = solve.read_text(encoding="utf-8") if solve.is_file() else ""
        _write_solve(solve, drop_last_apply(raw))
        return
    if spec.kind == "revert_env":
        for mut in harbor_file_mutants(task_dir):
            src = task_dir / mut["environment"]
            dst = task_dir / mut["solution"]
            if src.is_file() and dst.is_file():
                dst.write_bytes(src.read_bytes())
        return
    raise ValueError(f"unknown probe kind {spec.kind}")


def _write_solve(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o755)


def _is_apply_line(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("cp ") or s.startswith("install ") or s.startswith("python3 ")


def drop_last_apply(text: str) -> str:
    lines = text.splitlines(keepends=True)
    idxs = [i for i, line in enumerate(lines) if _is_apply_line(line)]
    if not idxs:
        return "#!/bin/bash\nexit 0\n"
    del lines[idxs[-1]]
    body = "".join(lines).strip()
    if not body or body in {"#!/bin/bash", "#!/bin/sh"}:
        return "#!/bin/bash\nexit 0\n"
    return "".join(lines)


def materialize(src: Path, dest: Path, spec: ProbeSpec) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=_IGNORE)
    apply_probe(dest, spec)
    return dest


def verifier_timeout_sec(task_dir: Path) -> float:
    fields = _parse_toml_lite(_read(task_dir / "task.toml") or "")
    try:
        return float(fields.get("verifier.timeout_sec") or 180)
    except ValueError:
        return 180.0


def is_complete_package(task_dir: Path) -> bool:
    return (
        (task_dir / "instruction.md").is_file()
        and (task_dir / "task.toml").is_file()
        and (task_dir / "environment" / "Dockerfile").is_file()
        and (task_dir / "tests" / "test.sh").is_file()
        and (task_dir / "solution" / "solve.sh").is_file()
    )


def complete_packages(root: Path) -> list[Path]:
    skip_parts = {"scripts", "research", "jobs", "tb-ref", "vendor"}
    out = []
    for d in discover_tasks(root):
        if any(p in skip_parts for p in d.parts):
            continue
        if is_complete_package(d):
            out.append(d)
    return out


def package_meta(task_dir: Path, source_root: Path | None = None) -> dict:
    fields = _parse_toml_lite(_read(task_dir / "task.toml") or "")
    rel = task_dir.name
    if source_root is not None and (source_root in task_dir.parents or task_dir == source_root):
        rel = str(task_dir.relative_to(source_root)).replace("\\", "/")
    family = "experimental" if "experimental" in Path(rel).parts else "tasks"
    return {
        "task_id": rel,
        "benchmark": "eval_tasks",
        "benchmark_version": "local",
        "task_source": "eval_tasks",
        "task_family": fields.get("metadata.subcategory") or family,
        "language": "python",
        "verifier": {
            "identifier": "harbor-official",
            "environment_mode": fields.get("verifier.environment_mode"),
            "timeout_sec": verifier_timeout_sec(task_dir),
            "task_name": fields.get("task.name"),
        },
    }


def interrogate_verifier(
    task_dir: Path,
    work_root: Path,
    *,
    timeout: int | None = 180,
    source_root: Path | None = None,
) -> dict:
    task_dir = task_dir.resolve()
    meta = package_meta(task_dir, source_root)
    slug = task_dir.name
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    jobs_out = work_root / "jobs"
    copies = work_root / "probes" / slug
    vto = verifier_timeout_sec(task_dir)
    cap = int(timeout) if timeout else 600
    trial_timeout = min(int(vto) + 90, cap)
    trial_timeout = max(trial_timeout, 120)
    probes = probe_catalog(task_dir)
    trials: list[dict] = []
    infra: list[dict] = []
    failures: list[dict] = []
    observe_findings: list[dict] = []
    t0_all = 0.0
    for spec in probes:
        row = asdict(spec)
        if spec.availability == "unavailable":
            row.update(
                {
                    "reward": None,
                    "accepted": None,
                    "elapsed_sec": 0.0,
                    "returncode": None,
                    "stderr_tail": "",
                    "status": "unavailable",
                }
            )
            trials.append(row)
            continue
        dest = copies / spec.probe_id
        materialize(task_dir, dest, spec)
        name = f"{slug}-{spec.probe_id}-{stamp}"
        run = run_harbor_trial(dest, spec.agent, jobs_out, name, trial_timeout)
        accepted = None if run["reward"] is None else run["reward"] == 1.0
        status = "executed" if run["reward"] is not None else "failed"
        row.update(
            {
                "reward": run["reward"],
                "accepted": accepted,
                "elapsed_sec": run["elapsed_sec"],
                "returncode": run["returncode"],
                "stderr_tail": run["stderr_tail"],
                "status": status,
            }
        )
        trials.append(row)
        t0_all += float(run["elapsed_sec"] or 0)
        if status == "failed":
            item = {
                "probe_id": spec.probe_id,
                "returncode": run["returncode"],
                "stderr_tail": run["stderr_tail"],
            }
            failures.append(item)
            if run["returncode"] is None or run["returncode"] != 0:
                infra.append(item)
        if spec.intended == "observe" and accepted is not None:
            observe_findings.append(
                {
                    "probe_id": spec.probe_id,
                    "reward": run["reward"],
                    "note": spec.note,
                }
            )
    rates = discrimination_rates(trials)
    ref = next((t for t in trials if t["probe_id"] == "reference"), None)
    nop = next((t for t in trials if t["probe_id"] == "nop"), None)
    return {
        **meta,
        "path": str(task_dir),
        "kind": task_kind(task_dir),
        "interrogation_id": f"{slug}-{stamp}",
        "executed": True,
        "metadata_inferred": False,
        "trial_timeout_sec": trial_timeout,
        "trials": trials,
        "rates": rates,
        "coverage": treatment_coverage(probes),
        "oracle_status": None if ref is None else ref.get("accepted"),
        "nop_status": None if nop is None else (nop.get("accepted") is False),
        "determinism": None,
        "environment_execution_status": "ok" if rates["n_failed_to_execute"] == 0 else "partial_or_failed",
        "observe_findings": observe_findings,
        "interrogation_failures": failures,
        "infrastructure_failures": infra,
        "elapsed_sec_total": t0_all,
        "field_provenance": {
            "rates": "official Harbor reward.txt on spec-labeled probes",
            "intended_labels": "instruction / reference_solution / known_semantics; never tests",
            "human_validity_label": "not joined",
            "determinism": "not_run",
        },
    }


def summarize_records(rows: list[dict]) -> dict:
    n = len(rows)
    interrogable = sum(1 for r in rows if (r.get("rates") or {}).get("interrogable"))
    costs = [float(r.get("elapsed_sec_total") or 0) for r in rows]
    feasible: dict[str, int] = {k: 0 for k in TREATMENTS}
    for r in rows:
        cov = r.get("coverage") or {}
        for k, slot in cov.items():
            if (slot or {}).get("status") in {"tested", "observe"}:
                feasible[k] = feasible.get(k, 0) + 1

    def avg_rate(key: str) -> float | None:
        xs = [r["rates"][key] for r in rows if r.get("rates") and r["rates"].get(key) is not None]
        return _mean(xs)

    return {
        "n_tasks": n,
        "n_interrogable": interrogable,
        "interrogable_frac": (interrogable / n) if n else None,
        "elapsed_sec_mean": _mean(costs),
        "elapsed_sec_total": sum(costs),
        "treatment_feasible_n": feasible,
        "mean_correct_accept": avg_rate("correct_accept"),
        "mean_variant_accept": avg_rate("variant_accept"),
        "mean_incorrect_reject": avg_rate("incorrect_reject"),
        "mean_false_accept": avg_rate("false_accept"),
        "mean_false_reject": avg_rate("false_reject"),
        "n_with_observe_findings": sum(1 for r in rows if r.get("observe_findings")),
        "n_with_infra_failure": sum(1 for r in rows if r.get("infrastructure_failures")),
        "static_metadata_baseline": {
            "note": "negative baseline; not rerun",
            "change_causality_auroc_2024": 0.41,
            "contract_provenance_auroc_2024": 0.42,
        },
    }


def load_done_ids(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.is_file():
        return done
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            done.add(rec["task_id"])
    return done


def append_jsonl(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def matrix_row(rec: dict) -> dict:
    """X_task scaffolding. No human Y. No composite verifier score."""
    rates = rec.get("rates") or {}
    cov = rec.get("coverage") or {}
    return {
        "task_id": rec.get("task_id"),
        "benchmark": rec.get("benchmark"),
        "task_family": rec.get("task_family"),
        "language": rec.get("language"),
        "interrogable": rates.get("interrogable"),
        "correct_accept": rates.get("correct_accept"),
        "variant_accept": rates.get("variant_accept"),
        "incorrect_reject": rates.get("incorrect_reject"),
        "false_accept": rates.get("false_accept"),
        "false_reject": rates.get("false_reject"),
        "n_executed": rates.get("n_executed"),
        "n_unavailable": rates.get("n_unavailable"),
        "n_observe": rates.get("n_observe"),
        "n_failed_to_execute": rates.get("n_failed_to_execute"),
        "oracle_status": rec.get("oracle_status"),
        "nop_status": rec.get("nop_status"),
        "environment_execution_status": rec.get("environment_execution_status"),
        "elapsed_sec_total": rec.get("elapsed_sec_total"),
        "preserve_equivalent_status": (cov.get("preserve_equivalent") or {}).get("status"),
        "revert_gold_status": (cov.get("revert_gold") or {}).get("status"),
        "has_observe_finding": bool(rec.get("observe_findings")),
        "has_infra_failure": bool(rec.get("infrastructure_failures")),
    }
