"""Non-LLM validity footprint and held-out transfer.

Footprint = execution gate + static artifact features + solve-rate band
(SWE public submissions only). No severity axes, no human labels as
features, no judge scores as inputs.

Frozen before any holdout cell or coverage count was computed:

F1. Transfer UCB covers the held-out rate in at least 4 of 5 populations
    for the verifier construct, and in at least 3 of 5 for the spec
    construct. The five populations are swe, swe_verified, swe_pro,
    tb21, harbor_index. eval_tasks is in the footprint, not in F1.

Every reported AUROC, Se/Sp, and coverage figure is from a population
or repository the calibration never saw.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

from task_validation.evidence.diffstats import diff_stats, identifiers
from task_validation.evidence.irt import auroc, bootstrap_auroc, sigmoid
from task_validation.evidence.spec_atoms import ASSERT_LINE_RE, STRING_RE, extract_atoms
from task_validation.evidence.swe_artifacts import swe_cheap_features
from task_validation.evidence.tb21_pairs import parse_cpus, parse_memory_mb
from task_validation.ingest.harbor_task import _parse_toml_lite, _read
from task_validation.sampling.estimators import (
    clopper_pearson_upper,
    srs_estimate,
)
from task_validation.sampling.judge_bound import clopper_pearson_lower, rogan_gladen

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD = REPO_ROOT / "data" / "gold"
RAW_GENERATED = REPO_ROOT / "data" / "raw" / "generated"

TB21_ROOT = Path("/home/evan/Documents/tb21-dataset/terminal-bench-2-1")
HARBOR_INDEX_ROOT = Path("/home/evan/Documents/harbor-index-dataset/harbor-index-1.0")
EVAL_TASKS_ROOT = Path("/home/evan/Documents/eval_tasks")

# Written before computing. Do not retune after seeing cells.
FROZEN_PREDICATE = (
    "the transfer UCB covers the held-out rate in at least 4 of 5 "
    "populations for the verifier construct, and in at least 3 of 5 "
    "for the spec construct"
)
TRANSFER_POPS = ("swe", "swe_verified", "swe_pro", "tb21", "harbor_index")
ALL_POPS = TRANSFER_POPS + ("eval_tasks",)
VERIFIER_REPAIR_CLASSES = frozenset({"solution_fix", "test_fix", "docker_env"})
OC_VERIFIER_CATS = frozenset({"overly_narrow_tests", "overly_broad_tests"})
SAMPLE_SEED = "footprint-generated-v0"
SPLIT_SEED = "footprint-repo-holdout-v0"
BOOT_SEED = 20260912
N_BOOT_AUROC = 400
N_BOOT_RG = 400
N_GENERATED = 200
LOGIT_L2 = 1.0
LOGIT_MAX_ITER = 40
YOUDEN_MIN = 1e-12

SMITH_HF = "SWE-bench/SWE-smith"
REBENCH_HF = "nebius/SWE-rebench"

JUDGE_FILE_NAMES = frozenset({"native_judge.py", "llm_judge.py"})
JUDGE_MARKERS = ("JUDGE_MODELS", "JUDGE_REPEATS")
TEST_NAME_RE = re.compile(r"(^|/)(tests?/|test_)|test\.(py|sh|js|ts)$", re.I)

FEATURE_NAMES = (
    "reference_pass",
    "nop_reject",
    "determinism",
    "environment_failure",
    "instruction_chars",
    "instruction_lines",
    "stmt_n_identifiers",
    "test_file_count",
    "assertion_count",
    "literal_pins_absent",
    "solution_size",
    "resource_memory_mb",
    "resource_cpus",
    "timeout_sec",
    "network_isolated",
    "judge_verifier",
    "test_stmt_id_overlap",
    "test_only_id_frac",
    "n_fail_to_pass",
    "n_pass_to_pass",
    "patch_n_files",
    "patch_n_hunks",
    "patch_n_changed_lines",
    "test_n_files",
    "test_n_hunks",
    "test_n_changed_lines",
    "has_code_fence",
    "has_traceback",
    "has_http_url",
    "has_reproduction_hint",
    "hints_chars",
    "gold_to_test_line_ratio",
    "f2p_in_statement_frac",
    "test_has_exact_string_literal",
    "solve_rate",
    "solve_rate_band",
    "n_attempted",
)

RANK_FEATURES = (
    "instruction_chars",
    "instruction_lines",
    "stmt_n_identifiers",
    "test_file_count",
    "assertion_count",
    "literal_pins_absent",
    "solution_size",
    "resource_memory_mb",
    "timeout_sec",
    "network_isolated",
    "judge_verifier",
    "test_stmt_id_overlap",
    "test_only_id_frac",
    "n_fail_to_pass",
    "n_pass_to_pass",
    "patch_n_changed_lines",
    "test_n_changed_lines",
    "has_traceback",
    "has_reproduction_hint",
    "gold_to_test_line_ratio",
)

LOG1P_FEATURES = frozenset(
    {
        "instruction_chars",
        "instruction_lines",
        "stmt_n_identifiers",
        "test_file_count",
        "assertion_count",
        "literal_pins_absent",
        "solution_size",
        "resource_memory_mb",
        "timeout_sec",
        "n_fail_to_pass",
        "n_pass_to_pass",
        "patch_n_changed_lines",
        "test_n_changed_lines",
        "hints_chars",
    }
)

LABEL_KEYS = (
    "openai_2024_conservative",
    "openai_2024_majority",
    "openai_2024_unanimous",
    "aba_major",
    "aba_minor",
    "aba_construct",
    "aba_static_major",
    "aba_trajectory_major",
    "opencompass_repaired",
    "opencompass_category",
    "june_kim_major",
    "tb21_repaired",
    "tb21_verifier_repair",
    "tb21_misspec_repair",
    "our_diagnosis_invalid",
    "srs100_verifier_invalid",
    "curated_accepted",
)

FORBIDDEN_FEATURE_SUBSTR = (
    "underspecified",
    "false_negative",
    "other_major",
    "filter_out",
    "p_invalid",
    "p_logistic",
    "human_severity",
    "human_validity",
    "judge",
)

EVAL_TASK_IDS = (
    "experimental/bootstrap-merge-resume",
    "experimental/catalog-contention-recovery",
    "experimental/catalog-shift-closure",
    "experimental/catalog-shift-replay",
    "experimental/gold-retry-publisher",
    "experimental/logged-bandit-ope",
    "experimental/payments-ledger-reconciliation",
    "experimental/schema-evolution-cdc",
    "experimental/warehouse-drift-closure",
    "tasks/durable-prefix-ack",
    "tasks/hello-world",
    "tasks/keydir-merge",
    "tasks/lakehouse-publish-recovery",
    "tasks/late-session-gc",
    "tasks/shared-limit-si",
    "tasks/week-hours",
)

DIAGNOSIS_INVALID = frozenset(
    {
        "experimental/bootstrap-merge-resume",
        "experimental/logged-bandit-ope",
    }
)


def empty_features() -> dict:
    return {name: None for name in FEATURE_NAMES}


def empty_labels() -> dict:
    return {
        key: {"value": None, "provenance": None, "construct": None} for key in LABEL_KEYS
    }


def _clip01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _bool01(value) -> float | None:
    if value is None:
        return None
    return 1.0 if value else 0.0


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in rows:
            fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _seed_int(*parts: object) -> int:
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:4], "big")


def solve_rate_band(p_i: float | None, near_constant: bool | None = None) -> str | None:
    if p_i is None:
        return None
    if near_constant and p_i <= 0.02:
        return "never"
    if p_i <= 0.0:
        return "never"
    if p_i <= 0.20:
        return "low"
    if p_i < 0.80:
        return "mid"
    return "high"


def _set_label(labels: dict, key: str, value, provenance: str, construct: str) -> None:
    labels[key] = {"value": value, "provenance": provenance, "construct": construct}


def merge_features(base: dict, extra: dict) -> dict:
    out = empty_features()
    out.update({k: extra.get(k, base.get(k)) for k in FEATURE_NAMES})
    for key in FEATURE_NAMES:
        if key == "solve_rate_band":
            continue
        if out[key] is not None and key not in {"solve_rate_band"}:
            if isinstance(out[key], bool):
                out[key] = 1.0 if out[key] else 0.0
    return out


def _count_assertions(text: str) -> float:
    n = 0
    for line in (text or "").splitlines():
        if ASSERT_LINE_RE.search(line):
            n += 1
    return float(n)


def _literal_pins_absent(instruction: str, tests: str) -> float:
    inst = extract_atoms(instruction or "")
    tes = extract_atoms(tests or "")
    inst_lits = {x.lower() for x in inst.literals}
    tes_lits = {x.lower() for x in tes.literals}
    if not tes_lits:
        # fall back to raw string literals in tests
        raw = []
        for _, body in STRING_RE.findall(tests or ""):
            if any(ch.isalpha() for ch in body):
                raw.append(body.strip()[:80].lower())
        tes_lits = set(raw)
    return float(len(tes_lits - inst_lits))


def _id_alignment(instruction: str, tests: str) -> tuple[float, float]:
    stmt_ids = identifiers(instruction or "")
    test_ids = identifiers(tests or "")
    if not test_ids:
        return 0.0, 0.0
    overlap = len(stmt_ids & test_ids) / len(test_ids)
    only = len(test_ids - stmt_ids) / len(test_ids)
    return float(overlap), float(only)


def _dir_blob(root: Path, pattern: str) -> tuple[int, str, int]:
    if not root.is_dir():
        return 0, "", 0
    blobs = []
    n_files = 0
    n_bytes = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in {".git", "__pycache__"} for part in p.parts):
            continue
        name = p.name.lower()
        rel = p.relative_to(root).as_posix().lower()
        if pattern == "tests":
            if not (
                name.startswith("test")
                or name.endswith("_test.py")
                or name in {"test.sh", "verify.sh"}
                or "/tests/" in "/" + rel
            ):
                continue
        n_files += 1
        try:
            data = p.read_bytes()
        except OSError:
            data = b""
        n_bytes += len(data)
        if len(data) > 2_000_000:
            data = data[:2_000_000]
        try:
            blobs.append(data.decode("utf-8", errors="replace"))
        except Exception:
            blobs.append("")
    return n_files, "\n".join(blobs), n_bytes


def is_judge_verifier(task_dir: Path) -> bool:
    tests = task_dir / "tests"
    if not tests.is_dir():
        return False
    for p in tests.rglob("*"):
        if not p.is_file():
            continue
        if p.name in JUDGE_FILE_NAMES:
            return True
        if p.suffix.lower() not in {".py", ".sh", ".txt", ".toml", ".md", ".json"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(m in text for m in JUDGE_MARKERS):
            return True
    return False


def layout_static_features(task_dir: Path) -> dict:
    """TB / Harbor / eval_tasks directory layout. Explicit nulls."""

    feats = empty_features()
    if not task_dir.is_dir():
        return feats
    instruction = _read(task_dir / "instruction.md") or ""
    toml_text = _read(task_dir / "task.toml") or ""
    fields = _parse_toml_lite(toml_text)
    n_test, tests_blob, _ = _dir_blob(task_dir / "tests", "tests")
    n_sol, sol_blob, sol_bytes = _dir_blob(task_dir / "solution", "solution")
    overlap, only = _id_alignment(instruction, tests_blob)
    mem = parse_memory_mb(fields)
    if mem is None:
        mem = parse_memory_mb(
            {k.replace("verifier.environment.", "environment."): v for k, v in fields.items()}
        )
    cpus = parse_cpus(fields)
    if cpus is None:
        cpus = _as_float(fields.get("verifier.environment.cpus"))
    timeout = _as_float(fields.get("verifier.timeout_sec")) or _as_float(
        fields.get("agent.timeout_sec")
    )
    net = (
        fields.get("environment.network_mode")
        or fields.get("verifier.environment.network_mode")
        or fields.get("environment.network")
        or ""
    ).lower()
    isolated = 0.0
    if net:
        isolated = 1.0 if ("no-network" in net or "isolated" in net or net == "none") else 0.0
    elif "isolated" in toml_text.lower() or "no-network" in toml_text.lower():
        isolated = 1.0
    else:
        isolated = None if not toml_text else 0.0
    feats.update(
        {
            "instruction_chars": float(len(instruction)),
            "instruction_lines": float(instruction.count("\n") + 1) if instruction else 0.0,
            "stmt_n_identifiers": float(len(identifiers(instruction))),
            "test_file_count": float(n_test),
            "assertion_count": _count_assertions(tests_blob),
            "literal_pins_absent": _literal_pins_absent(instruction, tests_blob),
            "solution_size": float(sol_bytes if sol_bytes else len(sol_blob)),
            "resource_memory_mb": float(mem) if mem is not None else None,
            "resource_cpus": float(cpus) if cpus is not None else None,
            "timeout_sec": timeout,
            "network_isolated": isolated,
            "judge_verifier": 1.0 if is_judge_verifier(task_dir) else 0.0,
            "test_stmt_id_overlap": overlap,
            "test_only_id_frac": only,
            "has_code_fence": 1.0 if ("```" in instruction or "~~~" in instruction) else 0.0,
            "has_traceback": 1.0
            if ("Traceback" in instruction or "Error:" in instruction)
            else 0.0,
            "has_http_url": 1.0
            if ("http://" in instruction or "https://" in instruction)
            else 0.0,
            "has_reproduction_hint": 1.0
            if any(
                w in instruction.lower()
                for w in ("reproduce", "to reproduce", "minimal example")
            )
            else 0.0,
            "hints_chars": 0.0,
            "n_fail_to_pass": None,
            "n_pass_to_pass": None,
        }
    )
    _ = n_sol
    return feats


def _test_blob_from_swe(rec: dict) -> str:
    tpatch = rec.get("test_patch") or ""
    if tpatch:
        return tpatch
    patch = rec.get("patch") or ""
    if not patch:
        return ""
    keep = []
    take = False
    for line in patch.splitlines():
        if line.startswith("diff --git"):
            parts = line.split()
            name = parts[-1] if parts else ""
            take = bool(TEST_NAME_RE.search(name))
        if take:
            keep.append(line)
    return "\n".join(keep)


_CHEAP_TO_FOOTPRINT = (
    ("stmt_chars", "instruction_chars"),
    ("stmt_lines", "instruction_lines"),
    ("stmt_n_identifiers", "stmt_n_identifiers"),
    ("test_n_files", "test_file_count"),
    ("patch_n_changed_lines", "solution_size"),
    ("test_stmt_id_overlap", "test_stmt_id_overlap"),
    ("test_only_id_frac", "test_only_id_frac"),
    ("n_fail_to_pass", "n_fail_to_pass"),
    ("n_pass_to_pass", "n_pass_to_pass"),
    ("patch_n_files", "patch_n_files"),
    ("patch_n_hunks", "patch_n_hunks"),
    ("patch_n_changed_lines", "patch_n_changed_lines"),
    ("test_n_files", "test_n_files"),
    ("test_n_hunks", "test_n_hunks"),
    ("test_n_changed_lines", "test_n_changed_lines"),
    ("has_code_fence", "has_code_fence"),
    ("has_traceback", "has_traceback"),
    ("has_http_url", "has_http_url"),
    ("has_reproduction_hint", "has_reproduction_hint"),
    ("hints_chars", "hints_chars"),
    ("gold_to_test_line_ratio", "gold_to_test_line_ratio"),
    ("f2p_in_statement_frac", "f2p_in_statement_frac"),
    ("test_has_exact_string_literal", "test_has_exact_string_literal"),
    ("strict_exact_lits_not_in_spec", "literal_pins_absent"),
)


def swe_static_features(rec: dict) -> dict:
    """Map SWE/Pro cheap features onto the shared footprint keys.

    Stored cheap tables have no patches. New keys stay null unless the
    record carries problem_statement / patch / test_patch (generated samples).
    """

    feats = empty_features()
    existing = rec.get("features") or {}
    for src, dst in _CHEAP_TO_FOOTPRINT:
        if existing.get(src) is not None and feats.get(dst) is None:
            feats[dst] = existing[src]
    for key in FEATURE_NAMES:
        if feats.get(key) is None and existing.get(key) is not None:
            feats[key] = existing[key]
    stmt = rec.get("problem_statement") or rec.get("instruction") or ""
    patch = rec.get("patch") or ""
    tpatch = rec.get("test_patch") or _test_blob_from_swe(rec)
    if not (stmt or patch or tpatch):
        if feats.get("judge_verifier") is None:
            feats["judge_verifier"] = 0.0
        return feats
    cheap = swe_cheap_features(
        {
            "problem_statement": stmt,
            "patch": patch,
            "test_patch": tpatch,
            "hints_text": rec.get("hints_text") or rec.get("requirements") or "",
            "FAIL_TO_PASS": rec.get("FAIL_TO_PASS") or rec.get("fail_to_pass") or "[]",
            "PASS_TO_PASS": rec.get("PASS_TO_PASS") or rec.get("pass_to_pass") or "[]",
        }
    )
    pstats = diff_stats(patch)
    feats.update(
        {
            "instruction_chars": cheap["stmt_chars"],
            "instruction_lines": cheap["stmt_lines"],
            "stmt_n_identifiers": cheap["stmt_n_identifiers"],
            "test_file_count": cheap["test_n_files"],
            "assertion_count": _count_assertions(tpatch),
            "literal_pins_absent": _literal_pins_absent(stmt, tpatch),
            "solution_size": float(pstats["n_changed_lines"]),
            "judge_verifier": 0.0,
            "test_stmt_id_overlap": cheap["test_stmt_id_overlap"],
            "test_only_id_frac": cheap["test_only_id_frac"],
            "n_fail_to_pass": cheap["n_fail_to_pass"],
            "n_pass_to_pass": cheap["n_pass_to_pass"],
            "patch_n_files": cheap["patch_n_files"],
            "patch_n_hunks": cheap["patch_n_hunks"],
            "patch_n_changed_lines": cheap["patch_n_changed_lines"],
            "test_n_files": cheap["test_n_files"],
            "test_n_hunks": cheap["test_n_hunks"],
            "test_n_changed_lines": cheap["test_n_changed_lines"],
            "has_code_fence": cheap["has_code_fence"],
            "has_traceback": cheap["has_traceback"],
            "has_http_url": cheap["has_http_url"],
            "has_reproduction_hint": cheap["has_reproduction_hint"],
            "hints_chars": cheap["hints_chars"],
            "gold_to_test_line_ratio": cheap["gold_to_test_line_ratio"],
            "f2p_in_statement_frac": cheap["f2p_in_statement_frac"],
            "test_has_exact_string_literal": cheap["test_has_exact_string_literal"],
        }
    )
    return feats


def execution_gate_flag(features: dict) -> float | None:
    """1 if the verifier gate fails, 0 if it passes, None if not run."""

    ref = features.get("reference_pass")
    nop = features.get("nop_reject")
    env = features.get("environment_failure")
    judge = features.get("judge_verifier")
    if judge == 1.0:
        return None
    observed = [v for v in (ref, nop, env) if v is not None]
    if not observed:
        return None
    if env == 1.0:
        return 1.0
    if ref == 0.0:
        return 1.0
    if nop == 0.0:
        return 1.0
    if ref is None and nop is None:
        return None
    return 0.0


def attach_execution_from_swe(exec_rows: list[dict]) -> dict[str, dict]:
    by: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for rec in exec_rows:
        tid = rec.get("instance_id") or rec.get("task_id")
        treat = rec.get("treatment") or rec.get("probe")
        by[tid][treat].append(rec)
    out: dict[str, dict] = {}
    for tid, treats in by.items():
        golds = treats.get("gold") or []
        empties = treats.get("empty") or []
        gold_ok = [r for r in golds if r.get("status") == "executed"]
        empty_ok = [r for r in empties if r.get("status") == "executed"]
        infra = any(r.get("infra_failure") or r.get("status") == "infra" for r in golds + empties)
        ref = None
        if gold_ok:
            ref = 1.0 if any(r.get("resolved") for r in gold_ok) else 0.0
            if gold_ok and all(r.get("resolved") is False for r in gold_ok):
                ref = 0.0
        nop = None
        if empty_ok:
            nop = 0.0 if any(r.get("resolved") for r in empty_ok) else 1.0
        det = None
        resolved = [bool(r.get("resolved")) for r in gold_ok]
        if len(resolved) >= 2:
            det = 1.0 if len(set(resolved)) == 1 else 0.0
        env = None
        if infra:
            env = 1.0
        elif ref == 0.0 and nop == 1.0:
            env = 1.0
        elif gold_ok or empty_ok:
            env = 0.0
        out[tid] = {
            "reference_pass": ref,
            "nop_reject": nop,
            "determinism": det,
            "environment_failure": env,
        }
    return out


def attach_execution_from_harbor_trials(rows: list[dict]) -> dict[str, dict]:
    by: dict[str, list[dict]] = defaultdict(list)
    for rec in rows:
        by[rec["task_id"]].append(rec)
    out: dict[str, dict] = {}
    for tid, trials in by.items():
        oracles = [t for t in trials if t.get("probe") == "oracle"]
        nops = [t for t in trials if str(t.get("probe", "")).startswith("nop")]
        exec_o = [t for t in oracles if t.get("status") == "executed"]
        exec_n = [t for t in nops if t.get("status") == "executed"]
        infra = any(t.get("status") == "infra" for t in trials)
        no_ref = any(t.get("status") == "no_reference" for t in oracles)
        ref = None
        if exec_o:
            acc = [t.get("accepted") for t in exec_o if t.get("accepted") is not None]
            if acc:
                ref = 1.0 if acc[0] else 0.0
                if len(acc) >= 2:
                    ref = 1.0 if any(acc) and all(acc) else (0.0 if not any(acc) else 0.0)
        nop = None
        if exec_n:
            accn = [t.get("accepted") for t in exec_n if t.get("accepted") is not None]
            if accn:
                nop = 0.0 if any(accn) else 1.0
        det = None
        rewards = []
        for t in exec_o:
            if t.get("reward") is not None:
                rewards.append(t["reward"])
        if len(rewards) >= 2:
            det = 1.0 if len(set(rewards)) == 1 else 0.0
        env = None
        if infra:
            env = 1.0
        elif no_ref:
            env = None
        elif exec_o or exec_n:
            env = 0.0
        out[tid] = {
            "reference_pass": ref,
            "nop_reject": nop,
            "determinism": det,
            "environment_failure": env,
            "no_reference": 1.0 if no_ref else 0.0,
        }
    return out


def attach_execution_from_pairs(summary: dict) -> dict[str, dict]:
    """POST (2.1) execution for the 28 maintained tasks; PRE used only as label context."""

    out: dict[str, dict] = {}
    for tid, rec in (summary.get("tasks") or {}).items():
        post = rec.get("post") or {}
        pre = rec.get("pre") or {}
        oracle_rewards = post.get("oracle_rewards") or []
        nop_rewards = post.get("nop_rewards") or []
        ref = None
        if post.get("oracle") is not None:
            ref = 1.0 if post.get("oracle") == 1.0 else 0.0
        nop = None
        if post.get("nop") is not None:
            nop = 1.0 if post.get("nop") == 0.0 else 0.0
        det = None
        if len(oracle_rewards) >= 2:
            det = 1.0 if len(set(oracle_rewards)) == 1 else 0.0
        env = 1.0 if rec.get("infra") else (0.0 if ref is not None or nop is not None else None)
        out[tid] = {
            "reference_pass": ref,
            "nop_reject": nop,
            "determinism": det,
            "environment_failure": env,
            "pre_reference_pass": 1.0
            if pre.get("oracle") == 1.0
            else (0.0 if pre.get("oracle") == 0.0 else None),
        }
        _ = nop_rewards
    return out


def attach_execution_from_interrogate(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for rec in rows:
        trials = rec.get("trials") or []
        ref_t = next((t for t in trials if t.get("probe_id") == "reference"), None)
        nop_t = next((t for t in trials if t.get("probe_id") == "nop"), None)
        ref = None
        if ref_t and ref_t.get("status") == "executed" and ref_t.get("accepted") is not None:
            ref = 1.0 if ref_t["accepted"] else 0.0
        nop = None
        if nop_t and nop_t.get("status") == "executed" and nop_t.get("accepted") is not None:
            nop = 0.0 if nop_t["accepted"] else 1.0
        det = rec.get("determinism")
        if isinstance(det, bool):
            det = 1.0 if det else 0.0
        env_status = rec.get("environment_execution_status")
        infra = bool(rec.get("infrastructure_failures"))
        env = None
        if infra or env_status not in (None, "ok"):
            env = 1.0
        elif ref is not None or nop is not None:
            env = 0.0
        out[rec["task_id"]] = {
            "reference_pass": ref,
            "nop_reject": nop,
            "determinism": det,
            "environment_failure": env,
        }
    return out


def _index_labels_2026(rows: list[dict]) -> dict[str, dict[str, list[dict]]]:
    by: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for rec in rows:
        by[rec["source"]][rec["task_id"]].append(rec)
        if rec.get("task_id_source") and rec["task_id_source"] != rec["task_id"]:
            by[rec["source"]][rec["task_id_source"]].append(rec)
    return by


def _aba_for(tid: str, aba_by_id: dict[str, list[dict]], *, benchmark: str | None = None):
    recs = aba_by_id.get(tid) or aba_by_id.get(tid.casefold()) or []
    if benchmark:
        recs = [r for r in recs if r.get("benchmark") == benchmark]
    return recs[0] if recs else None


def apply_labels_for_population(
    labels: dict,
    *,
    population: str,
    task_id: str,
    raters: dict | None,
    labels_2026_by: dict,
    pairs_classes: dict[str, list[str]],
    srs_verdicts: dict[str, dict],
) -> dict:
    if raters:
        _set_label(
            labels,
            "openai_2024_conservative",
            int(raters.get("openai_2024_conservative") or 0),
            "openai-swe-bench-verified-2024-conservative",
            "spec_invalid",
        )
        _set_label(
            labels,
            "openai_2024_majority",
            int(raters.get("majority_invalid") or 0),
            "openai-swe-bench-verified-2024-majority",
            "spec_invalid",
        )
        _set_label(
            labels,
            "openai_2024_unanimous",
            int(raters.get("unanimous_invalid") or 0),
            "openai-swe-bench-verified-2024-unanimous",
            "spec_invalid",
        )
    aba_bench = {
        "swe": "swe-bench-verified",
        "swe_verified": "swe-bench-verified",
        "swe_pro": "swe-bench-pro",
        "tb21": "terminal-bench-2",
    }.get(population)
    aba = _aba_for(task_id, labels_2026_by.get("aba") or {}, benchmark=aba_bench)
    if aba is None and population == "swe_pro":
        aba = _aba_for(task_id.casefold(), labels_2026_by.get("aba") or {}, benchmark="swe-bench-pro")
    if aba:
        _set_label(
            labels,
            "aba_major",
            1 if aba.get("label") == "major_issue" else 0,
            aba.get("provenance") or "aba",
            aba.get("construct") or "mixed",
        )
        _set_label(
            labels,
            "aba_minor",
            1 if aba.get("label") == "minor_issue" else 0,
            aba.get("provenance") or "aba",
            aba.get("construct") or "mixed",
        )
        _set_label(
            labels,
            "aba_construct",
            aba.get("construct"),
            aba.get("provenance") or "aba",
            aba.get("construct") or "mixed",
        )
        _set_label(
            labels,
            "aba_static_major",
            int(aba.get("static_major") or 0),
            aba.get("provenance") or "aba",
            aba.get("construct") or "mixed",
        )
        _set_label(
            labels,
            "aba_trajectory_major",
            int(aba.get("trajectory_major") or 0),
            aba.get("provenance") or "aba",
            aba.get("construct") or "mixed",
        )
    oc_rows = (labels_2026_by.get("opencompass_pro_verified") or {}).get(task_id) or []
    if oc_rows:
        rec = oc_rows[0]
        cat = rec.get("finding_class")
        _set_label(
            labels,
            "opencompass_repaired",
            1,
            rec.get("provenance") or "opencompass",
            "spec_invalid" if cat == "misleading_prompts" else "verifier_invalid",
        )
        _set_label(
            labels,
            "opencompass_category",
            cat,
            rec.get("provenance") or "opencompass",
            "spec_invalid" if cat == "misleading_prompts" else "verifier_invalid",
        )
    jk = (labels_2026_by.get("june_kim_pro") or {}).get(task_id) or []
    if jk:
        _set_label(
            labels,
            "june_kim_major",
            1,
            jk[0].get("provenance") or "june_kim_pro",
            "spec_invalid",
        )
    classes = pairs_classes.get(task_id) or []
    tb_rep = (labels_2026_by.get("tb21_maintenance") or {}).get(task_id) or []
    if tb_rep or classes:
        _set_label(
            labels,
            "tb21_repaired",
            1 if (tb_rep or classes) else 0,
            "tb21_maintenance + file-diff classes",
            "mixed",
        )
        _set_label(
            labels,
            "tb21_verifier_repair",
            1 if (set(classes) & VERIFIER_REPAIR_CLASSES) else 0,
            "tb21 file-diff: solution/test/env",
            "verifier_invalid",
        )
        _set_label(
            labels,
            "tb21_misspec_repair",
            1 if "misspec" in classes else 0,
            "tb21 file-diff: instruction.md",
            "spec_invalid",
        )
    if population == "eval_tasks":
        _set_label(
            labels,
            "our_diagnosis_invalid",
            1 if task_id in DIAGNOSIS_INVALID else 0,
            "data/gold/harbor_outlier_diagnosis.json",
            "verifier_invalid",
        )
    if task_id in srs_verdicts:
        v = srs_verdicts[task_id]
        _set_label(
            labels,
            "srs100_verifier_invalid",
            1 if v.get("invalid") else 0,
            v.get("label_protocol") or "swe_srs100_verdicts",
            "verifier_invalid",
        )
    if population in {"harbor_index", "tb21", "swe_verified"}:
        _set_label(
            labels,
            "curated_accepted",
            1,
            {
                "harbor_index": "Harbor-Index 1.0 accepted 82",
                "tb21": "Terminal-Bench 2.1 catalog 89",
                "swe_verified": "SWE-bench Verified 500",
            }[population],
            "mixed",
        )
    return labels


def spec_y(row: dict) -> int | None:
    pop = row["population"]
    lab = row["labels"]
    if pop == "swe":
        v = lab["openai_2024_conservative"]["value"]
        return int(v) if v is not None else None
    if pop in {"swe_verified", "swe_pro", "tb21"}:
        v = lab["aba_major"]["value"]
        return int(v) if v is not None else None
    if pop == "harbor_index":
        return 0
    return None


def verifier_y(row: dict) -> int | None:
    pop = row["population"]
    lab = row["labels"]
    if pop == "tb21":
        v = lab["tb21_verifier_repair"]["value"]
        return int(v) if v is not None else 0
    if pop == "swe_pro":
        cat = lab["opencompass_category"]["value"]
        if cat in OC_VERIFIER_CATS:
            return 1
        if lab["opencompass_repaired"]["value"] == 1:
            return 0
        v = lab["aba_major"]["value"]
        construct = lab["aba_construct"]["value"]
        if v == 1 and construct == "verifier_invalid":
            return 1
        if v is not None:
            return 0
        return None
    if pop == "swe_verified":
        v = lab["aba_major"]["value"]
        construct = lab["aba_construct"]["value"]
        if v is None:
            return None
        if v == 1 and construct in {"verifier_invalid", "mixed"}:
            return 1
        return 0
    if pop == "harbor_index":
        return 0
    if pop == "eval_tasks":
        v = lab["our_diagnosis_invalid"]["value"]
        return int(v) if v is not None else None
    if pop == "swe":
        # SRS-100 verdicts are the execution gate itself. Not independent gold.
        return None
    return None


def _solve_from_irt(items: list[dict]) -> dict[str, dict]:
    out = {}
    for rec in items:
        p = rec.get("p_i")
        out[rec["task_id"]] = {
            "solve_rate": float(p) if p is not None else None,
            "solve_rate_band": solve_rate_band(p, rec.get("near_constant")),
            "n_attempted": rec.get("n_attempted"),
        }
    return out


def build_footprint_rows(gold: Path = GOLD) -> list[dict]:
    labels_path = gold / "labels_2026.jsonl"
    if not labels_path.is_file():
        raise SystemExit("data/gold/labels_2026.jsonl is absent; stop")
    labels_2026 = load_jsonl(labels_path)
    labels_by = _index_labels_2026(labels_2026)
    swe_feats = load_jsonl(gold / "swe_verified_features.jsonl")
    pro_feats = load_jsonl(gold / "swe_pro_features.jsonl")
    raters = {r["task_id"]: r for r in load_jsonl(gold / "swe_rater_targets.jsonl")}
    irt_path = gold / "swe_irt.json"
    irt_items = json.loads(irt_path.read_text(encoding="utf-8"))["items"] if irt_path.is_file() else []
    solve = _solve_from_irt(irt_items)
    srs_exec = attach_execution_from_swe(load_jsonl(gold / "swe_srs100_exec.jsonl"))
    x2_exec = attach_execution_from_swe(load_jsonl(gold / "swe_2x2_exec.jsonl"))
    swe_exec = {**x2_exec, **srs_exec}
    srs_verdicts = {
        r["unit_id"]: r for r in load_jsonl(gold / "swe_srs100_verdicts.jsonl")
    }
    pairs_summary = {}
    pairs_path = gold / "tb21_pairs.summary.json"
    if pairs_path.is_file():
        pairs_summary = json.loads(pairs_path.read_text(encoding="utf-8"))
    pairs_exec = attach_execution_from_pairs(pairs_summary)
    pairs_classes = {
        tid: list((rec.get("change_classes") or []))
        for tid, rec in (pairs_summary.get("classifications") or pairs_summary.get("tasks") or {}).items()
    }
    census_exec = attach_execution_from_harbor_trials(load_jsonl(gold / "tb21_census.jsonl"))
    hindex_exec = attach_execution_from_harbor_trials(
        load_jsonl(gold / "harbor_index_control.jsonl")
    )
    eval_exec = attach_execution_from_interrogate(load_jsonl(gold / "harbor_interrogate.jsonl"))
    aba_verified_ids = sorted(
        {
            r["task_id"]
            for r in labels_2026
            if r["source"] == "aba" and r["benchmark"] == "swe-bench-verified"
        }
    )
    swe_by_id = {r["task_id"]: r for r in swe_feats}
    rows: list[dict] = []

    def _row(population: str, task_id: str, features: dict, repository=None) -> dict:
        labels = empty_labels()
        apply_labels_for_population(
            labels,
            population=population,
            task_id=task_id,
            raters=raters.get(task_id),
            labels_2026_by=labels_by,
            pairs_classes=pairs_classes,
            srs_verdicts=srs_verdicts,
        )
        for key in FEATURE_NAMES:
            if key not in features:
                features[key] = None
        gate = execution_gate_flag(features)
        return {
            "population": population,
            "task_id": task_id,
            "repository": repository,
            "features": {k: features.get(k) for k in FEATURE_NAMES},
            "labels": labels,
            "exec_gate_fail": gate,
        }

    for rec in swe_feats:
        tid = rec["task_id"]
        feats = swe_static_features({"features": rec.get("features"), **rec})
        feats.update(swe_exec.get(tid) or {})
        feats.update(solve.get(tid) or {})
        rows.append(_row("swe", tid, feats, rec.get("repository")))

    for tid in aba_verified_ids:
        rec = swe_by_id.get(tid) or {"task_id": tid, "features": {}}
        feats = swe_static_features({"features": rec.get("features"), **rec})
        feats.update(swe_exec.get(tid) or {})
        feats.update(solve.get(tid) or {})
        repo = rec.get("repository") or (tid.split("__")[0] if "__" in tid else None)
        rows.append(_row("swe_verified", tid, feats, repo))

    for rec in pro_feats:
        tid = rec["task_id"]
        feats = swe_static_features({"features": rec.get("features"), **rec})
        rows.append(_row("swe_pro", tid, feats, rec.get("repository")))

    tb_ids = []
    if TB21_ROOT.is_dir():
        tb_ids = sorted(p.parent.name for p in TB21_ROOT.glob("*/task.toml"))
    if not tb_ids:
        tb_ids = sorted(census_exec)
    for tid in tb_ids:
        feats = layout_static_features(TB21_ROOT / tid)
        execu = census_exec.get(tid) or pairs_exec.get(tid) or {}
        for k in ("reference_pass", "nop_reject", "determinism", "environment_failure"):
            if execu.get(k) is not None:
                feats[k] = execu[k]
        if feats.get("judge_verifier") == 1.0:
            feats["reference_pass"] = None
        rows.append(_row("tb21", tid, feats, None))

    hi_ids = []
    if HARBOR_INDEX_ROOT.is_dir():
        hi_ids = sorted(p.parent.name for p in HARBOR_INDEX_ROOT.glob("*/task.toml"))
    if not hi_ids:
        hi_ids = sorted(hindex_exec)
    for tid in hi_ids:
        feats = layout_static_features(HARBOR_INDEX_ROOT / tid)
        execu = hindex_exec.get(tid) or {}
        for k in ("reference_pass", "nop_reject", "determinism", "environment_failure"):
            if execu.get(k) is not None:
                feats[k] = execu[k]
        if feats.get("judge_verifier") == 1.0:
            feats["reference_pass"] = None
            feats["environment_failure"] = None
        rows.append(_row("harbor_index", tid, feats, None))

    for tid in EVAL_TASK_IDS:
        feats = layout_static_features(EVAL_TASKS_ROOT / tid)
        execu = eval_exec.get(tid) or {}
        for k in ("reference_pass", "nop_reject", "determinism", "environment_failure"):
            if execu.get(k) is not None:
                feats[k] = execu[k]
        rows.append(_row("eval_tasks", tid, feats, None))

    for rec in rows:
        for name in FORBIDDEN_FEATURE_SUBSTR:
            if name == "judge":
                continue
            if name in rec["features"]:
                raise ValueError(f"forbidden feature {name} on {rec['task_id']}")
    return rows


# --- stdlib logistic -------------------------------------------------------


def _log1p_val(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if name in LOG1P_FEATURES:
        return math.log1p(max(0.0, float(value)))
    return float(value)


def design_matrix(
    rows: list[dict],
    names: tuple[str, ...] = RANK_FEATURES,
    *,
    stats: dict | None = None,
    missing_indicators: bool = True,
) -> tuple[list[list[float]], dict]:
    """Impute train medians; optional missingness indicators for sparse columns."""

    raw: list[list[float | None]] = []
    for rec in rows:
        feats = rec["features"]
        raw.append([_log1p_val(n, _as_float(feats.get(n))) for n in names])
    n = len(raw)
    p = len(names)
    if stats is None:
        med = []
        miss_rate = []
        for j in range(p):
            vals = [row[j] for row in raw if row[j] is not None]
            miss_rate.append(1.0 - (len(vals) / n if n else 0.0))
            med.append(_mean(vals) if vals else 0.0)
        use_miss = [
            bool(missing_indicators) and miss_rate[j] >= 0.05 and miss_rate[j] < 1.0
            for j in range(p)
        ]
        filled = []
        for row in raw:
            cur = []
            for j in range(p):
                v = med[j] if row[j] is None else row[j]
                cur.append(v)
            for j in range(p):
                if use_miss[j]:
                    cur.append(1.0 if row[j] is None else 0.0)
            filled.append(cur)
        cols = list(range(len(filled[0]))) if filled else []
        mu = [_mean([r[j] for r in filled]) for j in cols]
        sd = []
        for j in cols:
            var = _mean([(r[j] - mu[j]) ** 2 for r in filled]) if filled else 0.0
            sd.append(math.sqrt(var) if var > 1e-12 else 1.0)
        stats = {
            "names": list(names),
            "median": med,
            "use_miss": use_miss,
            "mu": mu,
            "sd": sd,
            "missing_indicators": bool(missing_indicators),
        }
    else:
        med = stats["median"]
        use_miss = stats["use_miss"]
        filled = []
        for row in raw:
            cur = []
            for j in range(p):
                v = med[j] if row[j] is None else row[j]
                cur.append(v)
            for j in range(p):
                if use_miss[j]:
                    cur.append(1.0 if row[j] is None else 0.0)
            filled.append(cur)
        mu = stats["mu"]
        sd = stats["sd"]
    X = []
    for row in filled:
        X.append([(row[j] - mu[j]) / sd[j] for j in range(len(mu))])
    return X, stats


def _solve_sym(A: list[list[float]], b: list[float]) -> list[float] | None:
    n = len(b)
    M = [A[i][:] + [b[i]] for i in range(n)]
    for k in range(n):
        piv = max(range(k, n), key=lambda i: abs(M[i][k]))
        if abs(M[piv][k]) < 1e-14:
            return None
        M[k], M[piv] = M[piv], M[k]
        diag = M[k][k]
        for j in range(k, n + 1):
            M[k][j] /= diag
        for i in range(n):
            if i == k:
                continue
            f = M[i][k]
            if f == 0.0:
                continue
            for j in range(k, n + 1):
                M[i][j] -= f * M[k][j]
    return [M[i][n] for i in range(n)]


def fit_logit(
    X: list[list[float]],
    y: list[int],
    *,
    l2: float = LOGIT_L2,
    max_iter: int = LOGIT_MAX_ITER,
) -> dict:
    n = len(y)
    if not n:
        return {"coef": [], "intercept": 0.0, "ok": False, "reason": "empty"}
    n_pos = sum(y)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        p = n_pos / n
        intercept = math.log(p / (1.0 - p)) if 0.0 < p < 1.0 else (10.0 if p >= 1 else -10.0)
        pdim = len(X[0]) if X else 0
        return {
            "coef": [0.0] * pdim,
            "intercept": intercept,
            "ok": False,
            "reason": "constant_y",
        }
    p = len(X[0])
    beta = [0.0] * (p + 1)
    wp = n / (2.0 * n_pos)
    wn = n / (2.0 * n_neg)
    w_obs = [wp if yi == 1 else wn for yi in y]
    for _ in range(max_iter):
        p_hat = []
        for i in range(n):
            eta = beta[0] + sum(beta[j + 1] * X[i][j] for j in range(p))
            p_hat.append(sigmoid(eta))
        Wz = []
        z = []
        for i in range(n):
            pi = min(1.0 - 1e-6, max(1e-6, p_hat[i]))
            wi = w_obs[i] * pi * (1.0 - pi)
            eta = beta[0] + sum(beta[j + 1] * X[i][j] for j in range(p))
            Wz.append(wi)
            z.append(eta + (y[i] - pi) / (pi * (1.0 - pi)))
        dim = p + 1
        A = [[0.0] * dim for _ in range(dim)]
        bvec = [0.0] * dim
        for i in range(n):
            xi = [1.0] + X[i]
            wi = Wz[i]
            for a in range(dim):
                bvec[a] += wi * xi[a] * z[i]
                for c in range(dim):
                    A[a][c] += wi * xi[a] * xi[c]
        for j in range(1, dim):
            A[j][j] += l2
        sol = _solve_sym(A, bvec)
        if sol is None:
            break
        delta = sum((sol[j] - beta[j]) ** 2 for j in range(dim))
        beta = sol
        if delta < 1e-10:
            break
    return {"coef": beta[1:], "intercept": beta[0], "ok": True, "reason": None}


def predict_logit(model: dict, X: list[list[float]]) -> list[float]:
    b0 = model["intercept"]
    coef = model["coef"]
    out = []
    for row in X:
        eta = b0 + sum(c * x for c, x in zip(coef, row))
        out.append(sigmoid(eta))
    return out


def fit_ranker(
    train_rows: list[dict],
    y: list[int],
    names: tuple[str, ...] = RANK_FEATURES,
    *,
    missing_indicators: bool = True,
) -> dict:
    X, stats = design_matrix(
        train_rows, names, missing_indicators=missing_indicators
    )
    model = fit_logit(X, y)
    model["stats"] = stats
    feat_names = list(stats["names"])
    extra = []
    for j, flag in enumerate(stats["use_miss"]):
        if flag:
            extra.append(f"{feat_names[j]}_missing")
    model["feature_names"] = feat_names + extra
    coef_map = {}
    for name, c in zip(model["feature_names"], model["coef"]):
        coef_map[name] = float(c)
    model["coef_map"] = coef_map
    return model


def score_ranker(model: dict, rows: list[dict]) -> list[float]:
    names = tuple(model["stats"]["names"])
    X, _ = design_matrix(rows, names, stats=model["stats"])
    return predict_logit(model, X)


def split_by_repo(rows: list[dict], seed: str = SPLIT_SEED, test_frac: float = 0.3) -> tuple[list[int], list[int]]:
    repos = sorted({r.get("repository") or "unknown" for r in rows})
    test_repos = set()
    for repo in repos:
        digest = hashlib.sha256(f"{seed}:{repo}".encode()).digest()
        u = int.from_bytes(digest[:8], "big") / 2**64
        if u < test_frac:
            test_repos.add(repo)
    if not test_repos or len(test_repos) == len(repos):
        test_repos = {repos[0]} if repos else set()
    train = [i for i, r in enumerate(rows) if (r.get("repository") or "unknown") not in test_repos]
    test = [i for i, r in enumerate(rows) if (r.get("repository") or "unknown") in test_repos]
    return train, test


def binomial_ci(k: int, n: int, alpha: float = 0.05) -> dict:
    if n <= 0:
        return {"k": k, "n": n, "p": None, "lo": None, "hi": None}
    p = k / n
    lo = clopper_pearson_lower(k, n, alpha / 2.0)
    hi = clopper_pearson_upper(k, n, alpha / 2.0)
    return {"k": k, "n": n, "p": p, "lo": lo, "hi": hi}


def sens_spec(y: list[int], pred: list[int]) -> dict:
    tp = fn = tn = fp = 0
    for yi, pi in zip(y, pred):
        if yi == 1:
            if pi == 1:
                tp += 1
            else:
                fn += 1
        else:
            if pi == 1:
                fp += 1
            else:
                tn += 1
    n_pos = tp + fn
    n_neg = tn + fp
    se = (tp / n_pos) if n_pos else None
    sp = (tn / n_neg) if n_neg else None
    return {
        "tp": tp,
        "fn": fn,
        "tn": tn,
        "fp": fp,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "sens": se,
        "spec": sp,
        "sens_ci": binomial_ci(tp, n_pos) if n_pos else None,
        "spec_ci": binomial_ci(tn, n_neg) if n_neg else None,
    }


def youden_threshold(y: list[int], scores: list[float]) -> dict:
    pairs = sorted(set(scores))
    best = {"threshold": 0.5, "youden": -1.0, "sens": None, "spec": None}
    if not pairs or not y or min(y) == max(y):
        return best
    for i, t in enumerate(pairs):
        pred = [1 if s >= t else 0 for s in scores]
        ss = sens_spec(y, pred)
        if ss["sens"] is None or ss["spec"] is None:
            continue
        you = ss["sens"] + ss["spec"] - 1.0
        if you > best["youden"]:
            best = {
                "threshold": t,
                "youden": you,
                "sens": ss["sens"],
                "spec": ss["spec"],
            }
        _ = i
    return best


def auroc_ci(y: list[int], scores: list[float], seed: int = BOOT_SEED) -> dict:
    boot = bootstrap_auroc(y, scores, n_reps=N_BOOT_AUROC, seed=seed)
    return {
        "auroc": boot.get("value"),
        "ci95": boot.get("ci95"),
        "n": len(y),
        "n_pos": sum(y),
        "n_neg": len(y) - sum(y),
        "n_boot": N_BOOT_AUROC,
    }


def _rows_by_pop(rows: list[dict]) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = defaultdict(list)
    for rec in rows:
        by[rec["population"]].append(rec)
    return by


def execution_gate_table(rows: list[dict]) -> list[dict]:
    by = _rows_by_pop(rows)
    out = []
    pops = list(ALL_POPS)
    for pop in pops:
        block = by.get(pop) or []
        y = []
        pred = []
        for rec in block:
            yi = verifier_y(rec)
            gi = execution_gate_flag(rec["features"])
            if yi is None or gi is None:
                continue
            y.append(int(yi))
            pred.append(int(gi))
        ss = sens_spec(y, pred) if y else {
            "tp": 0, "fn": 0, "tn": 0, "fp": 0, "n_pos": 0, "n_neg": 0,
            "sens": None, "spec": None, "sens_ci": None, "spec_ci": None,
        }
        gold_name = {
            "tb21": "tb21_verifier_repair (solution/test/env class)",
            "swe_pro": "opencompass narrow/broad tests; else ABA verifier-major",
            "swe_verified": "ABA major with verifier or mixed construct",
            "harbor_index": "accepted set (rate 0)",
            "eval_tasks": "our diagnosis INVALID",
            "swe": "no independent verifier gold (SRS verdicts are the gate)",
        }[pop]
        out.append(
            {
                "population": pop,
                "n_scored": len(y),
                "n_pop": len(block),
                "gold": gold_name,
                **ss,
            }
        )
    return out


def _labeled(rows: list[dict], construct: str) -> tuple[list[dict], list[int]]:
    fn = spec_y if construct == "spec" else verifier_y
    keep = []
    y = []
    for rec in rows:
        yi = fn(rec)
        if yi is None:
            continue
        keep.append(rec)
        y.append(int(yi))
    return keep, y


def _drop_ids(rows: list[dict], banned: set[str]) -> list[dict]:
    return [r for r in rows if r["task_id"] not in banned]


def _y_of(rows: list[dict], construct: str) -> list[int]:
    fn = spec_y if construct == "spec" else verifier_y
    out = []
    for rec in rows:
        yi = fn(rec)
        if yi is None:
            raise ValueError("unlabeled row after filter")
        out.append(int(yi))
    return out


def static_lopo_matrix(rows: list[dict], construct: str) -> dict:
    by = _rows_by_pop(rows)
    pops = list(TRANSFER_POPS)
    matrix = {}
    for train_pop in pops:
        tr_rows, ytr = _labeled(by.get(train_pop) or [], construct)
        matrix[train_pop] = {}
        if len(set(ytr)) < 2 or len(tr_rows) < 8:
            for test_pop in pops:
                matrix[train_pop][test_pop] = {
                    "auroc": None,
                    "reason": (
                        "train_population_excluded"
                        if test_pop == train_pop
                        else "train_unusable"
                    ),
                    "n_train": len(tr_rows),
                    "n_test": 0,
                }
            continue
        for test_pop in pops:
            if test_pop == train_pop:
                matrix[train_pop][test_pop] = {
                    "auroc": None,
                    "reason": "train_population_excluded",
                    "n_train": len(tr_rows),
                    "n_test": 0,
                }
                continue
            te_rows, yte = _labeled(by.get(test_pop) or [], construct)
            banned = {r["task_id"] for r in te_rows}
            tr_use = _drop_ids(tr_rows, banned)
            ytr_use = _y_of(tr_use, construct) if tr_use else []
            if len(set(ytr_use)) < 2 or len(tr_use) < 8:
                matrix[train_pop][test_pop] = {
                    "auroc": None,
                    "reason": "train_unusable_after_id_exclusion",
                    "n_train": len(tr_use),
                    "n_test": len(te_rows),
                    "n_overlap_dropped": len(tr_rows) - len(tr_use),
                }
                continue
            model = fit_ranker(tr_use, ytr_use)
            if len(set(yte)) < 2:
                matrix[train_pop][test_pop] = {
                    "auroc": None,
                    "reason": "test_single_class",
                    "n_train": len(tr_use),
                    "n_test": len(te_rows),
                    "n_pos": sum(yte) if yte else 0,
                }
                continue
            scores = score_ranker(model, te_rows)
            cell = auroc_ci(
                yte,
                scores,
                seed=_seed_int("static", construct, train_pop, test_pop),
            )
            cell.update(
                {
                    "n_train": len(tr_use),
                    "n_test": len(te_rows),
                    "n_overlap_dropped": len(tr_rows) - len(tr_use),
                    "reason": None,
                    "top_features": sorted(
                        model["coef_map"].items(), key=lambda kv: abs(kv[1]), reverse=True
                    )[:5],
                }
            )
            matrix[train_pop][test_pop] = cell
    return {"construct": construct, "rows_train_cols_test": matrix}


def within_swe_holdout(rows: list[dict]) -> dict:
    swe = [r for r in rows if r["population"] == "swe"]
    y = []
    keep = []
    for rec in swe:
        yi = spec_y(rec)
        if yi is None:
            continue
        keep.append(rec)
        y.append(int(yi))
    train_i, test_i = split_by_repo(keep)
    tr = [keep[i] for i in train_i]
    te = [keep[i] for i in test_i]
    ytr = [y[i] for i in train_i]
    yte = [y[i] for i in test_i]
    if len(set(ytr)) < 2 or len(set(yte)) < 2:
        return {"auroc": None, "reason": "single_class", "n_train": len(tr), "n_test": len(te)}
    model = fit_ranker(tr, ytr)
    scores = score_ranker(model, te)
    cell = auroc_ci(yte, scores, seed=BOOT_SEED + 17)
    cell.update(
        {
            "n_train": len(tr),
            "n_test": len(te),
            "split": "by_repository",
            "seed": SPLIT_SEED,
            "top_features": sorted(
                model["coef_map"].items(), key=lambda kv: abs(kv[1]), reverse=True
            )[:8],
        }
    )
    return cell


def _combined_rows(static_scores: list[float], rows: list[dict]) -> list[dict]:
    out = []
    for rec, p in zip(rows, static_scores):
        feats = rec["features"]
        gate = execution_gate_flag(feats)
        sr = _as_float(feats.get("solve_rate"))
        child = {
            "population": rec["population"],
            "task_id": rec["task_id"],
            "features": {
                "p_static": p,
                "exec_fail": 0.0 if gate is None else float(gate),
                "exec_observed": 0.0 if gate is None else 1.0,
                "solve_risk": (1.0 - sr) if sr is not None else 0.5,
                "solve_observed": 1.0 if sr is not None else 0.0,
            },
            "labels": rec["labels"],
            "repository": rec.get("repository"),
        }
        out.append(child)
    return out


COMBINED_FEATURES = (
    "p_static",
    "exec_fail",
    "exec_observed",
    "solve_risk",
    "solve_observed",
)

# Shared across Harbor/TB directories and SWE records. No missingness
# flags: those flags encode layout, which is source identity.
CURATED_FEATURES = (
    "instruction_chars",
    "instruction_lines",
    "stmt_n_identifiers",
    "test_file_count",
    "solution_size",
    "test_stmt_id_overlap",
    "test_only_id_frac",
    "has_code_fence",
    "has_traceback",
    "has_http_url",
    "has_reproduction_hint",
)


def fit_combined(train_rows: list[dict], y: list[int]) -> dict:
    X, stats = design_matrix(train_rows, COMBINED_FEATURES)
    model = fit_logit(X, y, l2=0.5)
    model["stats"] = stats
    model["feature_names"] = list(COMBINED_FEATURES)
    model["coef_map"] = {n: float(c) for n, c in zip(COMBINED_FEATURES, model["coef"])}
    return model


def score_combined(model: dict, rows: list[dict]) -> list[float]:
    X, _ = design_matrix(rows, COMBINED_FEATURES, stats=model["stats"])
    return predict_logit(model, X)


def combined_lopo_matrix(rows: list[dict], construct: str) -> dict:
    by = _rows_by_pop(rows)
    pops = list(TRANSFER_POPS)
    matrix = {}
    for train_pop in pops:
        tr_raw, ytr = _labeled(by.get(train_pop) or [], construct)
        matrix[train_pop] = {}
        if len(set(ytr)) < 2 or len(tr_raw) < 8:
            for test_pop in pops:
                matrix[train_pop][test_pop] = {
                    "auroc": None,
                    "reason": (
                        "train_population_excluded"
                        if test_pop == train_pop
                        else "train_unusable"
                    ),
                    "n_train": len(tr_raw),
                }
            continue
        for test_pop in pops:
            if test_pop == train_pop:
                matrix[train_pop][test_pop] = {
                    "auroc": None,
                    "reason": "train_population_excluded",
                    "n_train": len(tr_raw),
                }
                continue
            te_raw, yte = _labeled(by.get(test_pop) or [], construct)
            banned = {r["task_id"] for r in te_raw}
            tr_use = _drop_ids(tr_raw, banned)
            ytr_use = _y_of(tr_use, construct) if tr_use else []
            if len(set(ytr_use)) < 2 or len(tr_use) < 8:
                matrix[train_pop][test_pop] = {
                    "auroc": None,
                    "reason": "train_unusable_after_id_exclusion",
                    "n_train": len(tr_use),
                    "n_test": len(te_raw),
                    "n_overlap_dropped": len(tr_raw) - len(tr_use),
                }
                continue
            static_model = fit_ranker(tr_use, ytr_use)
            tr_comb = _combined_rows(score_ranker(static_model, tr_use), tr_use)
            comb_model = fit_combined(tr_comb, ytr_use)
            if len(set(yte)) < 2:
                matrix[train_pop][test_pop] = {
                    "auroc": None,
                    "reason": "test_single_class",
                    "n_train": len(tr_use),
                    "n_test": len(te_raw),
                    "n_pos": sum(yte) if yte else 0,
                }
                continue
            te_comb = _combined_rows(score_ranker(static_model, te_raw), te_raw)
            scores = score_combined(comb_model, te_comb)
            cell = auroc_ci(
                yte, scores, seed=_seed_int("combined", construct, train_pop, test_pop)
            )
            cell.update({"n_train": len(tr_raw), "n_test": len(te_raw), "reason": None})
            matrix[train_pop][test_pop] = cell
    return {"construct": construct, "rows_train_cols_test": matrix}


def transfer_coverage(rows: list[dict], construct: str) -> list[dict]:
    """Calibrate Se/Sp on other pops, RG on held-out instrument outputs."""

    by = _rows_by_pop(rows)
    pops = list(TRANSFER_POPS)
    out = []
    for held in pops:
        cal_raw: list[dict] = []
        y_cal: list[int] = []
        for pop in pops:
            if pop == held:
                continue
            keep, y = _labeled(by.get(pop) or [], construct)
            cal_raw.extend(keep)
            y_cal.extend(y)
        held_raw, y_held = _labeled(by.get(held) or [], construct)
        banned = {r["task_id"] for r in held_raw}
        cal_raw = _drop_ids(cal_raw, banned)
        y_cal = _y_of(cal_raw, construct) if cal_raw else []
        true_p = (_mean([float(v) for v in y_held]) if y_held else None)
        n_held = len(y_held)
        if len(set(y_cal)) < 2 or len(cal_raw) < 8 or n_held == 0:
            out.append(
                {
                    "population": held,
                    "construct": construct,
                    "covers": False,
                    "reason": "calibration_or_holdout_unusable",
                    "true_p": true_p,
                    "n_held": n_held,
                    "n_cal": len(cal_raw),
                }
            )
            continue
        static_model = fit_ranker(cal_raw, y_cal)
        cal_comb = _combined_rows(score_ranker(static_model, cal_raw), cal_raw)
        comb_model = fit_combined(cal_comb, y_cal)
        cal_scores = score_combined(comb_model, cal_comb)
        thr = youden_threshold(y_cal, cal_scores)
        cal_pred = [1 if s >= thr["threshold"] else 0 for s in cal_scores]
        ss = sens_spec(y_cal, cal_pred)
        held_comb = _combined_rows(score_ranker(static_model, held_raw), held_raw)
        held_scores = score_combined(comb_model, held_comb)
        held_pred = [1 if s >= thr["threshold"] else 0 for s in held_scores]
        p_j = _mean([float(v) for v in held_pred])
        se, sp = ss["sens"], ss["spec"]
        if se is None or sp is None or ss["n_pos"] == 0 or ss["n_neg"] == 0:
            rg = None
            ucb = 1.0
            p_hat = 1.0
        else:
            rg = rogan_gladen(
                p_j,
                se,
                sp,
                n_sens=ss["n_pos"],
                n_spec=ss["n_neg"],
                n_boot=N_BOOT_RG,
                seed=f"footprint-rg:{construct}:{held}",
            )
            ucb = rg.ucb95
            p_hat = rg.p_hat
        covers = true_p is not None and true_p <= ucb + 1e-12
        n_srs = min(100, n_held)
        k_srs = int(round((true_p or 0.0) * n_srs))
        k_srs = min(n_srs, max(0, k_srs))
        srs = srs_estimate(k_srs, n_srs, n_held, 0.05)
        out.append(
            {
                "population": held,
                "construct": construct,
                "true_p": true_p,
                "n_held": n_held,
                "n_cal": len(cal_raw),
                "p_instrument": p_j,
                "threshold": thr["threshold"],
                "youden": thr["youden"],
                "sens": se,
                "spec": sp,
                "sens_ci": ss["sens_ci"],
                "spec_ci": ss["spec_ci"],
                "p_hat": p_hat,
                "ucb95": ucb,
                "width": (ucb - (true_p or 0.0)) if true_p is not None else None,
                "covers": covers,
                "rg_method": None if rg is None else rg.method,
                "srs_n100_p_hat": srs.p_hat,
                "srs_n100_ucb95": srs.ucb95,
                "srs_n100_width": srs.ucb95 - srs.p_hat,
                "srs_n": n_srs,
                "reason": None,
            }
        )
    return out


def evaluate_frozen_predicate(coverage: list[dict]) -> dict:
    ver = [c for c in coverage if c["construct"] == "verifier"]
    spec = [c for c in coverage if c["construct"] == "spec"]
    v_hits = sum(1 for c in ver if c.get("covers"))
    s_hits = sum(1 for c in spec if c.get("covers"))
    v_pass = v_hits >= 4
    s_pass = s_hits >= 3
    return {
        "text": FROZEN_PREDICATE,
        "written_before_computing": True,
        "verifier_hits": v_hits,
        "verifier_n": len(ver),
        "spec_hits": s_hits,
        "spec_n": len(spec),
        "verifier_pass": v_pass,
        "spec_pass": s_pass,
        "pass": bool(v_pass and s_pass),
        "populations": list(TRANSFER_POPS),
    }


# --- curated vs raw --------------------------------------------------------


def _hash_keep(seed: str, key: str) -> float:
    digest = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def reservoir_sample(records, n: int, seed: str, key_fn) -> list[dict]:
    rng = _rng(seed)
    sample: list[dict] = []
    seen = 0
    for rec in records:
        key = key_fn(rec)
        if not key:
            continue
        stmt = rec.get("problem_statement") or rec.get("instruction") or ""
        patch = rec.get("patch") or ""
        if not stmt or not patch:
            continue
        seen += 1
        if len(sample) < n:
            sample.append(rec)
            continue
        j = rng.randrange(seen)
        if j < n:
            sample[j] = rec
    return sample


def download_generated_sample(
    hf_id: str,
    split: str,
    n: int,
    seed: str,
    dest: Path,
) -> list[dict]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1000:
        return load_jsonl(dest)
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "datasets/huggingface_hub required only for generated-task download"
        ) from exc
    ds = load_dataset(hf_id, split=split, streaming=True)
    sample = reservoir_sample(
        ds, n, seed, key_fn=lambda r: r.get("instance_id") or r.get("id")
    )
    compact = []
    for rec in sample:
        compact.append(
            {
                "task_id": rec.get("instance_id") or rec.get("id"),
                "repo": rec.get("repo"),
                "problem_statement": rec.get("problem_statement") or "",
                "patch": rec.get("patch") or "",
                "test_patch": rec.get("test_patch") or "",
                "FAIL_TO_PASS": rec.get("FAIL_TO_PASS") or rec.get("fail_to_pass") or [],
                "PASS_TO_PASS": rec.get("PASS_TO_PASS") or rec.get("pass_to_pass") or [],
                "hints_text": rec.get("hints_text") or "",
                "source": hf_id,
            }
        )
    write_jsonl(dest, compact)
    return compact


def curated_vs_raw(
    footprint_rows: list[dict],
    *,
    gold: Path = GOLD,
    skip_download: bool = False,
) -> dict:
    by = _rows_by_pop(footprint_rows)
    positives = []
    for pop, source in (
        ("harbor_index", "harbor_index"),
        ("tb21", "tb21"),
        ("swe_verified", "swe_verified"),
    ):
        for rec in by.get(pop) or []:
            positives.append(
                {
                    "source": source,
                    "task_id": rec["task_id"],
                    "y": 1,
                    "features": rec["features"],
                    "population": pop,
                    "repository": rec.get("repository"),
                    "labels": rec["labels"],
                }
            )
    smith_path = RAW_GENERATED / "swe_smith_n200.jsonl"
    rebench_path = RAW_GENERATED / "swe_rebench_n200.jsonl"
    smith = load_jsonl(smith_path)
    rebench = load_jsonl(rebench_path)
    if not skip_download:
        if len(smith) < N_GENERATED:
            smith = download_generated_sample(
                SMITH_HF, "train", N_GENERATED, SAMPLE_SEED + ":smith", smith_path
            )
        if len(rebench) < N_GENERATED:
            rebench = download_generated_sample(
                REBENCH_HF, "test", N_GENERATED, SAMPLE_SEED + ":rebench", rebench_path
            )
    negatives = []
    for rec, source in [(r, "swe_smith") for r in smith] + [
        (r, "swe_rebench") for r in rebench
    ]:
        feats = swe_static_features(rec)
        negatives.append(
            {
                "source": source,
                "task_id": rec.get("task_id"),
                "y": 0,
                "features": feats,
                "population": source,
                "repository": rec.get("repo"),
                "labels": empty_labels(),
            }
        )
    all_rows = positives + negatives
    sources = ("harbor_index", "tb21", "swe_verified", "swe_smith", "swe_rebench")
    folds = []
    for held in sources:
        train = [r for r in all_rows if r["source"] != held]
        test_held = [r for r in all_rows if r["source"] == held]
        other_class = 0 if (test_held and test_held[0]["y"] == 1) else 1
        # Opposite class comes from train sources only (held-out source unseen).
        test_opp = [r for r in train if r["y"] == other_class]
        test = test_held + test_opp
        ytr = [r["y"] for r in train]
        yte = [r["y"] for r in test]
        if len(set(ytr)) < 2 or len(set(yte)) < 2:
            folds.append(
                {
                    "held_out": held,
                    "auroc": None,
                    "reason": "single_class",
                    "n_train": len(train),
                    "n_test": len(test),
                    "note": (
                        "AUROC uses the held-out source plus the opposite class "
                        "from other sources. Opposite-class rows were in training; "
                        "this is source transfer, not a fully unseen two-class draw."
                    ),
                }
            )
            continue
        model = fit_ranker(
            train, ytr, CURATED_FEATURES, missing_indicators=False
        )
        scores = score_ranker(model, test)
        cell = auroc_ci(yte, scores, seed=BOOT_SEED + 123)
        top = sorted(model["coef_map"].items(), key=lambda kv: abs(kv[1]), reverse=True)[:8]
        cell.update(
            {
                "held_out": held,
                "n_train": len(train),
                "n_test": len(test),
                "n_held_source": len(test_held),
                "top_features": top,
                "note": (
                    "Held-out source is unseen. Opposite class is from the "
                    "other sources (seen in training). Measures distribution "
                    "membership, not expert taste."
                ),
            }
        )
        folds.append(cell)
    # Mean |coef| across folds that fit
    acc: dict[str, list[float]] = defaultdict(list)
    for fold in folds:
        for name, val in fold.get("top_features") or []:
            acc[name].append(abs(float(val)))
    mean_abs = sorted(
        ((n, _mean(vs)) for n, vs in acc.items()), key=lambda kv: kv[1], reverse=True
    )
    return {
        "n_positives": len(positives),
        "n_negatives": len(negatives),
        "n_smith": len(smith),
        "n_rebench": len(rebench),
        "positive_sources": {"harbor_index": 82, "tb21": 89, "swe_verified": 500},
        "folds": folds,
        "top_features_mean_abs_coef": mean_abs[:10],
        "claim": (
            "This classifier measures membership in the curated-benchmark "
            "artifact distribution versus raw generated SWE tasks. It is not "
            "expert taste. Closing that gap without human ratings would need "
            "an independent taste instrument (frontier-agent discrimination, "
            "construction quotas) whose errors are themselves bounded on a "
            "fresh human sample."
        ),
    }


def _fmt_table(headers: list[str], rows: list[list[object]]) -> str:
    srows = [headers] + [
        [
            ""
            if x is None
            else f"{x:.3f}"
            if isinstance(x, float)
            else str(x)
            for x in r
        ]
        for r in rows
    ]
    widths = [max(len(srows[i][j]) for i in range(len(srows))) for j in range(len(headers))]
    lines = []
    for i, r in enumerate(srows):
        line = " | ".join(
            val.ljust(widths[j]) if j == 0 else val.rjust(widths[j])
            for j, val in enumerate(r)
        )
        lines.append(line)
        if i == 0:
            lines.append("-+-".join("-" * w for w in widths))
    return "\n".join(lines)


def format_key_tables(report: dict) -> str:
    chunks = []
    chunks.append("execution gate vs verifier gold (held-out labels, not features)")
    eg_rows = []
    for r in report["execution_gate"]:
        se = r.get("sens")
        sp = r.get("spec")
        eg_rows.append(
            [
                r["population"],
                r["n_scored"],
                r.get("n_pos"),
                se,
                (r.get("sens_ci") or {}).get("lo"),
                (r.get("sens_ci") or {}).get("hi"),
                sp,
                (r.get("spec_ci") or {}).get("lo"),
                (r.get("spec_ci") or {}).get("hi"),
            ]
        )
    chunks.append(
        _fmt_table(
            ["pop", "n", "n_pos", "sens", "se_lo", "se_hi", "spec", "sp_lo", "sp_hi"],
            eg_rows,
        )
    )
    for construct, key in (("spec", "static_lopo_spec"), ("verifier", "static_lopo_verifier")):
        chunks.append(f"static logistic AUROC train\\test ({construct})")
        mat = report[key]["rows_train_cols_test"]
        pops = list(TRANSFER_POPS)
        body = []
        for tr in pops:
            row = [tr]
            for te in pops:
                cell = (mat.get(tr) or {}).get(te) or {}
                row.append(cell.get("auroc"))
            body.append(row)
        chunks.append(_fmt_table(["train\\test", *pops], body))
    chunks.append("within-SWE repository holdout (spec, 2024 conservative)")
    ws = report["within_swe"]
    chunks.append(
        _fmt_table(
            ["n_train", "n_test", "auroc", "lo", "hi"],
            [[ws.get("n_train"), ws.get("n_test"), ws.get("auroc"),
              (ws.get("ci95") or [None, None])[0], (ws.get("ci95") or [None, None])[1]]],
        )
    )
    chunks.append("combined LOPO AUROC spec")
    mat = report["combined_lopo_spec"]["rows_train_cols_test"]
    pops = list(TRANSFER_POPS)
    body = []
    for tr in pops:
        row = [tr]
        for te in pops:
            cell = (mat.get(tr) or {}).get(te) or {}
            row.append(cell.get("auroc"))
        body.append(row)
    chunks.append(_fmt_table(["train\\test", *pops], body))
    chunks.append("transfer RG coverage (combined instrument)")
    cov_rows = []
    for r in report["transfer_coverage"]:
        cov_rows.append(
            [
                r["construct"],
                r["population"],
                r.get("true_p"),
                r.get("p_hat"),
                r.get("ucb95"),
                r.get("width"),
                r.get("srs_n100_ucb95"),
                r.get("srs_n100_width"),
                "yes" if r.get("covers") else "no",
            ]
        )
    chunks.append(
        _fmt_table(
            ["construct", "pop", "true_p", "rg_p", "rg_ucb", "rg_width", "srs100_ucb", "srs100_width", "covers"],
            cov_rows,
        )
    )
    pred = report["frozen_predicate"]
    chunks.append(
        f"F1 {pred['text']}: verifier {pred['verifier_hits']}/{pred['verifier_n']} "
        f"{'PASS' if pred['verifier_pass'] else 'FAIL'}; spec {pred['spec_hits']}/{pred['spec_n']} "
        f"{'PASS' if pred['spec_pass'] else 'FAIL'}; overall "
        f"{'PASS' if pred['pass'] else 'FAIL'}"
    )
    cv = report.get("curated_vs_raw") or {}
    chunks.append("curated vs raw LOSO AUROC (distribution membership, not taste)")
    cv_rows = []
    for fold in cv.get("folds") or []:
        ci = fold.get("ci95") or [None, None]
        cv_rows.append(
            [fold.get("held_out"), fold.get("n_train"), fold.get("n_test"), fold.get("auroc"), ci[0], ci[1]]
        )
    chunks.append(_fmt_table(["held_out", "n_train", "n_test", "auroc", "lo", "hi"], cv_rows))
    top = cv.get("top_features_mean_abs_coef") or []
    if top:
        chunks.append("top |coef| across LOSO folds: " + ", ".join(f"{n}={v:.3f}" for n, v in top[:6]))
    return "\n".join(chunks)


def run(
    *,
    gold: Path = GOLD,
    skip_generated: bool = False,
    write_rows: bool = True,
) -> dict:
    rows = build_footprint_rows(gold)
    if write_rows:
        write_jsonl(gold / "footprint.jsonl", rows)
    n_by = {pop: sum(1 for r in rows if r["population"] == pop) for pop in ALL_POPS}
    exec_tbl = execution_gate_table(rows)
    static_spec = static_lopo_matrix(rows, "spec")
    static_ver = static_lopo_matrix(rows, "verifier")
    combined_spec = combined_lopo_matrix(rows, "spec")
    combined_ver = combined_lopo_matrix(rows, "verifier")
    within = within_swe_holdout(rows)
    cov = transfer_coverage(rows, "verifier") + transfer_coverage(rows, "spec")
    pred = evaluate_frozen_predicate(cov)
    curated = curated_vs_raw(rows, gold=gold, skip_download=skip_generated)
    report = {
        "meta": {
            "n_rows": len(rows),
            "n_by_population": n_by,
            "frozen_predicate": FROZEN_PREDICATE,
            "transfer_pops": list(TRANSFER_POPS),
            "rank_features": list(RANK_FEATURES),
            "no_llm": True,
            "held_out_only": True,
            "judge_scores_used": False,
            "human_labels_as_features": False,
        },
        "execution_gate": exec_tbl,
        "static_lopo_spec": static_spec,
        "static_lopo_verifier": static_ver,
        "combined_lopo_spec": combined_spec,
        "combined_lopo_verifier": combined_ver,
        "within_swe": within,
        "transfer_coverage": cov,
        "frozen_predicate": pred,
        "curated_vs_raw": curated,
    }
    if write_rows:
        write_json(gold / "footprint.holdout.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validity footprint with held-out transfer")
    p.add_argument("--gold", type=Path, default=GOLD)
    p.add_argument("--skip-generated", action="store_true")
    p.add_argument("--no-write", action="store_true")
    args = p.parse_args(argv)
    report = run(
        gold=args.gold,
        skip_generated=args.skip_generated,
        write_rows=not args.no_write,
    )
    print(format_key_tables(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
