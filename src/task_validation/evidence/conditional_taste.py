"""Taste conditional on validity, within and across populations (doc 59).

Taste is measured only among tasks already valid under the majority
protocol, so a kept label cannot conflate "not broken" with "worth
keeping". Keep decisions by population:

- swe: Verified-500 membership, parsed from the ABA static_audits
  filenames (<instance_id>__<hash>.json). taste_kept is defined on the
  935 majority-valid annotated tasks only.
- tb21: the 28 maintenance repairs (maintainer fix-or-drop decision),
  conditioned on the 89-task census verifier verdict.
- harbor_index funnel: survived_2_to_4 among the 1,331 reconstructed
  stage-1 survivors. Stage 1 is a difficulty screen, not a validity
  label, so the conditioning is weak there (doc 54 caveat).

Model class is doc 40: median imputation, missingness indicators,
standardized design matrix, class-weighted L2 logistic (fit_logit in
footprint.py). External labels are eval-only (doc 43); nothing here
enters a bound.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path

from task_validation.evidence.footprint import (
    CURATED_FEATURES,
    LOG1P_FEATURES,
    LOGIT_L2,
    LOGIT_MAX_ITER,
    _as_float,
    _mean,
    fit_logit,
    load_jsonl,
    predict_logit,
    write_json,
    write_jsonl,
)
from task_validation.evidence.harbor_funnel import (
    _pos_weighted_mean_auroc,
    _stratified_boot_idx,
    within_group_concordance,
)
from task_validation.evidence.irt import auroc, bootstrap_auroc
from task_validation.evidence.swe_artifacts import CHEAP_FEATURE_NAMES

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD = REPO_ROOT / "data" / "gold"
RAW = REPO_ROOT / "data" / "raw"

VERIFIED500_AUDIT_DIR = RAW / "aba" / "swe_bench_verified" / "static_audits"
VERIFIED500_IDS_PATH = GOLD / "swe_verified500_ids.json"
TASTE_LABELS_PATH = GOLD / "swe_taste_labels.jsonl"
EVAL_PATH = GOLD / "conditional_taste_eval.json"
RATERS_PATH = GOLD / "swe_rater_targets.jsonl"
SWE_FEATURES_PATH = GOLD / "swe_verified_features.jsonl"
IRT_PATH = GOLD / "swe_irt.json"
FOOTPRINT_PATH = GOLD / "footprint.jsonl"
TB21_CENSUS_PATH = GOLD / "tb21_census_verdicts.jsonl"
TB21_MAINT_PATH = GOLD / "tb21_maintenance.jsonl"
FUNNEL_WITHIN_PATH = GOLD / "harbor_funnel_within_benchmark.json"
FUNNEL_EVAL_PATH = GOLD / "harbor_funnel_traj_eval.json"
FUNNEL_STAGE1_SUMMARY = GOLD / "harbor_funnel_stage1.summary.json"

BOOT_SEED = 20260914
N_BOOT = 400
RETAIN_FRACS = (0.05, 0.10, 0.20)
WITHIN_MIN_POS = 5
WITHIN_MIN_NEG = 5
OVERLAP_K_FOLD = 5
OVERLAP_SEED = 20260914

MAJORITY_PROTOCOL = "openai-swe-bench-verified-2024-majority"
VERIFIED500_PROTOCOL = "swe_verified500_membership.static_audits.2026-09-14"
TASTE_PROTOCOL = "swe_taste_kept.verified500_given_majority_valid.2026-09-14"
TB21_CENSUS_PROTOCOL = "verifier_invalid.fresh_environment.execution"
TB21_TASTE_PROTOCOL = "tb21_maintainer_repair_given_census_valid.2026-09-14"

# Cheap features whose doc-40 footprint equivalents are log1p-transformed
# (stmt_chars -> instruction_chars, etc.). The transform set follows the
# feature semantics, not the name, so the cheap table gets the same
# treatment the footprint table does.
CHEAP_LOG1P = frozenset(
    {
        "stmt_chars",
        "stmt_lines",
        "stmt_n_identifiers",
        "hints_chars",
        "n_fail_to_pass",
        "n_pass_to_pass",
        "patch_n_changed_lines",
        "test_n_files",
        "test_n_changed_lines",
    }
)

# Doc-33 IRT block: empirical solve rate plus the stored 2PL parameters.
IRT_FEATURES = ("irt_p_i", "irt_a_i", "irt_b_i")

_AUDIT_NAME_RE = re.compile(r"^(.+)__([0-9a-fA-F]{6,64})\.json$")


# --- Verified-500 id parsing ------------------------------------------------


def parse_verified500_ids(audit_dir: Path) -> list[str]:
    """Verified-500 membership from static_audits filenames.

    Each file is <instance_id>__<hexhash>.json. Instance ids themselves
    contain "__" (astropy__astropy-12907), so the split is on the final
    "__" and the suffix must be hex. Non-.json files are ignored; a
    malformed .json name raises.
    """

    ids = []
    for p in sorted(Path(audit_dir).iterdir()):
        if not p.is_file():
            continue
        if p.suffix != ".json":
            continue
        m = _AUDIT_NAME_RE.match(p.name)
        if m is None:
            raise ValueError(f"audit filename does not match <id>__<hex>.json: {p.name}")
        ids.append(m.group(1))
    return sorted(set(ids))


def write_verified500_ids(
    audit_dir: Path = VERIFIED500_AUDIT_DIR,
    out_path: Path = VERIFIED500_IDS_PATH,
) -> dict:
    ids = parse_verified500_ids(audit_dir)
    obj = {
        "schema": "swe_verified500_ids.v1",
        "n": len(ids),
        "ids": ids,
        "provenance": {
            "source_dir": str(audit_dir),
            "filename_pattern": "<instance_id>__<hexhash>.json",
            "parse": "final '__' splits instance_id from the audit hash; suffix must be hex",
            "source": "ABA swe-bench-verified static audit files (Verified-500 membership list)",
            "created": "2026-09-14",
            "check": (
                "Equals the swe-bench-verified id set in "
                "data/gold/labels_2026.jsonl (source=aba); all 500 ids sit "
                "inside the 1,699 annotated rows of swe_rater_targets.jsonl."
            ),
        },
    }
    write_json(out_path, obj)
    return obj


# --- Label rows -------------------------------------------------------------


def _label(value, protocol: str, grade: str, adjudicator: str, **extra) -> dict:
    rec = {
        "value": value,
        "protocol": protocol,
        "grade": grade,
        "adjudicator": adjudicator,
    }
    rec.update(extra)
    return rec


def build_swe_taste_labels(
    raters: dict[str, dict],
    repositories: dict[str, str],
    v500: set[str],
) -> list[dict]:
    """One row per annotated instance. taste_kept exists only on
    majority-valid tasks; it is Verified-500 membership there."""

    rows = []
    for tid in sorted(raters):
        r = raters[tid]
        in500 = tid in v500
        majority_invalid = int(r.get("majority_invalid") or 0)
        kept = None if majority_invalid else int(in500)
        rows.append(
            {
                "task_id": tid,
                "population": "swe",
                "repository": repositories.get(tid),
                "n_raters": r.get("n_raters"),
                "n_material_votes": r.get("n_material_votes"),
                "votes": r.get("votes"),
                "validity": {
                    "openai_2024_conservative": _label(
                        int(r.get("openai_2024_conservative") or 0),
                        "openai-swe-bench-verified-2024-conservative",
                        "A",
                        "human_raters_3",
                        eval_only=True,
                    ),
                    "majority_invalid": _label(
                        majority_invalid,
                        MAJORITY_PROTOCOL,
                        "A",
                        "human_raters_3",
                        eval_only=True,
                    ),
                    "unanimous_invalid": _label(
                        int(r.get("unanimous_invalid") or 0),
                        "openai-swe-bench-verified-2024-unanimous",
                        "A",
                        "human_raters_3",
                        eval_only=True,
                    ),
                },
                "in_verified500": _label(
                    in500,
                    VERIFIED500_PROTOCOL,
                    "A",
                    "published_list",
                    eval_only=True,
                    provenance=str(VERIFIED500_IDS_PATH),
                ),
                "taste_kept": _label(
                    kept,
                    TASTE_PROTOCOL,
                    "A",
                    "published_list",
                    eval_only=True,
                    condition="majority_invalid == 0",
                    derivation=(
                        "Verified-500 membership on majority-valid rows; "
                        "null on majority-invalid rows so kept never "
                        "conflates not-broken with worth-keeping"
                    ),
                ),
            }
        )
    return rows


def validity_membership_2x2(rows: list[dict]) -> dict:
    """Validity-protocol x Verified-500 membership cross-tabs."""

    out = {}
    for key in ("openai_2024_conservative", "majority_invalid", "unanimous_invalid"):
        tab = {"valid_kept": 0, "valid_not_kept": 0, "invalid_kept": 0, "invalid_not_kept": 0}
        for r in rows:
            invalid = int(r["validity"][key]["value"] or 0)
            kept = bool(r["in_verified500"]["value"])
            cell = ("invalid_" if invalid else "valid_") + ("kept" if kept else "not_kept")
            tab[cell] += 1
        n = sum(tab.values())
        n_valid = tab["valid_kept"] + tab["valid_not_kept"]
        n_kept = tab["valid_kept"] + tab["invalid_kept"]
        out[key] = {
            **tab,
            "n": n,
            "n_valid": n_valid,
            "n_kept": n_kept,
            "p_kept_given_valid": (tab["valid_kept"] / n_valid) if n_valid else None,
            "p_valid_given_kept": (tab["valid_kept"] / n_kept) if n_kept else None,
            "kept_rate_overall": n_kept / n if n else None,
        }
    return out


# --- Design matrix (doc 40 class, parameterized transform set) ---------------


def design_matrix(
    rows: list[dict],
    names: tuple[str, ...],
    *,
    stats: dict | None = None,
    missing_indicators: bool = True,
    log1p_names: frozenset = LOG1P_FEATURES,
) -> tuple[list[list[float]], dict]:
    """Same construction as footprint.design_matrix with an explicit
    log1p set so the cheap-feature table gets the doc-40 transform."""

    def tr(n, v):
        if v is None:
            return None
        if n in log1p_names:
            return math.log1p(max(0.0, float(v)))
        return float(v)

    raw = [[tr(n, _as_float(r["features"].get(n))) for n in names] for r in rows]
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
            bool(missing_indicators) and 0.05 <= miss_rate[j] < 1.0 for j in range(p)
        ]
        filled = []
        for row in raw:
            cur = [med[j] if row[j] is None else row[j] for j in range(p)]
            cur += [
                1.0 if row[j] is None else 0.0 for j in range(p) if use_miss[j]
            ]
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
            "log1p_names": sorted(log1p_names),
        }
    else:
        med = stats["median"]
        use_miss = stats["use_miss"]
        filled = []
        for row in raw:
            cur = [med[j] if row[j] is None else row[j] for j in range(p)]
            cur += [
                1.0 if row[j] is None else 0.0 for j in range(p) if use_miss[j]
            ]
            filled.append(cur)
        mu = stats["mu"]
        sd = stats["sd"]
    X = [[(row[j] - mu[j]) / sd[j] for j in range(len(mu))] for row in filled]
    return X, stats


def _score_fold(rows, y, train_idx, test_idx, names, *, missing_indicators, log1p_names):
    Xtr, stats = design_matrix(
        [rows[i] for i in train_idx],
        names,
        missing_indicators=missing_indicators,
        log1p_names=log1p_names,
    )
    model = fit_logit(Xtr, [y[i] for i in train_idx], l2=LOGIT_L2, max_iter=LOGIT_MAX_ITER)
    Xte, _ = design_matrix(
        [rows[i] for i in test_idx],
        names,
        stats=stats,
        missing_indicators=missing_indicators,
        log1p_names=log1p_names,
    )
    return model, predict_logit(model, Xte)


def grouped_oof_scores(
    rows: list[dict],
    y: list[int],
    names: tuple[str, ...],
    fold_key: str,
    *,
    missing_indicators: bool = True,
    log1p_names: frozenset = LOG1P_FEATURES,
) -> dict:
    """Leave-one-group-out: every row is scored by a model fit on all
    rows outside its fold."""

    by_fold = defaultdict(list)
    for i, r in enumerate(rows):
        by_fold[r.get(fold_key) or "unknown"].append(i)
    oof = [None] * len(rows)
    fold_aurocs = {}
    n_undefined = 0
    for fold in sorted(by_fold):
        test_set = set(by_fold[fold])
        train_idx = [i for i in range(len(rows)) if i not in test_set]
        test_idx = by_fold[fold]
        model, scores = _score_fold(
            rows, y, train_idx, test_idx, names,
            missing_indicators=missing_indicators, log1p_names=log1p_names,
        )
        for i, s in zip(test_idx, scores):
            oof[i] = s
        a = auroc([y[i] for i in test_idx], scores)
        if a is None:
            n_undefined += 1
        else:
            fold_aurocs[fold] = a
    return {
        "oof": oof,
        "fold_aurocs": fold_aurocs,
        "n_folds": len(by_fold),
        "n_folds_undefined_auroc": n_undefined,
        "scheme": f"leave_one_{fold_key}_out",
    }


def stratified_kfold_oof(
    rows: list[dict],
    y: list[int],
    names: tuple[str, ...],
    *,
    k: int = OVERLAP_K_FOLD,
    seed: int = OVERLAP_SEED,
    missing_indicators: bool = True,
    log1p_names: frozenset = LOG1P_FEATURES,
) -> dict:
    """Seeded stratified k-fold OOF for populations with no group
    structure to hold out."""

    rng = random.Random(seed)
    pos = [i for i, t in enumerate(y) if t == 1]
    neg = [i for i, t in enumerate(y) if t == 0]
    rng.shuffle(pos)
    rng.shuffle(neg)
    k = max(2, min(k, len(pos) or 1, len(neg) or 1))
    folds = [[] for _ in range(k)]
    for j, i in enumerate(pos):
        folds[j % k].append(i)
    for j, i in enumerate(neg):
        folds[j % k].append(i)
    oof = [None] * len(rows)
    for test_idx in folds:
        test_set = set(test_idx)
        train_idx = [i for i in range(len(rows)) if i not in test_set]
        _model, scores = _score_fold(
            rows, y, train_idx, test_idx, names,
            missing_indicators=missing_indicators, log1p_names=log1p_names,
        )
        for i, s in zip(test_idx, scores):
            oof[i] = s
    return {"oof": oof, "n_folds": k, "scheme": f"stratified_{k}fold_seed_{seed}"}


# --- Evaluation -------------------------------------------------------------


def risk_tail(
    y: list[int], scores: list[float], fracs: tuple[float, ...] = RETAIN_FRACS
) -> list[dict]:
    """Kept rate in the lowest-risk tail. Score is p(kept); lowest risk
    is the top of the ranking. Doc 14 table shape."""

    n = len(y)
    order = sorted(range(n), key=lambda i: (scores[i], i), reverse=True)
    out = []
    for frac in list(fracs) + [1.0]:
        k = min(n, max(1, int(round(frac * n))))
        kept = order[:k]
        n_kept = sum(y[i] for i in kept)
        out.append(
            {
                "retain_frac": frac,
                "n_retained": k,
                "n_kept": n_kept,
                "kept_rate": n_kept / k if k else None,
            }
        )
    return out


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    i = p * (len(ys) - 1)
    lo = int(i)
    hi = min(lo + 1, len(ys) - 1)
    w = i - lo
    return ys[lo] * (1.0 - w) + ys[hi] * w


def within_group_eval(
    y: list[int],
    scores: list[float],
    groups: list,
    *,
    min_pos: int = WITHIN_MIN_POS,
    min_neg: int = WITHIN_MIN_NEG,
    n_reps: int = N_BOOT,
    seed: int = BOOT_SEED,
) -> dict:
    """Within-group AUROC of precomputed honest scores.

    Every comparison pair is restricted to one group, so group identity
    earns nothing. Reports per-group AUROC where both classes have at
    least min_pos/min_neg members, the positives-weighted mean of those
    AUROCs, the single concordance over all same-group pairs, and the
    exact decomposition of the pooled AUROC into within-group and
    cross-group pair concordance.
    """

    by_g = defaultdict(list)
    for i, g in enumerate(groups):
        by_g[g].append(i)
    per_group = []
    qualified = set()
    for g in sorted(by_g):
        idx = by_g[g]
        yg = [y[i] for i in idx]
        sg = [scores[i] for i in idx]
        n_pos = sum(yg)
        n_neg = len(yg) - n_pos
        qual = n_pos >= min_pos and n_neg >= min_neg
        entry = {
            "group": g,
            "n": len(idx),
            "n_pos": n_pos,
            "n_neg": n_neg,
            "n_pairs": n_pos * n_neg,
            "qualified": qual,
            "auroc": auroc(yg, sg),
            "ci95": None,
        }
        if qual:
            boot = bootstrap_auroc(yg, sg, n_reps=n_reps, seed=seed + sum(map(ord, g)))
            entry["ci95"] = boot["ci95"]
            qualified.add(g)
        per_group.append(entry)

    q_idx = [i for i, g in enumerate(groups) if g in qualified]
    yq = [y[i] for i in q_idx]
    sq = [scores[i] for i in q_idx]
    gq = [groups[i] for i in q_idx]

    rng = random.Random(seed)
    wboots, cboots, cboots_q = [], [], []
    for _ in range(n_reps):
        bidx = _stratified_boot_idx(gq, rng)
        w = _pos_weighted_mean_auroc(
            [yq[i] for i in bidx], [sq[i] for i in bidx], [gq[i] for i in bidx]
        )
        if w is not None:
            wboots.append(w)
        c = within_group_concordance(
            [yq[i] for i in bidx], [sq[i] for i in bidx], [gq[i] for i in bidx]
        )
        if c["value"] is not None:
            cboots_q.append(c["value"])
        aidx = _stratified_boot_idx(groups, rng)
        c = within_group_concordance(
            [y[i] for i in aidx], [scores[i] for i in aidx],
            [groups[i] for i in aidx],
        )
        if c["value"] is not None:
            cboots.append(c["value"])

    conc_all = within_group_concordance(y, scores, groups)
    conc_q = within_group_concordance(yq, sq, gq)
    n_pos_all = sum(y)
    n_pairs_total = n_pos_all * (len(y) - n_pos_all)
    pooled = auroc(y, scores)
    c_total = pooled * n_pairs_total if pooled is not None else None
    n_cross = n_pairs_total - conc_all["n_pairs"]
    c_cross = (
        c_total - conc_all["concordant_pair_equivalents"]
        if c_total is not None
        else None
    )
    return {
        "min_pos": min_pos,
        "min_neg": min_neg,
        "n_groups_qualified": len(qualified),
        "per_group": per_group,
        "positives_weighted_mean": {
            "value": _pos_weighted_mean_auroc(yq, sq, gq),
            "ci95": [_pct(wboots, 0.025), _pct(wboots, 0.975)],
            "n_bootstrap": n_reps,
        },
        "concordance_all_pairs": {
            **conc_all,
            "ci95": [_pct(cboots, 0.025), _pct(cboots, 0.975)],
        },
        "concordance_qualified_pairs": {
            **conc_q,
            "ci95": [_pct(cboots_q, 0.025), _pct(cboots_q, 0.975)],
        },
        "concordance_cross_pairs": {
            "value": (c_cross / n_cross) if n_cross else None,
            "n_pairs": n_cross,
            "concordant_pair_equivalents": c_cross,
            "pooled_auroc": pooled,
        },
    }


def eval_feature_set(
    rows: list[dict],
    y: list[int],
    names: tuple[str, ...],
    *,
    fold_key: str | None = "repository",
    group_key: str | None = "repository",
    seed: int = BOOT_SEED,
    missing_indicators: bool = True,
    log1p_names: frozenset = LOG1P_FEATURES,
) -> dict:
    """Grouped OOF + AUROC bootstrap + risk tail + within-group eval."""

    if fold_key is not None:
        res = grouped_oof_scores(
            rows, y, names, fold_key,
            missing_indicators=missing_indicators, log1p_names=log1p_names,
        )
    else:
        res = stratified_kfold_oof(
            rows, y, names,
            missing_indicators=missing_indicators, log1p_names=log1p_names,
        )
    scores = res["oof"]
    boot = bootstrap_auroc(y, scores, n_reps=N_BOOT, seed=seed)
    out = {
        "n": len(y),
        "n_pos": sum(y),
        "base_rate": sum(y) / len(y) if y else None,
        "features": list(names),
        "oof_scheme": res["scheme"],
        "n_folds": res["n_folds"],
        "auroc": boot["value"],
        "auroc_ci95": boot["ci95"],
        "fold_aurocs": res.get("fold_aurocs"),
        "risk_tail": risk_tail(y, scores),
        "oof_scores": [
            {"task_id": r["task_id"], "y": int(t), "score": s}
            for r, t, s in zip(rows, y, scores)
        ],
    }
    if group_key is not None:
        groups = [r.get(group_key) or "unknown" for r in rows]
        if len(set(groups)) > 1:
            out["within_group"] = within_group_eval(y, scores, groups, seed=seed)
            out["within_group_key"] = group_key
        else:
            out["within_group"] = None
            out["within_group_key"] = None
    return out


# --- Cross-population kept-set overlap --------------------------------------


def standardized_differences(
    rows_a: list[dict],
    rows_b: list[dict],
    names: tuple[str, ...],
    *,
    log1p_names: frozenset = LOG1P_FEATURES,
) -> dict:
    """Per-feature standardized mean difference on the model scale
    (log1p for the doc-40 count features), plus mean |d|."""

    per_feature = []
    for n in names:
        va = [
            math.log1p(max(0.0, _as_float(r["features"].get(n))))
            if n in log1p_names and _as_float(r["features"].get(n)) is not None
            else _as_float(r["features"].get(n))
            for r in rows_a
        ]
        vb = [
            math.log1p(max(0.0, _as_float(r["features"].get(n))))
            if n in log1p_names and _as_float(r["features"].get(n)) is not None
            else _as_float(r["features"].get(n))
            for r in rows_b
        ]
        va = [v for v in va if v is not None]
        vb = [v for v in vb if v is not None]
        if len(va) < 2 or len(vb) < 2:
            per_feature.append(
                {"feature": n, "d": None, "n_a": len(va), "n_b": len(vb)}
            )
            continue
        ma, mb = _mean(va), _mean(vb)
        ssa = _mean([(v - ma) ** 2 for v in va])
        ssb = _mean([(v - mb) ** 2 for v in vb])
        sd = math.sqrt((ssa + ssb) / 2.0)
        d = (ma - mb) / sd if sd > 1e-12 else (0.0 if abs(ma - mb) < 1e-12 else None)
        per_feature.append(
            {
                "feature": n,
                "d": d,
                "mean_a": ma,
                "mean_b": mb,
                "n_a": len(va),
                "n_b": len(vb),
            }
        )
    ds = [f["d"] for f in per_feature if f["d"] is not None]
    return {
        "per_feature": per_feature,
        "mean_abs_d": _mean([abs(d) for d in ds]) if ds else None,
    }


def pairwise_kept_overlap(
    kept_sets: dict[str, list[dict]],
    names: tuple[str, ...] = CURATED_FEATURES,
    *,
    k: int = OVERLAP_K_FOLD,
    seed: int = OVERLAP_SEED,
) -> dict:
    """Held-out separability of each pair of kept sets on the shared
    non-LLM footprint features. High AUROC = the kept sets occupy
    disjoint regions and a taste model does not transfer."""

    pops = sorted(kept_sets)
    pairs = {}
    for i, a in enumerate(pops):
        for b in pops[i + 1 :]:
            rows = kept_sets[a] + kept_sets[b]
            y = [1] * len(kept_sets[a]) + [0] * len(kept_sets[b])
            res = stratified_kfold_oof(
                rows, y, names, k=k, seed=seed, missing_indicators=False
            )
            boot = bootstrap_auroc(y, res["oof"], n_reps=N_BOOT, seed=seed)
            diff = standardized_differences(kept_sets[a], kept_sets[b], names)
            pairs[f"{a} vs {b}"] = {
                "positive_class": a,
                "n_a": len(kept_sets[a]),
                "n_b": len(kept_sets[b]),
                "oof_auroc": boot["value"],
                "ci95": boot["ci95"],
                "oof_scheme": res["scheme"],
                "mean_abs_std_diff": diff["mean_abs_d"],
                "per_feature_d": diff["per_feature"],
            }
    return {
        "features": list(names),
        "missing_indicators": False,
        "note": (
            "AUROC positive class = first population; the statistic is "
            "symmetric (1 - AUROC swaps the classes). Missingness flags "
            "off: they encode source layout, which is the class label."
        ),
        "pairs": pairs,
    }


# --- Population assemblies ---------------------------------------------------


def load_swe_eval_rows(v500: set[str]) -> tuple[list[dict], list[int]]:
    """Majority-valid annotated SWE rows; y = taste_kept."""

    feats = {r["task_id"]: r for r in load_jsonl(SWE_FEATURES_PATH)}
    raters = {r["task_id"]: r for r in load_jsonl(RATERS_PATH)}
    irt_items = {}
    if IRT_PATH.is_file():
        irt_items = {
            r["task_id"]: r
            for r in json.loads(IRT_PATH.read_text(encoding="utf-8"))["items"]
        }
    rows, y = [], []
    for tid in sorted(raters):
        r = raters[tid]
        if int(r.get("majority_invalid") or 0):
            continue
        f = feats.get(tid) or {}
        features = dict(f.get("features") or {})
        it = irt_items.get(tid) or {}
        features["irt_p_i"] = it.get("p_i")
        features["irt_a_i"] = it.get("a_i")
        features["irt_b_i"] = it.get("b_i")
        rows.append(
            {
                "task_id": tid,
                "repository": f.get("repository") or (tid.split("__")[0] if "__" in tid else "unknown"),
                "features": features,
            }
        )
        y.append(int(tid in v500))
    return rows, y


def load_tb21_eval_rows(footprint_rows: list[dict]) -> tuple[list[dict], dict]:
    """TB21 census pool with census verdict and maintenance flag."""

    census = {r["unit_id"]: bool(r["invalid"]) for r in load_jsonl(TB21_CENSUS_PATH)}
    maintained = {r["task_id"] for r in load_jsonl(TB21_MAINT_PATH)}
    rows = []
    for rec in footprint_rows:
        if rec["population"] != "tb21":
            continue
        tid = rec["task_id"]
        rows.append(
            {
                "task_id": tid,
                "repository": None,
                "features": rec["features"],
                "census_invalid": census.get(tid),
                "maintainer_repaired": tid in maintained,
            }
        )
    return rows, {"n_census": len(census), "n_maintained": len(maintained)}


def kept_sets_from_footprint(footprint_rows: list[dict]) -> dict[str, list[dict]]:
    """The shipped kept sets: what each population's humans kept."""

    out = defaultdict(list)
    for rec in footprint_rows:
        if rec["population"] in {"swe_verified", "tb21", "harbor_index", "swe_pro"}:
            out[rec["population"]].append(rec)
    return dict(out)


