"""Ablate causal-consistency assays vs proxy model. No new fit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from task_validation.evidence.causality import change_causality
from task_validation.evidence.discrimination import discrimination_profile
from task_validation.evidence.provenance import contract_provenance
from task_validation.model.metrics import auroc
from task_validation.model.risk_coverage import retain_curve


def _rng_key(tid: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{tid}".encode()).hexdigest()


def stratified_sample(oof: list[dict], n: int, salt: str = "causal-150") -> list[dict]:
    valid = [r for r in oof if int(r["y"]) == 0]
    invalid = [r for r in oof if int(r["y"]) == 1]
    n_v = max(1, int(round(n * len(valid) / max(len(oof), 1))))
    n_i = n - n_v
    valid.sort(key=lambda r: _rng_key(r["task_id"], salt))
    invalid.sort(key=lambda r: _rng_key(r["task_id"], salt))
    return valid[:n_v] + invalid[:n_i]


def ablate_causal(parquet_path: Path, oof_path: Path, n: int = 150) -> dict:
    import pandas as pd

    oof = [json.loads(l) for l in oof_path.open(encoding="utf-8")]
    sample = stratified_sample(oof, n)
    want = {r["task_id"]: r for r in sample}
    df = pd.read_parquet(parquet_path)
    y, a, b, c, d, e = [], [], [], [], [], []
    profiles = []
    for _, rec in df.iterrows():
        tid = rec["instance_id"]
        if tid not in want:
            continue
        row = rec.to_dict()
        caus = change_causality(row)
        prov = contract_provenance(row)
        disc = discrimination_profile(row)
        yy = int(want[tid]["y"])
        y.append(yy)
        a.append(float(want[tid]["p_logistic"]))
        b.append(caus.risk())
        c.append(float(prov["risk"]))
        d.append(float(disc["risk"]))
        e.append((b[-1] + c[-1] + d[-1]) / 3)
        profiles.append(
            {
                "task_id": tid,
                "y": yy,
                "p_logistic": a[-1],
                "change_causality": caus.to_dict(),
                "contract_provenance": {k: v for k, v in prov.items() if k != "sample"}
                | {"sample": prov.get("sample")},
                "verifier_discrimination": disc,
            }
        )

    def pack(name, scores):
        return {
            "name": name,
            "auroc": auroc(y, scores),
            "retain_curve": retain_curve(y, scores),
        }

    return {
        "n": len(y),
        "n_invalid": sum(y),
        "base_rate": sum(y) / len(y) if y else None,
        "sample_salt": "causal-150",
        "executed_gold_eval": False,
        "A_proxy_oof_logistic": pack("A", a),
        "B_change_causality": pack("B", b),
        "C_contract_provenance": pack("C", c),
        "D_verifier_discrimination": pack("D", d),
        "E_combined_untrained": pack("E", e),
        "primary_metric": "residual_invalid at retain 5% and 20%",
        "profiles": profiles,
    }
