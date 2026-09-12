"""OpenCompass SWE-Bench Pro Verified transfer (eval-only).

Joins the 102 repaired IDs to public Pro cheap scores. Never uses those
IDs as features. Never tunes weights. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

from task_validation.ingest.external_audits import match_prefixes, parse_june_kim_claims

PROVENANCE = "opencompass_swebench_pro_verified_2026"
SOURCE_URL = "https://huggingface.co/datasets/opencompass/SWEBench-Pro-Verified"
ARXIV = "2609.08149"
REVISION = "ae466f824cdee69d2c010b6c954b7418c411b6e4"
LICENSE = "Apache-2.0"

TOP_FRAC = 0.10
TAIL_FRAC = 0.20
ENRICHMENT_MIN = 1.5
RESIDUAL_EPS = 0.05
MIN_MATCHED = 90
N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 20260911

CATEGORY_ORDER = (
    "misleading_prompts",
    "overly_narrow_tests",
    "overly_broad_tests",
    "other",
)
CATEGORY_ALIASES = {
    "misleading prompts": "misleading_prompts",
    "overly narrow tests": "overly_narrow_tests",
    "overly broad tests": "overly_broad_tests",
    "overly borad tests": "overly_broad_tests",
    "other issues": "other",
    "other": "other",
}
HEADING_RE = re.compile(
    r"\*\*(Misleading prompts|Overly narrow tests|Overly broad tests|"
    r"Overly borad tests|Other issues)\*\*",
    re.I,
)
INSTANCE_RE = re.compile(r"instance_[A-Za-z0-9][A-Za-z0-9_.-]*")
INSTANCE_ID_JSON_RE = re.compile(r'"instance_id"\s*:\s*"([^"]+)"')

PREDICATES = {
    "P1": (
        "The 102 repaired IDs are enriched >= 1.5x in the top 10% of "
        "openai_style_risk versus the 102/731 base rate."
    ),
    "P2": (
        "The overly-narrow-tests subset (75) is enriched more than the "
        "misleading-prompts subset (22) in that same top 10%."
    ),
    "P3": (
        "The lowest-risk 20% by openai_style_risk still contains > 5% "
        "repaired IDs."
    ),
}


def head_size(n: int, frac: float) -> int:
    if n <= 0:
        return 0
    return min(n, max(1, int(round(frac * n))))


def parse_repaired_markdown(text: str) -> list[dict]:
    """Read category -> instance_id lists from OpenCompass README Part II."""

    lower = text.lower()
    start = lower.find("part ii")
    if start < 0:
        start = lower.find("misleading prompts")
    chunk = text[start:] if start >= 0 else text
    for stop in ("\n## contact", "\n## acknowledgments", "\n## citation"):
        i = chunk.lower().find(stop)
        if i >= 0:
            chunk = chunk[:i]
            break
    current: str | None = None
    out: list[dict] = []
    seen: set[str] = set()
    for line in chunk.splitlines():
        heading = HEADING_RE.search(line)
        if heading:
            current = CATEGORY_ALIASES[heading.group(1).lower()]
            continue
        if current is None:
            continue
        for iid in INSTANCE_RE.findall(line):
            if iid in seen:
                continue
            seen.add(iid)
            out.append({"instance_id": iid, "category": current})
    return out


def load_jsonl_instance_ids(path: Path) -> list[str]:
    ids: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = INSTANCE_ID_JSON_RE.search(line)
            if m:
                ids.append(m.group(1))
    return ids


def load_repaired(path: Path) -> list[dict]:
    """Load 102 repaired IDs from a verified dump dir, markdown, or jsonl."""

    if path.is_dir():
        readme = path / "README.md"
        claims = path / "CLAIMS.md"
        labels = path / "repaired.jsonl"
        if readme.is_file():
            return parse_repaired_markdown(readme.read_text(encoding="utf-8", errors="replace"))
        if labels.is_file():
            return _load_repaired_jsonl(labels)
        if claims.is_file():
            return parse_repaired_markdown(claims.read_text(encoding="utf-8", errors="replace"))
        raise FileNotFoundError(f"no README.md / repaired.jsonl / CLAIMS.md under {path}")
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".md", ".markdown"}:
        return parse_repaired_markdown(path.read_text(encoding="utf-8", errors="replace"))
    return _load_repaired_jsonl(path)


def _load_repaired_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            iid = rec.get("instance_id") or rec.get("task_id")
            cat = rec.get("category") or "other"
            cat = CATEGORY_ALIASES.get(str(cat).lower().replace("_", " "), cat)
            if iid:
                out.append({"instance_id": str(iid), "category": str(cat)})
    return out


def load_feature_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            feats = rec.get("features") or {}
            if "openai_style_risk" not in feats or "cheap_risk" not in feats:
                raise KeyError(f"missing risk fields on {rec.get('task_id')}")
            rows.append(rec)
    return rows


def map_instance_ids(verified_ids: list[str], pro_ids: list[str]) -> dict:
    """Map verified instance IDs onto public Pro task_ids. No fuzzy guessing."""

    pro_set = set(pro_ids)
    mapping: dict[str, str] = {}
    method: dict[str, str] = {}
    unmatched: list[str] = []

    def take(vid: str, pid: str, how: str) -> None:
        mapping[vid] = pid
        method[vid] = how

    remaining = []
    for vid in verified_ids:
        if vid in pro_set:
            take(vid, vid, "exact")
            continue
        stripped = vid[len("instance_") :] if vid.startswith("instance_") else vid
        added = vid if vid.startswith("instance_") else f"instance_{vid}"
        if stripped in pro_set:
            take(vid, stripped, "prefix_strip")
            continue
        if added in pro_set:
            take(vid, added, "prefix_add")
            continue
        remaining.append(vid)

    unused = [p for p in pro_ids if p not in set(mapping.values())]
    for vid in remaining:
        hits = [p for p in unused if p.startswith(vid) or vid.startswith(p)]
        if len(hits) == 1:
            take(vid, hits[0], "unique_prefix")
            unused = [p for p in unused if p != hits[0]]
        else:
            unmatched.append(vid)

    return {
        "mapping": mapping,
        "method": method,
        "unmatched": unmatched,
        "n_verified": len(verified_ids),
        "n_matched": len(mapping),
        "n_pro": len(pro_ids),
        "n_unique_verified": len(set(verified_ids)),
    }


def join(
    feature_rows: list[dict],
    repaired_by_pro_id: dict[str, str],
    june_kim_ids: set[str],
) -> list[dict]:
    """Attach eval-only labels after scoring. Labels are not features."""

    out = []
    for rec in feature_rows:
        tid = rec["task_id"]
        feats = rec["features"]
        out.append(
            {
                "task_id": tid,
                "openai_style_risk": float(feats["openai_style_risk"]),
                "cheap_risk": float(feats["cheap_risk"]),
                "repaired": tid in repaired_by_pro_id,
                "category": repaired_by_pro_id.get(tid),
                "june_kim": tid in june_kim_ids,
            }
        )
    return out


def rank_ids(rows: list[dict], score_key: str, *, descending: bool) -> list[str]:
    return [
        r["task_id"]
        for r in sorted(rows, key=lambda r: float(r[score_key]), reverse=descending)
    ]


def enrichment(ranked_ids: list[str], positive: set[str], frac: float) -> dict:
    n = len(ranked_ids)
    n_pos = len(positive)
    base = n_pos / n if n else 0.0
    k = head_size(n, frac)
    head = ranked_ids[:k]
    hit = sum(1 for i in head if i in positive)
    rate = hit / k if k else 0.0
    return {
        "top_frac": frac,
        "k": k,
        "n_positive": n_pos,
        "n_positive_in_head": hit,
        "rate": rate,
        "base_rate": base,
        "enrichment": (rate / base) if base else None,
    }


def residual_in_tail(ranked_low_to_high: list[str], positive: set[str], frac: float) -> dict:
    n = len(ranked_low_to_high)
    k = head_size(n, frac)
    tail = ranked_low_to_high[:k]
    hit = sum(1 for i in tail if i in positive)
    return {
        "retain_frac": frac,
        "k": k,
        "n_positive": hit,
        "residual": hit / k if k else 0.0,
    }


def auroc(y: list[int], scores: list[float]) -> float | None:
    pos = [s for s, t in zip(scores, y) if t == 1]
    neg = [s for s, t in zip(scores, y) if t == 0]
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    i = p * (len(ys) - 1)
    lo = int(i)
    hi = min(lo + 1, len(ys) - 1)
    w = i - lo
    return ys[lo] * (1.0 - w) + ys[hi] * w


def bootstrap_auroc(
    y: list[int],
    scores: list[float],
    n_reps: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    point = auroc(y, scores)
    rng = random.Random(seed)
    n = len(y)
    boots: list[float] = []
    for _ in range(n_reps):
        idx = [rng.randrange(n) for _ in range(n)] if n else []
        val = auroc([y[i] for i in idx], [scores[i] for i in idx])
        if val is not None:
            boots.append(val)
    lo = _percentile(boots, 0.025)
    hi = _percentile(boots, 0.975)
    return {
        "value": point,
        "n_bootstrap": n_reps,
        "n_defined": len(boots),
        "seed": seed,
        "ci95": [lo, hi] if lo is not None and hi is not None else None,
    }


def jaccard(a: set[str], b: set[str]) -> float | None:
    union = a | b
    if not union:
        return None
    return len(a & b) / len(union)


def evaluate_predicates(openai_block: dict) -> dict:
    e_all = openai_block["all"]["enrichment"]
    e_narrow = openai_block["overly_narrow_tests"]["enrichment"]
    e_mis = openai_block["misleading_prompts"]["enrichment"]
    residual = openai_block["tail"]["residual"]
    p1 = e_all is not None and e_all >= ENRICHMENT_MIN
    p2 = (
        e_narrow is not None
        and e_mis is not None
        and e_narrow > e_mis
    )
    p3 = residual > RESIDUAL_EPS
    return {
        "P1": p1,
        "P2": p2,
        "P3": p3,
        "YES": p1 and p2 and p3,
        "P2_note": None if p2 else "score is not category-specific",
    }


def _category_sets(joined: list[dict]) -> dict[str, set[str]]:
    out = {c: set() for c in CATEGORY_ORDER}
    for r in joined:
        cat = r.get("category")
        if cat in out and r["repaired"]:
            out[cat].add(r["task_id"])
    return out


def score_block(
    joined: list[dict],
    score_key: str,
    *,
    head_frac: float = TOP_FRAC,
    tail_frac: float = TAIL_FRAC,
    n_bootstrap: int = 0,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    ranked_high = rank_ids(joined, score_key, descending=True)
    ranked_low = rank_ids(joined, score_key, descending=False)
    repaired = {r["task_id"] for r in joined if r["repaired"]}
    cats = _category_sets(joined)
    block = {
        "score_key": score_key,
        "all": enrichment(ranked_high, repaired, head_frac),
        "misleading_prompts": enrichment(ranked_high, cats["misleading_prompts"], head_frac),
        "overly_narrow_tests": enrichment(ranked_high, cats["overly_narrow_tests"], head_frac),
        "overly_broad_tests": enrichment(ranked_high, cats["overly_broad_tests"], head_frac),
        "other": enrichment(ranked_high, cats["other"], head_frac),
        "tail": residual_in_tail(ranked_low, repaired, tail_frac),
    }
    if n_bootstrap:
        y = [1 if r["repaired"] else 0 for r in joined]
        scores = [float(r[score_key]) for r in joined]
        block["auroc"] = bootstrap_auroc(y, scores, n_reps=n_bootstrap, seed=seed)
    return block


def label_rows(
    repaired: list[dict],
    mapping: dict[str, str],
) -> list[dict]:
    rows = []
    for rec in repaired:
        vid = rec["instance_id"]
        pid = mapping.get(vid)
        rows.append(
            {
                "task_id": pid or vid,
                "verified_instance_id": vid,
                "category": rec["category"],
                "provenance": PROVENANCE,
                "eval_only": True,
                "matched_to_pro": pid is not None,
                "benchmark": "swe-bench-pro",
                "benchmark_version": "public-731",
                "label": "REPAIRED",
                "source": SOURCE_URL,
                "arxiv": ARXIV,
            }
        )
    rows.sort(key=lambda r: (CATEGORY_ORDER.index(r["category"]) if r["category"] in CATEGORY_ORDER else 99, r["task_id"]))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in rows:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")


def run(
    features_path: Path,
    verified_path: Path,
    out_path: Path,
    *,
    june_kim_path: Path | None = None,
    labels_path: Path | None = None,
    min_matched: int = MIN_MATCHED,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    feature_rows = load_feature_rows(features_path)
    pro_ids = [r["task_id"] for r in feature_rows]
    repaired = load_repaired(verified_path)
    verified_ids = [r["instance_id"] for r in repaired]
    mapped = map_instance_ids(verified_ids, pro_ids)
    jsonl_ids: list[str] = []
    if verified_path.is_dir():
        dump = verified_path / "swebench_pro_verified.jsonl"
        if dump.is_file():
            jsonl_ids = load_jsonl_instance_ids(dump)
    jsonl_overlap = len(set(jsonl_ids) & set(pro_ids)) if jsonl_ids else None
    cat_listed = {}
    for rec in repaired:
        cat_listed[rec["category"]] = cat_listed.get(rec["category"], 0) + 1

    mapping_report = {
        **{k: mapped[k] for k in ("n_verified", "n_matched", "n_pro", "n_unique_verified", "unmatched")},
        "methods": {},
        "jsonl_n": len(jsonl_ids) if jsonl_ids else None,
        "jsonl_exact_overlap_with_pro": jsonl_overlap,
        "category_listed": cat_listed,
        "how": "exact instance_id == task_id; then add/strip instance_ prefix; then unique prefix only",
        "min_matched": min_matched,
        "mapping_ok": mapped["n_matched"] >= min_matched,
    }
    for how in ("exact", "prefix_strip", "prefix_add", "unique_prefix"):
        mapping_report["methods"][how] = sum(1 for v in mapped["method"].values() if v == how)

    labels = label_rows(repaired, mapped["mapping"])
    if labels_path is not None:
        write_jsonl(labels_path, labels)

    if not mapping_report["mapping_ok"]:
        report = {
            "error": "mapping_below_threshold",
            "mapping": mapping_report,
            "predicates": PREDICATES,
            "constraints": {
                "used_audit_labels_as_predictors": False,
                "tuned_weights": False,
                "eval_only": True,
            },
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    repaired_by_pro = {}
    for rec in repaired:
        pid = mapped["mapping"].get(rec["instance_id"])
        if pid:
            repaired_by_pro[pid] = rec["category"]

    june_ids: set[str] = set()
    june_meta = {"n_prefixes": 0, "n_matched": 0}
    if june_kim_path is not None and june_kim_path.is_file():
        prefixes = parse_june_kim_claims(june_kim_path)
        hits = match_prefixes(pro_ids, prefixes)
        june_ids = set(hits)
        june_meta = {"n_prefixes": len(prefixes), "n_matched": len(june_ids), "path": str(june_kim_path)}

    joined = join(feature_rows, repaired_by_pro, june_ids)
    openai_block = score_block(
        joined,
        "openai_style_risk",
        n_bootstrap=n_bootstrap,
        seed=seed,
    )
    cheap_block = score_block(joined, "cheap_risk", n_bootstrap=0, seed=seed)
    openai_block["predicates"] = evaluate_predicates(openai_block)
    cheap_block["predicates"] = evaluate_predicates(cheap_block)

    repaired_set = {r["task_id"] for r in joined if r["repaired"]}
    ranked_high = rank_ids(joined, "openai_style_risk", descending=True)
    inter = repaired_set & june_ids
    union = repaired_set | june_ids
    overlap = {
        "n_repaired": len(repaired_set),
        "n_june_kim": len(june_ids),
        "n_intersection": len(inter),
        "n_union": len(union),
        "jaccard": jaccard(repaired_set, june_ids),
        "intersection_enrichment": enrichment(ranked_high, inter, TOP_FRAC),
        "union_enrichment": enrichment(ranked_high, union, TOP_FRAC),
        "june_kim": june_meta,
    }

    report = {
        "source": {
            "huggingface": "opencompass/SWEBench-Pro-Verified",
            "revision": REVISION,
            "license": LICENSE,
            "arxiv": ARXIV,
            "provenance": PROVENANCE,
            "features": str(features_path),
            "verified": str(verified_path),
        },
        "predicates_frozen": PREDICATES,
        "mapping": mapping_report,
        "n_pro": len(joined),
        "openai_style_risk": openai_block,
        "cheap_risk": cheap_block,
        "june_kim_overlap": overlap,
        "constraints": {
            "used_audit_labels_as_predictors": False,
            "tuned_weights": False,
            "eval_only": True,
            "llm": False,
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Eval-only OpenCompass Pro Verified transfer")
    p.add_argument("--features", type=Path, default=Path("data/gold/swe_pro_features.jsonl"))
    p.add_argument("--verified", type=Path, default=Path("data/raw/swe-bench-pro-verified"))
    p.add_argument("--out", type=Path, default=Path("data/gold/pro_verified_transfer.json"))
    p.add_argument("--june-kim", type=Path, default=Path("data/raw/swe-bench-pro/CLAIMS.md"))
    p.add_argument("--labels-out", type=Path, default=Path("data/gold/pro_verified_labels.jsonl"))
    p.add_argument("--min-matched", type=int, default=MIN_MATCHED)
    p.add_argument("--bootstrap", type=int, default=N_BOOTSTRAP)
    p.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run(
        args.features,
        args.verified,
        args.out,
        june_kim_path=args.june_kim,
        labels_path=args.labels_out,
        min_matched=args.min_matched,
        n_bootstrap=args.bootstrap,
        seed=args.seed,
    )
    print(json.dumps(report, indent=2))
    if report.get("error") == "mapping_below_threshold":
        print("mapping problem: fewer than min-matched IDs joined; not guessing", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