def _slim_eval(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "oof_scores"}


def run(gold: Path = GOLD) -> dict:
    v500_obj = write_verified500_ids()
    v500 = set(v500_obj["ids"])

    raters = {r["task_id"]: r for r in load_jsonl(RATERS_PATH)}
    feats = {r["task_id"]: r for r in load_jsonl(SWE_FEATURES_PATH)}
    repos = {t: (r.get("repository")) for t, r in feats.items()}
    label_rows = build_swe_taste_labels(raters, repos, v500)
    write_jsonl(TASTE_LABELS_PATH, label_rows)
    x2 = validity_membership_2x2(label_rows)

    swe_rows, swe_y = load_swe_eval_rows(v500)
    swe = {}
    for set_name, names in (
        ("cheap24", tuple(CHEAP_FEATURE_NAMES)),
        ("cheap24_plus_irt", tuple(CHEAP_FEATURE_NAMES) + IRT_FEATURES),
    ):
        swe[set_name] = eval_feature_set(
            swe_rows,
            swe_y,
            names,
            fold_key="repository",
            log1p_names=CHEAP_LOG1P,
        )
        print(
            f"[swe] {set_name} n={swe[set_name]['n']} pos={swe[set_name]['n_pos']} "
            f"auroc={swe[set_name]['auroc']:.4f} {swe[set_name]['auroc_ci95']}",
            flush=True,
        )

    footprint_rows = load_jsonl(FOOTPRINT_PATH)
    tb_rows, tb_meta = load_tb21_eval_rows(footprint_rows)
    tb_valid = [r for r in tb_rows if r["census_invalid"] is False]
    tb_y = [int(r["maintainer_repaired"]) for r in tb_valid]
    tb_eval = eval_feature_set(
        tb_valid,
        tb_y,
        CURATED_FEATURES,
        fold_key=None,
    )
    tb21 = {
        "n_census": tb_meta["n_census"],
        "n_census_invalid": sum(1 for r in tb_rows if r["census_invalid"]),
        "n_valid": len(tb_valid),
        "n_kept": sum(tb_y),
        "label": "maintainer_repaired (the 28-list) given census-valid",
        "label_protocol": TB21_TASTE_PROTOCOL,
        "census_protocol": TB21_CENSUS_PROTOCOL,
        "powered": "marginal: 26 positives, 58 negatives; fit reported but wide",
        "eval_curated_features": _slim_eval(tb_eval),
    }
    print(
        f"[tb21] n={len(tb_valid)} pos={sum(tb_y)} "
        f"auroc={tb_eval['auroc']}",
        flush=True,
    )

    kept = kept_sets_from_footprint(footprint_rows)
    overlap = pairwise_kept_overlap(kept)
    print(
        "[overlap] " + "; ".join(
            f"{k}={v['oof_auroc']:.3f}" for k, v in overlap["pairs"].items()
        ),
        flush=True,
    )

    report = {
        "meta": {
            "date": "2026-09-14",
            "task": "TASK 24: taste conditional on validity",
            "model_class": (
                "doc 40: median imputation, missingness indicators, "
                "standardized design matrix, class-weighted L2 logistic "
                "(fit_logit, footprint.py)"
            ),
            "external_labels_eval_only": True,
            "no_model_in_bound": True,
            "n_boot": N_BOOT,
            "bootstrap_seed": BOOT_SEED,
        },
        "artifacts": {
            "verified500_ids": str(VERIFIED500_IDS_PATH),
            "taste_labels": str(TASTE_LABELS_PATH),
        },
        "swe": {
            "n_annotated": len(label_rows),
            "validity_x_verified500": x2,
            "population": {
                "n_valid_majority": x2["majority_invalid"]["n_valid"],
                "n_kept": x2["majority_invalid"]["valid_kept"],
                "kept_base_rate": x2["majority_invalid"]["p_kept_given_valid"],
            },
            "evals": {k: _slim_eval(v) for k, v in swe.items()},
            "oof_paths": {},
        },
        "tb21": tb21,
        "harbor_funnel": _harbor_summary(),
        "overlap": overlap,
    }
    oof_dir = gold / "conditional_taste_oof"
    oof_dir.mkdir(parents=True, exist_ok=True)
    for set_name, e in swe.items():
        p = oof_dir / f"swe_{set_name}.oof.jsonl"
        write_jsonl(p, e["oof_scores"])
        report["swe"]["oof_paths"][set_name] = str(p)
    p = oof_dir / "tb21_curated.oof.jsonl"
    write_jsonl(p, tb_eval["oof_scores"])
    tb21["oof_path"] = str(p)
    write_json(EVAL_PATH, report)
    return report


