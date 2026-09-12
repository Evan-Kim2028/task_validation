"""2026 per-task labels as eval-only gold, plus frozen transfer tests T1-T5.

No model API calls. Downloads only. Labels are never predictors (ADR-0011).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

from task_validation.evidence.pro_verified import (
    N_BOOTSTRAP,
    bootstrap_auroc,
    enrichment,
    jaccard,
)
from task_validation.ingest.external_audits import match_prefixes, parse_june_kim_claims
from task_validation.ingest.tb_maintenance import TB21_CHANGED

REPO_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_SEED = 20260912
TOP_FRAC = 0.10
UA = "task-validation-research/0.1 (eval-only cache; sequential; retry-once)"
ABA_BASE = "https://data.autobenchaudit.com/benchmarks"
ABA_SLUGS = ("swe_bench_verified", "swe_bench_pro", "tb2")
ABA_KINDS = ("static_audits", "trajectory_audits")

# Written before any transfer count is computed.
PREDICATES = {
    "T1": (
        "Among the 27 maintained TB tasks with a pre-fix execution result, "
        "tasks whose pre-fix reference failed (9) have a higher rate of ABA "
        "major findings on tb2 than tasks that passed (18). Report the 2x2 "
        "and Fisher exact p (stdlib implementation)."
    ),
    "T2": (
        "Once the census has rows, the TB 2.1 tasks whose reference fails or "
        "whose nop passes are enriched in ABA tb2 major findings versus the "
        "rest. Report counts; if the census is incomplete, report on the rows "
        "available and say so."
    ),
    "T3": (
        "The ABA Verified major-finding set (39) versus our judge p_invalid "
        "and solve rate 1-p_i on the ~500 Verified items that are also in "
        "the 1,699: AUROC with 1,000-rep bootstrap CI for each, and versus "
        "the 2024 conservative label as the old baseline. Predicate: judge "
        "AUROC vs ABA-major >= 0.70."
    ),
    "T4": (
        "ABA Pro major findings (static 85, trajectory 220) versus "
        "openai_style_risk and cheap_risk: AUROC and top-decile enrichment, "
        "plus overlap with OpenCompass 102 and June Kim 109 (Jaccard). "
        "Predicate: none frozen beyond reporting; this is descriptive."
    ),
    "T5": (
        "Do our two execution flags (django-10097, django-12503) appear in "
        "ABA Verified/any findings? Report what ABA says about them."
    ),
}

JOIN_RULES = {
    "tb": {
        "join_key_kind": "tb_directory_name",
        "rule": (
            "Terminal-Bench task directory name (build-pmars). ABA tb2 "
            "task_id, TB 2.1 maintenance, and Z.ai named tasks use this "
            "string exactly."
        ),
    },
    "swe_verified": {
        "join_key_kind": "swe_instance_id",
        "rule": (
            "SWE-bench instance_id (astropy__astropy-12907). ABA "
            "swe_bench_verified task_id equals this. Join to the 1,699 "
            "test-split labels, judge rows, and IRT items by exact string."
        ),
    },
    "swe_pro": {
        "join_key_kind": "swe_pro_instance_id",
        "rule": (
            "Scale SWE-Bench Pro instance id "
            "(instance_{org}__{repo}-{sha}[-v{...}]). ABA swe_bench_pro "
            "task_id is that full string except org/repo folded to "
            "lowercase (NodeBB -> nodebb); join by casefold onto public "
            "Pro task_id. The ABA task_file suffix (__<8-10 hex>) is an "
            "audit-artifact hash, not a Scale hash; do not join on it. "
            "OpenCompass is exact instance_id. June Kim CLAIMS.md stores "
            "truncated instance_* prefixes matched with match_prefixes."
        ),
    },
    "tau2": {
        "join_key_kind": "tau2_domain_task_number",
        "rule": (
            "domain + task number: airline-2, retail-0, "
            "banking_knowledge-074. Parsed from CHANGELOG.md Fixed "
            "sections (v1.0.0 and v1.0.1). Banking ids keep the three-digit "
            "form when the source wrote it that way."
        ),
    },
    "sab": {
        "join_key_kind": "sab_task_key",
        "rule": "Integer task key as a string (e.g. '9') from sab_gold.json.",
    },
    "bix": {
        "join_key_kind": "bix_question_id",
        "rule": "bix-<n>-q<m> keys from bixbench_gold.json.",
    },
}

T5_FLAGS = ("django__django-10097", "django__django-12503")
T3_JUDGE_MIN = 0.70

BENCHMARK_FOR_SLUG = {
    "swe_bench_verified": "swe-bench-verified",
    "swe_bench_pro": "swe-bench-pro",
    "tb2": "terminal-bench-2",
}
JOIN_KIND_FOR_SLUG = {
    "swe_bench_verified": "swe_instance_id",
    "swe_bench_pro": "swe_pro_instance_id",
    "tb2": "tb_directory_name",
}
ABA_DATES = {
    "index": "2026-05-18",
    "paper": "2026-05-18",
}

JUNE_HEADING_RE = re.compile(r"^###\s+([a-z0-9][a-z0-9_-]*)", re.I)
INSTANCE_PREFIX_RE = re.compile(r"`(instance_[^`]+)`")
ZAI_NUMBERED_RE = re.compile(r"^#{2,3}\s+\d+\.\s+([a-z][a-z0-9.-]+)")
ZAI_TABLE_RE = re.compile(
    r"^\|\s*([a-z][a-z0-9-]*-[a-z0-9][a-z0-9.-]*)\s*\|"
)
ZAI_LIST_RE = re.compile(r"[a-z][a-z0-9-]*-[a-z0-9][a-z0-9.-]*")
TASK_SPAN_RE = re.compile(
    r"(?:tasks?_?\s*|task_)\s*((?:\d+\s*(?:[\u2013\-,]|and)\s*)*\d+)",
    re.I,
)
RANGE_RE = re.compile(r"(\d+)\s*[\u2013\-]\s*(\d+)")
INT_RE = re.compile(r"\d+")


def _fetch_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last: Exception | None = None
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt == 1:
                time.sleep(0.5)
    assert last is not None
    raise last


def download_url(url: str, dest: Path, *, timeout: int = 60) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 50:
        return {
            "url": url,
            "path": str(dest),
            "status": "skip",
            "bytes": dest.stat().st_size,
        }
    try:
        data = _fetch_bytes(url, timeout=timeout)
        dest.write_bytes(data)
        return {"url": url, "path": str(dest), "status": "ok", "bytes": len(data)}
    except Exception as exc:  # noqa: BLE001
        return {
            "url": url,
            "path": str(dest),
            "status": f"fail:{getattr(exc, 'code', type(exc).__name__)}",
            "bytes": 0,
        }


def download_aba_slice(cache_dir: Path) -> dict:
    """Sequential coding-slice download. Retry once. Skip existing files."""

    cache_dir.mkdir(parents=True, exist_ok=True)
    recs = []
    recs.append(
        download_url("https://data.autobenchaudit.com/index.json", cache_dir / "index.json")
    )
    n_ok = n_skip = n_fail = 0
    for slug in ABA_SLUGS:
        bench_path = cache_dir / slug / "benchmark.json"
        rec = download_url(f"{ABA_BASE}/{slug}/benchmark.json", bench_path)
        recs.append(rec)
        if rec["status"] not in {"ok", "skip"}:
            n_fail += 1
            continue
        tasks = json.loads(bench_path.read_text(encoding="utf-8"))["tasks"]
        for task in tasks:
            tf = task["task_file"]
            for kind in ABA_KINDS:
                dest = cache_dir / slug / kind / f"{tf}.json"
                url = f"{ABA_BASE}/{slug}/{kind}/{tf}.json"
                rec = download_url(url, dest)
                recs.append(rec)
                if rec["status"] == "ok":
                    n_ok += 1
                elif rec["status"] == "skip":
                    n_skip += 1
                else:
                    n_fail += 1
    return {"n_ok": n_ok, "n_skip": n_skip, "n_fail": n_fail, "n_logged": len(recs)}


def download_aux(raw_root: Path) -> list[dict]:
    jobs = [
        (
            "https://raw.githubusercontent.com/XinmingTu/BenchGuard/main/eval/data/gold/sab_gold.json",
            raw_root / "benchguard" / "sab_gold.json",
        ),
        (
            "https://raw.githubusercontent.com/XinmingTu/BenchGuard/main/eval/data/gold/bixbench_gold.json",
            raw_root / "benchguard" / "bixbench_gold.json",
        ),
        (
            "https://raw.githubusercontent.com/XinmingTu/BenchGuard/main/LICENSE",
            raw_root / "benchguard" / "LICENSE",
        ),
        (
            "https://raw.githubusercontent.com/sierra-research/tau2-bench/main/CHANGELOG.md",
            raw_root / "tau2-bench" / "CHANGELOG.md",
        ),
        (
            "https://raw.githubusercontent.com/sierra-research/tau2-bench/main/LICENSE",
            raw_root / "tau2-bench" / "LICENSE",
        ),
        (
            "https://huggingface.co/datasets/zai-org/terminal-bench-2-verified/resolve/main/changes_instructions.md",
            raw_root / "zai-tb2-verified" / "changes_instructions.md",
        ),
        (
            "https://huggingface.co/datasets/zai-org/terminal-bench-2-verified/raw/main/README.md",
            raw_root / "zai-tb2-verified" / "README.md",
        ),
    ]
    return [download_url(url, dest) for url, dest in jobs]


def _label_from_counts(n_major: int, n_minor: int) -> str:
    if n_major > 0:
        return "major_issue"
    if n_minor > 0:
        return "minor_issue"
    return "none"


def _construct_from_cats(cats: dict, n_major: int, n_minor: int) -> str:
    if n_major <= 0 and n_minor <= 0:
        return "unknown"
    hit = []
    for name in ("instruction", "evaluation", "env"):
        block = cats.get(name) or {}
        if int(block.get("major") or 0) or int(block.get("minor") or 0):
            hit.append(name)
    if hit == ["instruction"]:
        return "spec_invalid"
    if hit == ["evaluation"]:
        return "verifier_invalid"
    return "mixed"


def _finding_class_from_cats(cats: dict) -> str:
    parts = []
    for name, block in (cats or {}).items():
        maj = int((block or {}).get("major") or 0)
        minor = int((block or {}).get("minor") or 0)
        if maj or minor:
            parts.append(f"{name}:{maj}maj/{minor}min")
    return ";".join(parts) if parts else "none"


def _merge_cats(*dicts: dict) -> dict:
    out: dict[str, dict[str, int]] = {}
    for d in dicts:
        for name, block in (d or {}).items():
            slot = out.setdefault(name, {"major": 0, "minor": 0})
            slot["major"] += int((block or {}).get("major") or 0)
            slot["minor"] += int((block or {}).get("minor") or 0)
    return out


def _detail_finding_class(cache_dir: Path, slug: str, task_file: str) -> str | None:
    found: list[str] = []
    seen: set[str] = set()
    for kind in ABA_KINDS:
        path = cache_dir / slug / kind / f"{task_file}.json"
        if not path.is_file():
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for finding in obj.get("findings") or []:
            bits = [
                finding.get("category"),
                finding.get("subtype"),
                finding.get("severity"),
            ]
            text = "/".join(str(b) for b in bits if b)
            if text and text not in seen:
                seen.add(text)
                found.append(text)
    return ";".join(found) if found else None


def parse_aba_benchmark(
    bench: dict,
    *,
    source: str = "aba",
    provenance: str,
    date: str,
    cache_dir: Path | None = None,
    slug: str | None = None,
) -> list[dict]:
    slug = slug or bench.get("slug") or "unknown"
    benchmark = BENCHMARK_FOR_SLUG.get(slug, slug)
    join_kind = JOIN_KIND_FOR_SLUG.get(slug, "unknown")
    rows = []
    for task in bench.get("tasks") or []:
        sm = int(task.get("static_findings_major") or 0)
        tm = int(task.get("trajectory_findings_major") or 0)
        smin = int(task.get("static_findings_minor") or 0)
        tmin = int(task.get("trajectory_findings_minor") or 0)
        cats = _merge_cats(
            task.get("static_findings_by_category") or {},
            task.get("trajectory_findings_by_category") or {},
        )
        n_major = sm + tm
        n_minor = smin + tmin
        finding_class = _finding_class_from_cats(cats)
        if cache_dir is not None:
            detail = _detail_finding_class(cache_dir, slug, task["task_file"])
            if detail:
                finding_class = detail
        severity = "major" if n_major else ("minor" if n_minor else "none")
        rows.append(
            {
                "source": source,
                "benchmark": benchmark,
                "task_id": task["task_id"],
                "join_key_kind": join_kind,
                "label": _label_from_counts(n_major, n_minor),
                "construct": _construct_from_cats(cats, n_major, n_minor),
                "finding_class": finding_class,
                "severity": severity,
                "provenance": provenance,
                "date": date,
                "eval_only": True,
                "static_major": sm,
                "trajectory_major": tm,
                "static_minor": smin,
                "trajectory_minor": tmin,
                "task_file": task.get("task_file"),
            }
        )
    return rows


def parse_benchguard_gold(
    obj: dict,
    *,
    source: str,
    benchmark: str,
    join_key_kind: str,
    construct: str,
    provenance: str,
    date: str,
) -> list[dict]:
    rows = []
    tasks = obj.get("tasks") or {}
    if isinstance(tasks, list):
        iterable = []
        for rec in tasks:
            tid = str(rec.get("task_id") or rec.get("id") or rec.get("key") or "")
            iterable.append((tid, rec))
    else:
        iterable = list(tasks.items())
    for tid, rec in iterable:
        issues = rec.get("issues") or []
        classes = []
        for issue in issues:
            bit = issue.get("category") or issue.get("change_type") or issue.get("id")
            if bit:
                classes.append(str(bit))
        rows.append(
            {
                "source": source,
                "benchmark": benchmark,
                "task_id": str(tid),
                "join_key_kind": join_key_kind,
                "label": "repaired",
                "construct": construct,
                "finding_class": ";".join(classes) if classes else "author_confirmed",
                "severity": None,
                "provenance": provenance,
                "date": date,
                "eval_only": True,
                "n_issues": len(issues),
            }
        )
    return rows


def _ints_and_ranges(chunk: str) -> list[int]:
    out: list[int] = []
    covered: set[int] = set()
    for a, b in RANGE_RE.findall(chunk):
        lo, hi = int(a), int(b)
        if lo > hi:
            lo, hi = hi, lo
        for n in range(lo, hi + 1):
            if n not in covered:
                out.append(n)
                covered.add(n)
    for m in INT_RE.findall(chunk):
        n = int(m)
        if n not in covered:
            out.append(n)
            covered.add(n)
    return out


def task_numbers_from_line(line: str) -> list[int]:
    """Task ids after Task/Tasks/task_; drop issue refs and versions."""

    cleaned = re.sub(r"#\d+", " ", line)
    cleaned = re.sub(r"\bv?\d+\.\d+(?:\.\d+)?\b", " ", cleaned)
    nums: list[int] = []
    for m in TASK_SPAN_RE.finditer(cleaned):
        nums.extend(_ints_and_ranges(m.group(1)))
    return nums


def parse_tau2_changelog(text: str) -> list[dict]:
    """Named task fixes from v1.0.0 / v1.0.1 Fixed sections."""

    domain: str | None = None
    pad = False
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    finding = "errata"
    in_v1 = False
    for raw in text.splitlines():
        line = raw.strip()
        low = line.lower()
        if line.startswith("## [1.0"):
            in_v1 = True
        elif line.startswith("## [") and in_v1 and not line.startswith("## [1.0"):
            in_v1 = False
        if not in_v1:
            continue
        if "airline task" in low:
            domain = "airline"
            pad = False
            finding = "errata"
        elif "retail task" in low:
            domain = "retail"
            pad = False
            finding = "errata"
        elif "banking" in low and "knowledge" in low:
            domain = "banking_knowledge"
            pad = True
            finding = "errata"
        heading_map = (
            ("incorrect expected actions", "incorrect_expected_actions"),
            ("ambiguous user instructions", "ambiguous_user_instructions"),
            ("impossible or contradictory", "impossible_or_contradictory"),
            ("policy loophole", "policy_loophole"),
            ("missing fallback", "missing_fallback"),
            ("data fixes", "data_fix"),
            ("tool additions", "tool_addition"),
            ("grading", "grading"),
        )
        for needle, name in heading_map:
            if needle in low:
                finding = name
        if domain is None:
            continue
        nums = task_numbers_from_line(line)
        if not nums:
            continue
        for n in nums:
            if n > 200:
                continue
            tid = f"{domain}-{n:03d}" if pad else f"{domain}-{n}"
            key = (domain, tid)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "source": "tau2_changelog",
                    "benchmark": "tau2-bench",
                    "task_id": tid,
                    "join_key_kind": "tau2_domain_task_number",
                    "label": "errata",
                    "construct": "mixed",
                    "finding_class": finding,
                    "severity": None,
                    "provenance": (
                        "https://github.com/sierra-research/tau2-bench/blob/main/CHANGELOG.md"
                    ),
                    "date": "2026-07-15",
                    "eval_only": True,
                    "domain": domain,
                    "task_number": n,
                }
            )
    return rows


def parse_zai_changes(text: str) -> list[dict]:
    """Named instruction/test fixes. Drop the 89 Dockerfile-only env rows."""

    by_id: dict[str, dict] = {}
    finding = "named_fix"
    construct = "mixed"
    date = "2026-08-18"
    for raw in text.splitlines():
        line = raw.strip()
        low = line.lower()
        if "2026.08.18" in line or "2026-08-18" in line:
            date = "2026-08-18"
        if "synced" in low and "2.1" in low:
            finding = "synced_tb21"
            date = "2026-08-18"
        if "grading/test" in low:
            finding = "test_fix"
            construct = "verifier_invalid"
        if "instruction fix" in low:
            finding = "instruction_fix"
            construct = "spec_invalid"
        if "category a:" in low:
            finding = "test_hardcodes_path"
            construct = "mixed"
            date = "2026-05-08"
        if "category b:" in low:
            finding = "underspecified_api"
            construct = "spec_invalid"
            date = "2026-05-08"
        if "category c:" in low:
            finding = "uncommunicated_test_constraint"
            construct = "mixed"
            date = "2026-05-08"
        names: list[str] = []
        hm = ZAI_NUMBERED_RE.match(line)
        if hm:
            names.append(hm.group(1).rstrip(".,"))
        tm = ZAI_TABLE_RE.match(line)
        if tm:
            names.append(tm.group(1))
        if "category" in low and ("—" in line or " - " in line):
            after = line.split("—", 1)[-1] if "—" in line else line.split(" - ", 1)[-1]
            names.extend(ZAI_LIST_RE.findall(after))
        for name in names:
            if name in {"instruction", "test"}:
                continue
            if name not in by_id:
                by_id[name] = {
                    "source": "zai_tb2_verified",
                    "benchmark": "terminal-bench-2",
                    "task_id": name,
                    "join_key_kind": "tb_directory_name",
                    "label": "repaired",
                    "construct": construct,
                    "finding_class": finding,
                    "severity": None,
                    "provenance": (
                        "https://huggingface.co/datasets/zai-org/terminal-bench-2-verified"
                    ),
                    "date": date,
                    "eval_only": True,
                }
            else:
                # keep first finding_class; union construct toward mixed
                prev = by_id[name]
                if prev["construct"] != construct:
                    prev["construct"] = "mixed"
    return list(by_id.values())


def parse_tb21_maintenance_rows(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        for tid in TB21_CHANGED:
            rows.append(
                {
                    "source": "tb21_maintenance",
                    "benchmark": "terminal-bench-2",
                    "task_id": tid,
                    "join_key_kind": "tb_directory_name",
                    "label": "repaired",
                    "construct": "mixed",
                    "finding_class": "maintainer_repair",
                    "severity": None,
                    "provenance": "https://www.tbench.ai/news/terminal-bench-2-1",
                    "date": "2026-05-06",
                    "eval_only": True,
                }
            )
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            rows.append(
                {
                    "source": "tb21_maintenance",
                    "benchmark": "terminal-bench-2",
                    "task_id": rec["task_id"],
                    "join_key_kind": "tb_directory_name",
                    "label": "repaired",
                    "construct": "mixed",
                    "finding_class": rec.get("named_misspec") or "maintainer_repair",
                    "severity": None,
                    "provenance": rec.get("source")
                    or "https://www.tbench.ai/news/terminal-bench-2-1",
                    "date": "2026-05-06",
                    "eval_only": True,
                }
            )
    return rows


def parse_opencompass_labels(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            rows.append(
                {
                    "source": "opencompass_pro_verified",
                    "benchmark": "swe-bench-pro",
                    "task_id": rec.get("task_id") or rec.get("instance_id"),
                    "join_key_kind": "swe_pro_instance_id",
                    "label": "repaired",
                    "construct": "spec_invalid",
                    "finding_class": rec.get("category") or "repaired",
                    "severity": None,
                    "provenance": rec.get("source")
                    or "https://huggingface.co/datasets/opencompass/SWEBench-Pro-Verified",
                    "date": "2026-09-08",
                    "eval_only": True,
                }
            )
    return rows


def parse_june_kim_labels(claims_md: Path, pro_ids: list[str]) -> list[dict]:
    if not claims_md.is_file():
        return []
    text = claims_md.read_text(encoding="utf-8", errors="replace")
    current = "determinacy"
    tagged: list[tuple[str, str]] = []
    for line in text.splitlines():
        h = JUNE_HEADING_RE.match(line)
        if h:
            current = h.group(1).lower()
        for raw in INSTANCE_PREFIX_RE.findall(line):
            tagged.append((raw, current))
    prefixes = parse_june_kim_claims(claims_md)
    hits = match_prefixes(pro_ids, prefixes)
    prefix_class = {}
    for raw, cls in tagged:
        cleaned = raw.replace("…", "").replace("...", "").rstrip()
        prefix_class.setdefault(cleaned, cls)
    rows = []
    used = set()
    for tid, pref in hits.items():
        if tid in used:
            continue
        used.add(tid)
        rows.append(
            {
                "source": "june_kim_pro",
                "benchmark": "swe-bench-pro",
                "task_id": tid,
                "join_key_kind": "swe_pro_instance_id",
                "label": "major_issue",
                "construct": "spec_invalid",
                "finding_class": prefix_class.get(pref, "determinacy"),
                "severity": None,
                "provenance": str(claims_md),
                "date": "2026-06-21",
                "eval_only": True,
                "matched_prefix": pref,
            }
        )
    return rows


def map_pro_casefold(rows: list[dict], pro_ids: list[str]) -> list[dict]:
    """Align ABA Pro ids onto public Pro task_id by casefold. Not hashing."""

    by = {p.casefold(): p for p in pro_ids}
    out = []
    for rec in rows:
        if rec.get("join_key_kind") != "swe_pro_instance_id":
            out.append(rec)
            continue
        src = rec["task_id"]
        mapped = by.get(src.casefold())
        rec = dict(rec)
        rec["task_id_source"] = src
        if mapped:
            rec["task_id"] = mapped
            rec["join_note"] = "casefold" if mapped != src else "exact"
        else:
            rec["join_note"] = "unmapped"
        out.append(rec)
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in rows:
            fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")


def count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for rec in rows:
        out[str(rec.get(key))] = out.get(str(rec.get(key)), 0) + 1
    return dict(sorted(out.items()))


def positive_ids(rows: list[dict]) -> dict[str, set[str]]:
    """task_id sets per source, excluding label=none."""

    out: dict[str, set[str]] = defaultdict(set)
    for rec in rows:
        if rec.get("label") == "none":
            continue
        out[rec["source"]].add(rec["task_id"])
    return dict(out)


def overlap_matrix(rows: list[dict]) -> dict:
    by_source: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    kinds: dict[str, str] = {}
    for rec in rows:
        src = rec["source"]
        kind = rec["join_key_kind"]
        kinds.setdefault(src, kind)
        if rec.get("label") == "none":
            continue
        by_source[src][kind].add(rec["task_id"])
    sources = sorted(by_source)
    matrix = {}
    for a in sources:
        matrix[a] = {}
        for b in sources:
            if a == b:
                n = sum(len(s) for s in by_source[a].values())
                matrix[a][b] = {
                    "n_a": n,
                    "n_b": n,
                    "n_intersection": n,
                    "n_union": n,
                    "jaccard": 1.0 if n else None,
                    "shared_join_key_kind": kinds.get(a),
                }
                continue
            shared_kinds = set(by_source[a]) & set(by_source[b])
            inter = 0
            union = 0
            n_a = n_b = 0
            kind_used = None
            for kind in shared_kinds:
                sa = by_source[a][kind]
                sb = by_source[b][kind]
                inter += len(sa & sb)
                union += len(sa | sb)
                n_a += len(sa)
                n_b += len(sb)
                kind_used = kind
            if not shared_kinds:
                matrix[a][b] = {
                    "n_a": sum(len(s) for s in by_source[a].values()),
                    "n_b": sum(len(s) for s in by_source[b].values()),
                    "n_intersection": 0,
                    "n_union": None,
                    "jaccard": None,
                    "shared_join_key_kind": None,
                }
            else:
                matrix[a][b] = {
                    "n_a": n_a,
                    "n_b": n_b,
                    "n_intersection": inter,
                    "n_union": union,
                    "jaccard": (inter / union) if union else None,
                    "shared_join_key_kind": kind_used if len(shared_kinds) == 1 else sorted(shared_kinds),
                }
    return {"sources": sources, "pairs": matrix}


def fisher_exact_2x2(a: int, b: int, c: int, d: int) -> dict:
    """Hypergeometric Fisher exact test. Stdlib only (math.comb)."""

    n1 = a + b
    n2 = c + d
    k = a + c
    n = n1 + n2
    if n == 0 or n1 == 0 or n2 == 0:
        return {
            "table": [[a, b], [c, d]],
            "p_greater": None,
            "p_less": None,
            "p_two_sided": None,
        }

    def pmf(x: int) -> float:
        y = n1 - x
        z = k - x
        w = n2 - z
        if min(x, y, z, w) < 0:
            return 0.0
        return math.comb(n1, x) * math.comb(n2, z) / math.comb(n, k)

    lo = max(0, k - n2)
    hi = min(n1, k)
    p_obs = pmf(a)
    p_greater = p_less = p_two = 0.0
    for x in range(lo, hi + 1):
        p = pmf(x)
        if x >= a:
            p_greater += p
        if x <= a:
            p_less += p
        if p <= p_obs + 1e-15:
            p_two += p
    return {
        "table": [[a, b], [c, d]],
        "p_greater": min(1.0, p_greater),
        "p_less": min(1.0, p_less),
        "p_two_sided": min(1.0, p_two),
        "p_obs": p_obs,
        "alternative_greater": "row1 major rate >= row2",
    }


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def aba_major_ids(rows: list[dict], *, source: str, benchmark: str) -> set[str]:
    return {
        r["task_id"]
        for r in rows
        if r["source"] == source
        and r["benchmark"] == benchmark
        and r["label"] == "major_issue"
    }


def aba_any_ids(rows: list[dict], *, source: str, benchmark: str) -> set[str]:
    return {
        r["task_id"]
        for r in rows
        if r["source"] == source
        and r["benchmark"] == benchmark
        and r["label"] != "none"
    }


def tb_pre_execution(pairs_summary: dict) -> dict:
    """27 tasks with a pre-fix execution result; 9 fail, 18 pass."""

    fail: list[str] = []
    passed: list[str] = []
    skipped: list[str] = []
    tasks = pairs_summary.get("tasks") or {}
    for tid, rec in tasks.items():
        pre_status = rec.get("pre_status") or []
        executed = any(s == "executed" for s in pre_status)
        if rec.get("infra") and not executed:
            skipped.append(tid)
            continue
        if not executed and rec.get("pre", {}).get("oracle") is None:
            skipped.append(tid)
            continue
        if rec.get("false_reject_pre") or rec.get("pre_oracle_pass") is False:
            fail.append(tid)
        elif rec.get("pre_oracle_pass") is True:
            passed.append(tid)
        elif rec.get("pre", {}).get("oracle") == 0.0:
            fail.append(tid)
        elif rec.get("pre", {}).get("oracle") == 1.0:
            passed.append(tid)
        else:
            skipped.append(tid)
    return {"fail": sorted(fail), "pass": sorted(passed), "skipped": sorted(skipped)}


def t1_tb2_verifier(label_rows: list[dict], pairs_summary: dict) -> dict:
    groups = tb_pre_execution(pairs_summary)
    majors = aba_major_ids(label_rows, source="aba", benchmark="terminal-bench-2")
    fail = groups["fail"]
    passed = groups["pass"]
    a = sum(1 for t in fail if t in majors)
    b = len(fail) - a
    c = sum(1 for t in passed if t in majors)
    d = len(passed) - c
    rate_fail = a / len(fail) if fail else None
    rate_pass = c / len(passed) if passed else None
    higher = (
        rate_fail is not None
        and rate_pass is not None
        and rate_fail > rate_pass
    )
    fish = fisher_exact_2x2(a, b, c, d)
    return {
        "predicate": PREDICATES["T1"],
        "n_fail": len(fail),
        "n_pass": len(passed),
        "n_skipped": len(groups["skipped"]),
        "fail_ids": fail,
        "pass_ids": passed,
        "skipped_ids": groups["skipped"],
        "fail_major_ids": [t for t in fail if t in majors],
        "pass_major_ids": [t for t in passed if t in majors],
        "table": {
            "rows": ["pre_fail", "pre_pass"],
            "cols": ["aba_major", "not_major"],
            "counts": [[a, b], [c, d]],
        },
        "rate_fail": rate_fail,
        "rate_pass": rate_pass,
        "higher_rate_on_fail": higher,
        "fisher": fish,
        "pass_predicate": higher,
    }


def census_flags(census_rows: list[dict]) -> dict:
    by: dict[str, dict[str, list]] = defaultdict(lambda: {"oracle": [], "nop": []})
    for rec in census_rows:
        probe = rec.get("probe")
        if probe in {"oracle", "nop"}:
            by[rec["task_id"]][probe].append(rec)
    flagged = []
    rest = []
    incomplete_ids = []
    for tid, probes in by.items():
        oracles = [r for r in probes["oracle"] if r.get("status") == "executed"]
        nops = [r for r in probes["nop"] if r.get("status") == "executed"]
        if not oracles or not nops:
            incomplete_ids.append(tid)
            continue
        ref_fail = any(r.get("intended") == "accept" and not r.get("accepted") for r in oracles)
        nop_pass = any(r.get("intended") == "reject" and r.get("accepted") for r in nops)
        if ref_fail or nop_pass:
            flagged.append(
                {
                    "task_id": tid,
                    "reference_fail": ref_fail,
                    "nop_pass": nop_pass,
                }
            )
        else:
            rest.append(tid)
    return {
        "n_tasks_in_census": len(by),
        "n_complete": len(flagged) + len(rest),
        "flagged": flagged,
        "rest": sorted(rest),
        "incomplete_ids": sorted(incomplete_ids),
    }


def t2_tb2_census(
    label_rows: list[dict],
    census_rows: list[dict],
    *,
    catalog_n: int = 89,
) -> dict:
    flags = census_flags(census_rows)
    majors = aba_major_ids(label_rows, source="aba", benchmark="terminal-bench-2")
    flagged_ids = [x["task_id"] for x in flags["flagged"]]
    rest = flags["rest"]
    a = sum(1 for t in flagged_ids if t in majors)
    b = len(flagged_ids) - a
    c = sum(1 for t in rest if t in majors)
    d = len(rest) - c
    incomplete = flags["n_tasks_in_census"] < catalog_n
    rate_f = a / len(flagged_ids) if flagged_ids else None
    rate_r = c / len(rest) if rest else None
    enriched = (
        rate_f is not None and rate_r is not None and rate_f > rate_r
    )
    return {
        "predicate": PREDICATES["T2"],
        "census_incomplete": incomplete,
        "n_catalog": catalog_n,
        "n_census_tasks": flags["n_tasks_in_census"],
        "n_complete_pairs": flags["n_complete"],
        "n_flagged": len(flagged_ids),
        "flagged": flags["flagged"],
        "table": {
            "rows": ["ref_fail_or_nop_pass", "rest"],
            "cols": ["aba_major", "not_major"],
            "counts": [[a, b], [c, d]],
        },
        "rate_flagged": rate_f,
        "rate_rest": rate_r,
        "enriched": enriched,
        "fisher": fisher_exact_2x2(a, b, c, d) if flagged_ids and rest else None,
        "note": (
            f"Census has {flags['n_tasks_in_census']} of {catalog_n} TB 2.1 "
            "tasks; results are on the rows available."
            if incomplete
            else "Census covers the 89-task catalog."
        ),
    }


def _score_auroc(y: list[int], scores: list[float], n_bootstrap: int, seed: int) -> dict:
    boot = bootstrap_auroc(y, scores, n_reps=n_bootstrap, seed=seed)
    return boot


def t3_swe_verified_spec(
    label_rows: list[dict],
    judge_rows: list[dict],
    irt_items: list[dict],
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    aba = {
        r["task_id"]: r
        for r in label_rows
        if r["source"] == "aba" and r["benchmark"] == "swe-bench-verified"
    }
    majors = {tid for tid, r in aba.items() if r["label"] == "major_issue"}
    judge = {r["task_id"]: r for r in judge_rows}
    irt = {r["task_id"]: r for r in irt_items}
    common = sorted(set(aba) & set(judge) & set(irt))
    y = [1 if tid in majors else 0 for tid in common]
    p_invalid = [float(judge[tid]["p_invalid"]) for tid in common]
    one_minus_pi = [1.0 - float(irt[tid]["p_i"]) for tid in common]
    conservative = [
        int(judge[tid].get("openai_2024_conservative") or 0) for tid in common
    ]
    judge_auc = _score_auroc(y, p_invalid, n_bootstrap, seed)
    solve_auc = _score_auroc(y, one_minus_pi, n_bootstrap, seed + 1)
    old_auc = _score_auroc(y, [float(v) for v in conservative], n_bootstrap, seed + 2)
    jv = judge_auc.get("value")
    return {
        "predicate": PREDICATES["T3"],
        "n_aba": len(aba),
        "n_aba_major": len(majors),
        "n_joined": len(common),
        "n_major_in_joined": sum(y),
        "n_conservative_positive_in_joined": int(sum(conservative)),
        "judge_p_invalid": judge_auc,
        "solve_rate_1_minus_pi": solve_auc,
        "openai_2024_conservative": old_auc,
        "pass_predicate": jv is not None and jv >= T3_JUDGE_MIN,
        "threshold": T3_JUDGE_MIN,
    }


def t4_pro_spec(
    label_rows: list[dict],
    feature_rows: list[dict],
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    aba = [
        r
        for r in label_rows
        if r["source"] == "aba" and r["benchmark"] == "swe-bench-pro"
    ]
    static_major = {r["task_id"] for r in aba if int(r.get("static_major") or 0) > 0}
    traj_major = {r["task_id"] for r in aba if int(r.get("trajectory_major") or 0) > 0}
    oc = {
        r["task_id"]
        for r in label_rows
        if r["source"] == "opencompass_pro_verified"
    }
    jk = {r["task_id"] for r in label_rows if r["source"] == "june_kim_pro"}
    feats = []
    for rec in feature_rows:
        feats.append(
            {
                "task_id": rec["task_id"],
                "openai_style_risk": float(rec["features"]["openai_style_risk"]),
                "cheap_risk": float(rec["features"]["cheap_risk"]),
            }
        )
    ids = [r["task_id"] for r in feats]
    n = len(feats)

    def block(score_key: str, positive: set[str]) -> dict:
        ranked = [
            r["task_id"]
            for r in sorted(feats, key=lambda r: float(r[score_key]), reverse=True)
        ]
        y = [1 if tid in positive else 0 for tid in ids]
        scores = [float(r[score_key]) for r in feats]
        return {
            "n_positive": len(positive & set(ids)),
            "auroc": _score_auroc(y, scores, n_bootstrap, seed),
            "top_decile": enrichment(ranked, positive, TOP_FRAC),
        }

    return {
        "predicate": PREDICATES["T4"],
        "n_pro": n,
        "n_static_major": len(static_major),
        "n_traj_major": len(traj_major),
        "openai_style_risk": {
            "static_major": block("openai_style_risk", static_major),
            "trajectory_major": block("openai_style_risk", traj_major),
        },
        "cheap_risk": {
            "static_major": block("cheap_risk", static_major),
            "trajectory_major": block("cheap_risk", traj_major),
        },
        "overlap": {
            "opencompass_n": len(oc),
            "june_kim_n": len(jk),
            "aba_static_vs_opencompass": {
                "jaccard": jaccard(static_major, oc),
                "n_intersection": len(static_major & oc),
            },
            "aba_traj_vs_opencompass": {
                "jaccard": jaccard(traj_major, oc),
                "n_intersection": len(traj_major & oc),
            },
            "aba_static_vs_june_kim": {
                "jaccard": jaccard(static_major, jk),
                "n_intersection": len(static_major & jk),
            },
            "aba_traj_vs_june_kim": {
                "jaccard": jaccard(traj_major, jk),
                "n_intersection": len(traj_major & jk),
            },
            "opencompass_vs_june_kim": {
                "jaccard": jaccard(oc, jk),
                "n_intersection": len(oc & jk),
            },
        },
    }


def t5_swe_random100(label_rows: list[dict]) -> dict:
    aba = {
        r["task_id"]: r
        for r in label_rows
        if r["source"] == "aba" and r["benchmark"] == "swe-bench-verified"
    }
    out = []
    for tid in T5_FLAGS:
        rec = aba.get(tid)
        if rec is None:
            out.append(
                {
                    "task_id": tid,
                    "in_aba_verified": False,
                    "label": None,
                    "static_major": None,
                    "trajectory_major": None,
                    "finding_class": None,
                    "any_finding": None,
                }
            )
            continue
        out.append(
            {
                "task_id": tid,
                "in_aba_verified": True,
                "label": rec["label"],
                "static_major": rec.get("static_major"),
                "trajectory_major": rec.get("trajectory_major"),
                "finding_class": rec.get("finding_class"),
                "any_finding": rec["label"] != "none",
                "construct": rec.get("construct"),
                "severity": rec.get("severity"),
            }
        )
    return {"predicate": PREDICATES["T5"], "flags": out}


def ingest_rows(
    *,
    aba_dir: Path,
    benchguard_dir: Path,
    tau2_changelog: Path,
    zai_changes: Path,
    tb21_maintenance: Path,
    opencompass_labels: Path,
    june_kim_claims: Path,
    pro_features: Path,
) -> list[dict]:
    rows: list[dict] = []
    date = ABA_DATES["index"]
    for slug in ABA_SLUGS:
        path = aba_dir / slug / "benchmark.json"
        if not path.is_file():
            continue
        bench = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(
            parse_aba_benchmark(
                bench,
                provenance=f"{ABA_BASE}/{slug}/benchmark.json",
                date=date,
                cache_dir=aba_dir,
                slug=slug,
            )
        )
    sab_path = benchguard_dir / "sab_gold.json"
    if sab_path.is_file():
        rows.extend(
            parse_benchguard_gold(
                json.loads(sab_path.read_text(encoding="utf-8")),
                source="benchguard_sab",
                benchmark="science-agent-bench",
                join_key_kind="sab_task_key",
                construct="mixed",
                provenance=(
                    "https://raw.githubusercontent.com/XinmingTu/BenchGuard/"
                    "main/eval/data/gold/sab_gold.json"
                ),
                date="2026-03-10",
            )
        )
    bix_path = benchguard_dir / "bixbench_gold.json"
    if bix_path.is_file():
        rows.extend(
            parse_benchguard_gold(
                json.loads(bix_path.read_text(encoding="utf-8")),
                source="benchguard_bix",
                benchmark="bixbench-v50",
                join_key_kind="bix_question_id",
                construct="spec_invalid",
                provenance=(
                    "https://raw.githubusercontent.com/XinmingTu/BenchGuard/"
                    "main/eval/data/gold/bixbench_gold.json"
                ),
                date="2026-03-07",
            )
        )
    if tau2_changelog.is_file():
        rows.extend(
            parse_tau2_changelog(tau2_changelog.read_text(encoding="utf-8", errors="replace"))
        )
    if zai_changes.is_file():
        rows.extend(
            parse_zai_changes(zai_changes.read_text(encoding="utf-8", errors="replace"))
        )
    rows.extend(parse_tb21_maintenance_rows(tb21_maintenance))
    rows.extend(parse_opencompass_labels(opencompass_labels))
    pro_ids = []
    if pro_features.is_file():
        for rec in load_jsonl(pro_features):
            pro_ids.append(rec["task_id"])
    rows.extend(parse_june_kim_labels(june_kim_claims, pro_ids))
    if pro_ids:
        rows = map_pro_casefold(rows, pro_ids)
    rows.sort(key=lambda r: (r["source"], r["benchmark"], r["task_id"]))
    return rows


def run_transfer(
    rows: list[dict],
    *,
    pairs_summary: dict,
    census_rows: list[dict],
    judge_rows: list[dict],
    irt_items: list[dict],
    feature_rows: list[dict],
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    return {
        "predicates_frozen": PREDICATES,
        "T1": t1_tb2_verifier(rows, pairs_summary),
        "T2": t2_tb2_census(rows, census_rows),
        "T3": t3_swe_verified_spec(
            rows, judge_rows, irt_items, n_bootstrap=n_bootstrap, seed=seed
        ),
        "T4": t4_pro_spec(
            rows, feature_rows, n_bootstrap=n_bootstrap, seed=seed
        ),
        "T5": t5_swe_random100(rows),
    }


def build_summary(rows: list[dict], transfer: dict | None) -> dict:
    by_source: dict[str, dict] = {}
    for rec in rows:
        slot = by_source.setdefault(
            rec["source"],
            {"n": 0, "by_label": {}, "by_construct": {}, "by_benchmark": {}},
        )
        slot["n"] += 1
        slot["by_label"][rec["label"]] = slot["by_label"].get(rec["label"], 0) + 1
        slot["by_construct"][rec["construct"]] = (
            slot["by_construct"].get(rec["construct"], 0) + 1
        )
        slot["by_benchmark"][rec["benchmark"]] = (
            slot["by_benchmark"].get(rec["benchmark"], 0) + 1
        )
    aba_slice = {}
    for rec in rows:
        if rec["source"] != "aba":
            continue
        b = rec["benchmark"]
        s = aba_slice.setdefault(
            b, {"n": 0, "major": 0, "minor": 0, "none": 0, "static_major": 0, "traj_major": 0}
        )
        s["n"] += 1
        if rec["label"] == "major_issue":
            s["major"] += 1
        elif rec["label"] == "minor_issue":
            s["minor"] += 1
        else:
            s["none"] += 1
        if int(rec.get("static_major") or 0) > 0:
            s["static_major"] += 1
        if int(rec.get("trajectory_major") or 0) > 0:
            s["traj_major"] += 1
    return {
        "as_of": "2026-09-12",
        "eval_only": True,
        "n_rows": len(rows),
        "join_rules": JOIN_RULES,
        "predicates_frozen": PREDICATES,
        "by_source": by_source,
        "by_construct": count_by(rows, "construct"),
        "by_label": count_by(rows, "label"),
        "aba_slice": aba_slice,
        "overlap_matrix": overlap_matrix(rows),
        "transfer": transfer,
        "constraints": {
            "used_audit_labels_as_predictors": False,
            "tuned_weights": False,
            "eval_only": True,
            "model_api_calls": False,
            "human_census": False,
        },
    }


def run(
    *,
    repo: Path = REPO_ROOT,
    download: bool = False,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    raw = repo / "data" / "raw"
    gold = repo / "data" / "gold"
    aba_dir = raw / "aba"
    if download:
        download_aux(raw)
        download_aba_slice(aba_dir)
    pro_features = gold / "swe_pro_features.jsonl"
    rows = ingest_rows(
        aba_dir=aba_dir,
        benchguard_dir=raw / "benchguard",
        tau2_changelog=raw / "tau2-bench" / "CHANGELOG.md",
        zai_changes=raw / "zai-tb2-verified" / "changes_instructions.md",
        tb21_maintenance=gold / "tb21_maintenance.jsonl",
        opencompass_labels=gold / "pro_verified_labels.jsonl",
        june_kim_claims=raw / "swe-bench-pro" / "CLAIMS.md",
        pro_features=pro_features,
    )
    labels_path = gold / "labels_2026.jsonl"
    write_jsonl(labels_path, rows)
    pairs = json.loads((gold / "tb21_pairs.summary.json").read_text(encoding="utf-8"))
    census = load_jsonl(gold / "tb21_census.jsonl")
    judge = load_jsonl(gold / "swe_llm_audit_full.jsonl")
    irt_obj = json.loads((gold / "swe_irt.json").read_text(encoding="utf-8"))
    irt_items = irt_obj["items"] if isinstance(irt_obj, dict) else irt_obj
    feats = load_jsonl(pro_features)
    transfer = run_transfer(
        rows,
        pairs_summary=pairs,
        census_rows=census,
        judge_rows=judge,
        irt_items=irt_items,
        feature_rows=feats,
        n_bootstrap=n_bootstrap,
        seed=seed,
    )
    summary = build_summary(rows, transfer)
    summary_path = gold / "labels_2026.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (gold / "labels_2026.transfer.json").write_text(
        json.dumps(transfer, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ingest 2026 eval-only labels and run T1-T5")
    p.add_argument("--repo", type=Path, default=REPO_ROOT)
    p.add_argument("--download", action="store_true")
    p.add_argument("--bootstrap", type=int, default=N_BOOTSTRAP)
    p.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run(
        repo=args.repo,
        download=args.download,
        n_bootstrap=args.bootstrap,
        seed=args.seed,
    )
    print(json.dumps({k: summary[k] for k in ("n_rows", "by_source", "by_construct", "by_label", "aba_slice") if k in summary}, indent=2))
    tr = summary.get("transfer") or {}
    for key in ("T1", "T2", "T3", "T4", "T5"):
        print(key, json.dumps(tr.get(key), indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
