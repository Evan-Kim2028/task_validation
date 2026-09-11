"""Join SWE-bench test artifacts onto the 2024 ensemble labels."""

from __future__ import annotations

import json
from pathlib import Path

from task_validation.evidence.mutation import swe_mutant_menu
from task_validation.evidence.swe_artifacts import CHEAP_FEATURE_NAMES, swe_cheap_features


def join_parquet(gold_jsonl: Path, parquet_path: Path, out_path: Path) -> dict:
    import pandas as pd

    gold = {}
    with gold_jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            gold[rec["task_id"]] = rec
    df = pd.read_parquet(parquet_path)
    n_matched = 0
    missing = []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for _, art in df.iterrows():
            tid = art["instance_id"]
            if tid not in gold:
                continue
            g = gold[tid]
            rec = {k: art[k] for k in art.index}
            feats = swe_cheap_features(rec)
            mutants = swe_mutant_menu(rec.get("patch") or "")
            row = {
                "task_id": tid,
                "benchmark": "swe-bench",
                "repository": g.get("repository"),
                "y": 1 if g.get("human_validity_label") == "invalid" else 0,
                "label_protocol": "openai-swe-bench-verified-2024-conservative",
                "features": {n: feats[n] for n in CHEAP_FEATURE_NAMES},
                "mutation_menu": {
                    "n_file_targets": mutants["n_file_targets"],
                    "n_hunk_mutants": mutants["n_hunk_mutants"],
                    "executed": False,
                },
            }
            fh.write(json.dumps(row) + "\n")
            n_matched += 1
        missing = sorted(set(gold) - set(df["instance_id"].tolist()))
    return {
        "n_gold": len(gold),
        "n_parquet": int(len(df)),
        "n_matched": n_matched,
        "n_gold_missing_from_parquet": len(missing),
        "missing_ids_head": missing[:10],
        "out": str(out_path),
    }