def _harbor_summary() -> dict:
    out = {
        "label": "survived_2_to_4",
        "label_protocol": "harbor_index_funnel.reconstructed.2026-09-13",
        "validity_conditioning": (
            "stage-1 survival is a difficulty screen (frontier solve rate "
            "<= 33%), not a validity label; no validity signal exists "
            "inside the 1,331 survivors (doc 52, doc 54)"
        ),
        "derived_label_caveat": (
            "survived_2_to_4 is the published 82-task list conditioned on "
            "the reconstructed stage-1 pass (grade A conditioned on grade "
            "B); 14 matched survivors do not pass the reconstruction "
            "(doc 52)"
        ),
    }
    if FUNNEL_EVAL_PATH.is_file():
        t = json.loads(FUNNEL_EVAL_PATH.read_text(encoding="utf-8"))
        e = t["evals"]["survived_2_to_4"]
        out["evals"] = {
            "n": e["A"]["lobo"]["n"],
            "n_pos": e["A"]["lobo"]["n_pos"],
            "lobo_auroc_A": e["A"]["lobo"]["lobo_auroc"],
            "lobo_ci95_A": e["A"]["lobo"]["lobo_ci95"],
            "lofo_auroc_A": e["A"]["lofo"]["lobo_auroc"],
            "lofo_ci95_A": e["A"]["lofo"]["lobo_ci95"],
            "pooled_auroc_A": e["A"]["lobo"]["pooled_auroc"],
            "source": str(FUNNEL_EVAL_PATH),
        }
    if FUNNEL_WITHIN_PATH.is_file():
        w = json.loads(FUNNEL_WITHIN_PATH.read_text(encoding="utf-8"))
        p = w["pooled_trained_within_evaluated"]["A"]
        out["within_benchmark"] = {
            "concordance_all_pairs": p["concordance_all_pairs"]["value"],
            "ci95": p["concordance_all_pairs"]["ci95"],
            "n_pairs": p["concordance_all_pairs"]["n_pairs"],
            "positives_weighted_mean": p["positives_weighted_mean"]["value"],
            "positives_weighted_mean_ci95": p["positives_weighted_mean"]["ci95"],
            "n_benchmarks": w["population"]["n_benchmarks"],
            "max_kept_per_benchmark": w["population"]["max_kept"],
            "source": str(FUNNEL_WITHIN_PATH),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Taste conditional on validity (doc 59)")
    p.add_argument("--gold", type=Path, default=GOLD)
    args = p.parse_args(argv)
    report = run(gold=args.gold)
    slim = dict(report)
    print(json.dumps({"swe": report["swe"]["population"], "eval": str(EVAL_PATH)}, indent=1))
    _ = slim
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
