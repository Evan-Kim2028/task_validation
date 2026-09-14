"""Reference distributions as a generation target (doc 62).

A taste model needs labels from its own population, so it fails on a
fresh pool (doc 59). The usable inversion is descriptive: describe what
a population's curators kept, in feature space, and treat that
description as a target a generator aims at rather than a filter that
scores tasks.

A reference target is, for a kept set on a recorded feature subset:

- per-feature median and interquartile range on the raw scale,
- the share of kept tasks inside the feature's middle 80 percent
  (10th to 90th percentile), which exposes degenerate features,
- a standardized centroid and a correlation matrix shrunk toward the
  identity with an eigenvalue floor (the doc-60 region fit), which
  together give a mask-marginalized Mahalanobis distance to the kept
  center.

References are fit for three kept sets: SWE-bench Verified (n = 500,
artifact plus content features), Terminal-Bench 2.1 (n = 26,
validity-conditioned maintainer repairs, shared statics), and
Harbor-Index (n = 82, statics plus behaviour features).

The validation asks whether the target means anything: fit on 400 of
the 500 kept SWE tasks under a fixed seed, then check whether distance
to the reference ranks the held-out 100 kept above the 435 valid
rejected tasks, reported as AUROC with a bootstrap interval over 20
split seeds. Cross-population, each reference scores another
population's kept against its rejected on the shared features.

Every distance is computed on the task's observed features intersected
with the reference subset (marginalized Mahalanobis); a feature a
population never observes contributes nothing rather than being imputed.
External labels (taste_kept, maintainer repair, the published
Harbor-Index list) define the kept sets and remain eval-only (doc 43).
No label is imputed. Nothing here enters a bound; a target shapes
generation, it never gates acceptance.

Run: ``python -m task_validation.evidence.reference_target run``.
Outputs: ``data/gold/reference_targets.json``,
``data/gold/reference_target_eval.json``,
``data/gold/lot001_gap_report.json``.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

from task_validation.evidence.content_features import (
    CONTENT_FEATURE_NAMES,
    CONTENT_LOG1P,
    lot001_content_rows,
    swe_content_rows,
)
from task_validation.evidence.decontam import harbor_fields
from task_validation.evidence.footprint import (
    FEATURE_NAMES as FOOTPRINT_FEATURE_NAMES,
    load_jsonl,
    write_json,
)
from task_validation.evidence.irt import auroc, bootstrap_auroc
from task_validation.evidence.typicality import (
    LOG1P_FEATURES as TYP_LOG1P,
    MIN_KEPT_OBS,
    EVAL_TASKS_ROOT,
    harbor_behavior_by_pair,
    fit_region,
    lot001_rows,
    mahalanobis,
    population_mask,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD = REPO_ROOT / "data" / "gold"

TASTE_LABELS_PATH = GOLD / "swe_taste_labels.jsonl"
SWE_FEATURES_PATH = GOLD / "swe_verified_features.jsonl"
FOOTPRINT_PATH = GOLD / "footprint.jsonl"
TB21_CENSUS_PATH = GOLD / "tb21_census_verdicts.jsonl"
TB21_MAINT_PATH = GOLD / "tb21_maintenance.jsonl"
FUNNEL_LABELS_PATH = GOLD / "harbor_funnel_labels.jsonl"
STRATA_PATH = GOLD / "harbor_index_strata.json"

LOT001_ROOT = EVAL_TASKS_ROOT / "lots" / "lot-001"

OUT_TARGETS = GOLD / "reference_targets.json"
OUT_EVAL = GOLD / "reference_target_eval.json"
OUT_GAP = GOLD / "lot001_gap_report.json"

PROTOCOL = "reference_target.2026-09-14"
BOOT_SEED = 20260914
N_BOOT = 400
N_SPLIT_SEEDS = 20
KEPT_FIT_N = 400
# A feature enters a population's scoring mask when at least this share
# of the population's tasks observe it (typicality.py convention).
MASK_COVER_MIN = 0.5
# A lot feature enters the per-feature gap table when at least this many
# lot tasks observe it.
LOT_MIN_OBS = 10

# Model-scale transform: log1p on the heavy-tailed count features, the
# union of the typicality set and the content-feature set.
REFERENCE_LOG1P = frozenset(set(TYP_LOG1P) | set(CONTENT_LOG1P))

# The doc-59 cheap artifact features canonicalized onto footprint names
# so one feature space serves SWE, TB 2.1, Harbor-Index and lot-001.
# patch_n_changed_lines stays a line count (footprint's solution_size is
# a byte count for directory tasks, so that alias is not used), and
# test_n_files maps to test_file_count, the shared "number of test
# files" semantic. The three cheap-only names carry over unchanged.
CHEAP_TO_CANON = {
    "stmt_chars": "instruction_chars",
    "stmt_lines": "instruction_lines",
    "stmt_n_identifiers": "stmt_n_identifiers",
    "test_n_files": "test_file_count",
    "patch_n_changed_lines": "patch_n_changed_lines",
    "test_stmt_id_overlap": "test_stmt_id_overlap",
    "test_only_id_frac": "test_only_id_frac",
    "n_fail_to_pass": "n_fail_to_pass",
    "n_pass_to_pass": "n_pass_to_pass",
    "patch_n_files": "patch_n_files",
    "patch_n_hunks": "patch_n_hunks",
    "test_n_hunks": "test_n_hunks",
    "test_n_changed_lines": "test_n_changed_lines",
    "has_code_fence": "has_code_fence",
    "has_traceback": "has_traceback",
    "has_http_url": "has_http_url",
    "has_reproduction_hint": "has_reproduction_hint",
    "hints_chars": "hints_chars",
    "gold_to_test_line_ratio": "gold_to_test_line_ratio",
    "f2p_in_statement_frac": "f2p_in_statement_frac",
    "test_has_exact_string_literal": "test_has_exact_string_literal",
    "test_has_warning_assert": "test_has_warning_assert",
    "test_has_match_kw": "test_has_match_kw",
    "gold_mentions_deprecation": "gold_mentions_deprecation",
}
ARTIFACT_FEATURES = tuple(dict.fromkeys(CHEAP_TO_CANON.values()))

# Statics that exist on both sides of the SWE / TB 2.1 boundary.
# solution_size is excluded by construction: it is patch lines for SWE
# but solution bytes for directory tasks.
SWE_TB21_SHARED = (
    "instruction_chars",
    "instruction_lines",
    "stmt_n_identifiers",
    "test_file_count",
    "test_stmt_id_overlap",
    "test_only_id_frac",
    "has_code_fence",
    "has_traceback",
    "has_http_url",
    "has_reproduction_hint",
    "hints_chars",
)

# Doc-40 statics plus the doc-52/54 behaviour block carried by the
# Harbor-Index kept set (typicality.ALL_FEATURES).
_EXEC_GATES = ("reference_pass", "nop_reject", "determinism", "environment_failure")
_STATIC_FEATURES = tuple(
    f for f in FOOTPRINT_FEATURE_NAMES if f not in _EXEC_GATES and f != "solve_rate_band"
)


def _np():
    import numpy as np

    return np


def _transform(name: str, value) -> float | None:
    if isinstance(value, bool):
        value = 1.0 if value else 0.0
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    if name in REFERENCE_LOG1P:
        if x < 0:
            return None
        return math.log1p(x)
    return x


def _model_features(raw: dict) -> dict:
    return {f: _transform(f, v) for f, v in raw.items()}


def _row(task_id: str, raw: dict, **meta) -> dict:
    return {"task_id": task_id, "raw": dict(raw), "features": _model_features(raw), **meta}


def _split_seed(i: int) -> int:
    digest = hashlib.sha256(f"reference-target-split:{i}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


# ---------------------------------------------------------------------------
# Population assembly (raw feature dicts; model scale is derived)
# ---------------------------------------------------------------------------


def swe_rows() -> dict[str, list[dict]]:
    """935 majority-valid annotated rows split by taste_kept:
    500 kept (Verified-500), 435 rejected. Features = canonicalized
    artifact 24 + content 19."""
    content = {r["task_id"]: r["features"] for r in swe_content_rows()}
    cheap = {r["task_id"]: (r.get("features") or {}) for r in load_jsonl(SWE_FEATURES_PATH)}
    kept, rejected = [], []
    for lab in load_jsonl(TASTE_LABELS_PATH):
        v = (lab.get("taste_kept") or {}).get("value")
        if v is None:
            continue
        tid = lab["task_id"]
        raw = {}
        for src, dst in CHEAP_TO_CANON.items():
            raw[dst] = (cheap.get(tid) or {}).get(src)
        raw.update(content.get(tid) or {})
        row = _row(tid, raw, repository=lab.get("repository"))
        (kept if v else rejected).append(row)
    return {"kept": kept, "rejected": rejected}


def tb21_rows() -> dict[str, list[dict]]:
    """TB 2.1 census-valid rows split by the maintainer-repair list:
    26 kept, 58 rejected. Features = the statics the footprint carries."""
    census = {r["unit_id"]: bool(r["invalid"]) for r in load_jsonl(TB21_CENSUS_PATH)}
    maintained = {r["task_id"] for r in load_jsonl(TB21_MAINT_PATH)}
    kept, rejected = [], []
    for rec in load_jsonl(FOOTPRINT_PATH):
        if rec.get("population") != "tb21":
            continue
        tid = rec["task_id"]
        if census.get(tid) is not False:
            continue
        raw = {f: (rec.get("features") or {}).get(f) for f in _STATIC_FEATURES}
        row = _row(tid, raw)
        (kept if tid in maintained else rejected).append(row)
    return {"kept": kept, "rejected": rejected}


def harbor_kept_rows() -> list[dict]:
    """The 82 published Harbor-Index tasks: footprint statics plus the
    doc-52/54 behaviour block, joined through the funnel labels."""
    labels = load_jsonl(FUNNEL_LABELS_PATH)
    behavior = harbor_behavior_by_pair()
    strata = json.loads(STRATA_PATH.read_text())
    kept_ids = set()
    for ids in strata["ids_by_stratum"].values():
        kept_ids |= set(ids)
    by_index = {r.get("index_task_id"): r for r in labels if r.get("index_task_id")}
    kept = []
    for rec in load_jsonl(FOOTPRINT_PATH):
        if rec.get("population") != "harbor_index":
            continue
        tid = rec["task_id"]
        if tid not in kept_ids:
            continue
        raw = {f: (rec.get("features") or {}).get(f) for f in _STATIC_FEATURES}
        for g in _EXEC_GATES:
            raw[g] = (rec.get("features") or {}).get(g)
        lab = by_index.get(tid)
        benchmark = "dacode"
        if lab is not None:
            benchmark = lab["benchmark"]
            raw.update(behavior.get((lab["benchmark"], lab["task_name"])) or {})
        kept.append(_row(tid, raw, benchmark=benchmark))
    return kept


def _untransform(name: str, v: float | None) -> float | None:
    """Invert the model-scale transform on doc-60 lot rows. Only the
    layout-static block was transformed there; gate-C fields are raw."""
    if v is None:
        return None
    if name in TYP_LOG1P and name in FOOTPRINT_FEATURE_NAMES:
        return float(math.expm1(v))
    return v


def lot001_rows_raw(lot_root: Path = LOT001_ROOT) -> list[dict]:
    """The 20 lot tasks: doc-60 features inverted to the raw scale, plus
    the content-19 and the three cheap-only artifact fields derivable
    from the task text."""
    rows, _meta = lot001_rows(lot_root)
    content = {r["task_id"]: r["features"] for r in lot001_content_rows(lot_root)}
    out = []
    for r in rows:
        tid = r["task_id"]
        raw = {f: _untransform(f, v) for f, v in (r.get("features") or {}).items()}
        raw.update(content.get(tid) or {})
        f = harbor_fields(lot_root / "tasks" / tid)
        tests_text = f.get("tests") or ""
        sol_text = f.get("solution") or ""
        raw.setdefault(
            "test_has_warning_assert",
            1.0
            if any(w in tests_text for w in ("DeprecationWarning", "FutureWarning", "pytest.warns"))
            else 0.0,
        )
        raw.setdefault("test_has_match_kw", 1.0 if "match=" in tests_text else 0.0)
        raw.setdefault(
            "gold_mentions_deprecation",
            1.0 if "deprecat" in sol_text.lower() else 0.0,
        )
        out.append(_row(tid, raw, benchmark="lot-001"))
    return out


# ---------------------------------------------------------------------------
# Reference fit and distance
# ---------------------------------------------------------------------------


def _feature_stats(rows: list[dict], features: tuple[str, ...]) -> dict:
    """Raw-scale robust stats plus model-scale mean/sd per feature."""
    np = _np()
    stats = {}
    for f in features:
        raw_vals = np.array(
            [r["raw"].get(f) for r in rows if r["raw"].get(f) is not None],
            dtype=float,
        )
        mod_vals = np.array(
            [r["features"].get(f) for r in rows if r["features"].get(f) is not None],
            dtype=float,
        )
        n = int(len(raw_vals))
        if n == 0:
            stats[f] = {"n": 0, "in_universe": False}
            continue
        q10, q25, q50, q75, q90 = np.quantile(raw_vals, [0.1, 0.25, 0.5, 0.75, 0.9])
        mid80 = float(((raw_vals >= q10) & (raw_vals <= q90)).mean())
        sd_model = float(mod_vals.std(ddof=1)) if len(mod_vals) > 1 else 0.0
        stats[f] = {
            "n": n,
            "median": float(q50),
            "q10": float(q10),
            "q25": float(q25),
            "q75": float(q75),
            "q90": float(q90),
            "iqr": float(q75 - q25),
            "mid80_share": mid80,
            "mean_model": float(mod_vals.mean()),
            "sd_model": sd_model,
            "in_universe": n >= MIN_KEPT_OBS and sd_model > 0,
        }
    return stats


def fit_reference(rows: list[dict], features: tuple[str, ...]) -> dict:
    """Describe a kept set on a feature subset: robust raw-scale stats,
    the in-universe subset, and the doc-60 shrunk-covariance fit on the
    model scale."""
    stats = _feature_stats(rows, features)
    universe = tuple(f for f in features if stats[f].get("in_universe"))
    model_rows = [{"task_id": r["task_id"], "features": r["features"]} for r in rows]
    fit = fit_region(model_rows, universe)
    return {
        "n": len(rows),
        "features": list(features),
        "universe": list(universe),
        "stats": stats,
        "fit": fit,
    }


def distance(feat_vec_model: dict, ref: dict, dims: tuple[str, ...] | None = None):
    """Mahalanobis distance to the kept centroid on dims ∩ observed."""
    return mahalanobis(feat_vec_model, ref["fit"], dims)


def _neg_d(row: dict, ref: dict, dims) -> float | None:
    d, _p = distance(row["features"], ref, dims)
    return -d if d is not None else None


def auroc_kept_over_rejected(kept_rows, rejected_rows, ref, dims) -> dict:
    """AUROC of proximity (negative distance) separating kept from
    rejected, with a 400-replicate bootstrap interval."""
    kept_s = [_neg_d(r, ref, dims) for r in kept_rows]
    rej_s = [_neg_d(r, ref, dims) for r in rejected_rows]
    y = [1] * len(kept_s) + [0] * len(rej_s)
    s = kept_s + rej_s
    defined = [(yy, ss) for yy, ss in zip(y, s) if ss is not None]
    y2 = [yy for yy, _ in defined]
    s2 = [ss for _, ss in defined]
    boot = bootstrap_auroc(y2, s2, n_reps=N_BOOT, seed=BOOT_SEED)
    return {
        "auroc": boot["value"],
        "ci95": boot["ci95"],
        "n_boot": N_BOOT,
        "n_kept_scored": sum(1 for x in kept_s if x is not None),
        "n_rejected_scored": sum(1 for x in rej_s if x is not None),
        "dims": list(dims),
    }


# ---------------------------------------------------------------------------
# (3) Validation on SWE-bench
# ---------------------------------------------------------------------------


def swe_validation(swe: dict, n_seeds: int = N_SPLIT_SEEDS) -> dict:
    """Fit on a random 400 of the 500 kept, then ask whether distance to
    the reference ranks the held-out 100 kept above the 435 rejected."""
    kept = swe["kept"]
    rejected = swe["rejected"]
    feature_sets = {
        "artifact": ARTIFACT_FEATURES,
        "content": tuple(CONTENT_FEATURE_NAMES),
        "both": ARTIFACT_FEATURES + tuple(CONTENT_FEATURE_NAMES),
    }
    per_seed = []
    for i in range(n_seeds):
        rng = random.Random(_split_seed(i))
        fit_rows = rng.sample(kept, KEPT_FIT_N)
        fit_ids = {r["task_id"] for r in fit_rows}
        held = [r for r in kept if r["task_id"] not in fit_ids]
        seed_res = {"seed_index": i, "seed": _split_seed(i), "n_fit": len(fit_rows)}
        for name, feats in feature_sets.items():
            ref = fit_reference(fit_rows, feats)
            res = auroc_kept_over_rejected(held, rejected, ref, tuple(ref["universe"]))
            res["n_held_kept"] = len(held)
            res["n_universe"] = len(ref["universe"])
            seed_res[name] = res
        per_seed.append(seed_res)
    mean_auroc = {
        name: sum(s[name]["auroc"] for s in per_seed if s[name]["auroc"] is not None)
        / max(1, sum(1 for s in per_seed if s[name]["auroc"] is not None))
        for name in feature_sets
    }
    range_auroc = {
        name: [
            min(s[name]["auroc"] for s in per_seed),
            max(s[name]["auroc"] for s in per_seed),
        ]
        for name in feature_sets
    }
    return {
        "design": {
            "kept_fit_n": KEPT_FIT_N,
            "n_seeds": n_seeds,
            "n_held_kept": len(kept) - KEPT_FIT_N,
            "n_rejected": len(rejected),
            "primary_seed": _split_seed(0),
            "boot_reps": N_BOOT,
            "boot_seed": BOOT_SEED,
        },
        "per_seed": per_seed,
        "mean_auroc": mean_auroc,
        "range_auroc": range_auroc,
    }


# ---------------------------------------------------------------------------
# (4) Gap report for lot-001
# ---------------------------------------------------------------------------


def gap_report(lot_rows: list[dict], references: dict) -> dict:
    """Per reference: distances for the 20 lot tasks plus a per-feature
    table of lot median vs reference median/IQR, an IQR-standardized
    difference, and a direction word. Descriptive only."""
    np = _np()
    out = {"n_lot": len(lot_rows), "references": {}}
    for ref_name, ref in references.items():
        universe = tuple(ref["universe"])
        mask = population_mask(lot_rows, universe)
        dims = tuple(f for f in mask)
        dists = []
        for r in lot_rows:
            d, p = distance(r["features"], ref, dims)
            dists.append({"task_id": r["task_id"], "d": d, "p_dims": p})
        per_feature = []
        for f in universe:
            vals = [r["raw"].get(f) for r in lot_rows]
            vals = [v for v in vals if v is not None]
            st = ref["stats"].get(f) or {}
            entry = {
                "feature": f,
                "n_lot_obs": len(vals),
                "lot_median": float(np.median(vals)) if vals else None,
                "ref_median": st.get("median"),
                "ref_iqr": st.get("iqr"),
                "ref_q25": st.get("q25"),
                "ref_q75": st.get("q75"),
                "ref_mid80_share": st.get("mid80_share"),
            }
            if len(vals) >= LOT_MIN_OBS and st.get("iqr") is not None:
                lot_med = float(np.median(vals))
                if st["iqr"] > 0:
                    entry["std_diff_iqr"] = (lot_med - st["median"]) / st["iqr"]
                else:
                    entry["std_diff_iqr"] = None
                if st["q25"] <= lot_med <= st["q75"]:
                    entry["direction"] = "inside"
                elif lot_med > st["q75"]:
                    entry["direction"] = "above"
                else:
                    entry["direction"] = "below"
            else:
                entry["std_diff_iqr"] = None
                entry["direction"] = "unscored"
            per_feature.append(entry)
        ranked = sorted(
            (e for e in per_feature if e["std_diff_iqr"] is not None),
            key=lambda e: -abs(e["std_diff_iqr"]),
        )
        out["references"][ref_name] = {
            "n_ref": ref["n"],
            "dims_used": list(dims),
            "n_dims": len(dims),
            "distances": dists,
            "d_summary": {
                "median": float(np.median([x["d"] for x in dists if x["d"] is not None]))
                if any(x["d"] is not None for x in dists)
                else None,
                "min": min((x["d"] for x in dists if x["d"] is not None), default=None),
                "max": max((x["d"] for x in dists if x["d"] is not None), default=None),
            },
            "per_feature": per_feature,
            "top10_abs_diff": [e["feature"] for e in ranked[:10]],
            "ranked": [
                {k: e[k] for k in ("feature", "lot_median", "ref_median", "ref_iqr", "std_diff_iqr", "direction")}
                for e in ranked
            ],
        }
    return out


# ---------------------------------------------------------------------------
# (5) Cross-population check
# ---------------------------------------------------------------------------


def cross_population(
    swe: dict, tb21: dict, swe_ref: dict, tb21_ref: dict, harbor_ref: dict
) -> dict:
    """Does a reference built on one population rank another
    population's kept above its rejected? Scored on the features both
    sides share."""
    out = {}
    # SWE reference -> TB21 kept/rejected, on the shared statics.
    shared_swe = tuple(f for f in SWE_TB21_SHARED if f in swe_ref["universe"])
    res = auroc_kept_over_rejected(tb21["kept"], tb21["rejected"], swe_ref, shared_swe)
    out["swe_ref_on_tb21"] = res
    # TB21 reference -> SWE kept/rejected, on the shared statics the
    # tb21 kept set informs.
    shared_tb = tuple(f for f in SWE_TB21_SHARED if f in tb21_ref["universe"])
    res = auroc_kept_over_rejected(swe["kept"], swe["rejected"], tb21_ref, shared_tb)
    out["tb21_ref_on_swe"] = res
    # Harbor-Index reference -> SWE and TB21 kept/rejected, on the
    # statics each scored population observes.
    for pop_name, pop in (("swe", swe), ("tb21", tb21)):
        dims = tuple(
            f
            for f in population_mask(pop["kept"] + pop["rejected"], tuple(harbor_ref["universe"]))
            if f in harbor_ref["universe"]
        )
        out[f"harbor_ref_on_{pop_name}"] = auroc_kept_over_rejected(
            pop["kept"], pop["rejected"], harbor_ref, dims
        )
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def run() -> dict:
    swe = swe_rows()
    tb21 = tb21_rows()
    harbor_kept = harbor_kept_rows()
    lot = lot001_rows_raw()

    swe_ref = fit_reference(swe["kept"], ARTIFACT_FEATURES + tuple(CONTENT_FEATURE_NAMES))
    tb21_ref = fit_reference(tb21["kept"], _STATIC_FEATURES)
    harbor_ref = fit_reference(harbor_kept, tuple(sorted({f for r in harbor_kept for f in r["raw"]})))

    validation = swe_validation(swe)

    references = {
        "swe_verified_kept": swe_ref,
        "tb21_kept": tb21_ref,
        "harbor_index_kept": harbor_ref,
    }
    gap = gap_report(lot, references)
    cross = cross_population(swe, tb21, swe_ref, tb21_ref, harbor_ref)

    targets = {
        "protocol": PROTOCOL,
        "code": "src/task_validation/evidence/reference_target.py",
        "references": {
            name: {
                "n": ref["n"],
                "feature_subset": ref["features"],
                "universe": ref["universe"],
                "shrinkage_alpha": ref["fit"]["alpha"],
                "per_feature": {
                    f: {k: v for k, v in st.items() if k != "in_universe"}
                    for f, st in ref["stats"].items()
                },
            }
            for name, ref in references.items()
        },
        "inputs": {
            "taste_labels": str(TASTE_LABELS_PATH),
            "swe_features": str(SWE_FEATURES_PATH),
            "footprint": str(FOOTPRINT_PATH),
            "tb21_census": str(TB21_CENSUS_PATH),
            "tb21_maintenance": str(TB21_MAINT_PATH),
            "strata": str(STRATA_PATH),
        },
    }
    write_json(OUT_TARGETS, targets)

    eval_doc = {
        "protocol": PROTOCOL,
        "external_labels_eval_only": True,
        "no_model_in_bound": True,
        "validation_swe": validation,
        "cross_population": cross,
    }
    write_json(OUT_EVAL, eval_doc)

    gap_doc = {
        "protocol": PROTOCOL,
        "n_lot": gap["n_lot"],
        "lot_root": str(LOT001_ROOT),
        "references": gap["references"],
        "framing": "distance description only; no quality judgement, no gate, no bound",
    }
    write_json(OUT_GAP, gap_doc)
    return {"targets": targets, "eval": eval_doc, "gap": gap_doc}


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "run":
        out = run()
        val = out["eval"]["validation_swe"]
        for name, m in val["mean_auroc"].items():
            r = val["range_auroc"][name]
            s0 = val["per_seed"][0][name]
            print(
                f"[swe] {name}: mean={m:.3f} range={r[0]:.3f}-{r[1]:.3f} "
                f"seed0={s0['auroc']:.3f} ci={s0['ci95']}"
            )
        for name, res in out["eval"]["cross_population"].items():
            print(f"[xpop] {name}: auroc={res['auroc']}")
    else:
        print("usage: python -m task_validation.evidence.reference_target run")


if __name__ == "__main__":
    main()
