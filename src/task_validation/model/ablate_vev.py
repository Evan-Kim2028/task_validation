"""Ablate untrained VEV primitives vs current static proxies.

No new fitted model. Ranking scores are either existing OOF probabilities
or direct invariant values (spec_gap).
"""

from __future__ import annotations

import json
from pathlib import Path

from task_validation.evidence.spec_atoms import spec_from_record
from task_validation.evidence.vev import vev_from_spec
from task_validation.model.metrics import auroc
from task_validation.model.risk_coverage import retain_curve


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
    return rows


def ablate(
    *,
    features_path: Path,
    oof_path: Path,
    parquet_path: Path,
    y_key: str = "y",
) -> dict:
    import pandas as pd

    feats = {r["task_id"]: r for r in _load_jsonl(features_path)}
    oof = {r["task_id"]: r for r in _load_jsonl(oof_path)}
    df = pd.read_parquet(parquet_path)
    y = []
    score_a = []
    score_b = []
    ids = []
    n_spec_fail = 0
    for _, rec in df.iterrows():
        tid = rec["instance_id"]
        if tid not in feats or tid not in oof:
            continue
        d = rec.to_dict()
        spec = spec_from_record(d)
        vev = vev_from_spec(tid, spec)
        if vev.primitives["specification_sufficiency"].status == "fail":
            n_spec_fail += 1
        ids.append(tid)
        y.append(int(oof[tid]["y"] if y_key == "y" else feats[tid].get(y_key, oof[tid]["y"])))
        # A: current fitted proxy (higher p = more invalid)
        score_a.append(float(oof[tid]["p_logistic"]))
        # B: untrained spec gap (higher = more ungrounded test atoms)
        score_b.append(float(spec.get("spec_gap_contract", spec["spec_gap"])))
    # C would add execution; not available on this population.
    def pack(name, scores):
        return {
            "name": name,
            "auroc": auroc(y, scores),
            "retain_curve": retain_curve(y, scores),
            "note": "retain_curve sorts *ascending* (low score kept). For A, low p_logistic is kept; we invert A so high-invalid ranks last.",
        }

    # retain_curve keeps LOW scores. For A, low p means predicted valid — correct.
    # For B, low spec_gap means better alignment — correct.
    return {
        "n": len(y),
        "base_rate": sum(y) / len(y) if y else None,
        "n_spec_sufficiency_fail": n_spec_fail,
        "A_current_oof_logistic": pack("A", score_a),
        "B_spec_gap_untrained": pack("B", score_b),
        "primary_metric": "residual_invalid at retain 5% and 20%",
        "trained_model_used_for_B": False,
    }
