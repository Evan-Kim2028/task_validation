"""Ingest ScaleAI SWE-bench Pro public split (731)."""

from __future__ import annotations

import json
from pathlib import Path

from task_validation.evidence.mutation import swe_mutant_menu
from task_validation.evidence.pro_families import family_flags, pro_family_features, suspected_family


ARTIFACT_FIELDS = (
    "instance_id",
    "repo",
    "repo_language",
    "base_commit",
    "dockerhub_tag",
    "issue_specificity",
    "issue_categories",
)


def ingest_pro(parquet_path: Path, out_jsonl: Path) -> dict:
    import pandas as pd

    df = pd.read_parquet(parquet_path)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    langs = {}
    families: dict[str, int] = {}
    n = 0
    with out_jsonl.open("w", encoding="utf-8") as fh:
        for rec in df.to_dict(orient="records"):
            feats = pro_family_features(rec)
            fam = suspected_family(feats)
            families[fam] = families.get(fam, 0) + 1
            flags = family_flags(feats)
            lang = rec.get("repo_language") or "unknown"
            langs[lang] = langs.get(lang, 0) + 1
            mutants = swe_mutant_menu(rec.get("patch") or "")
            row = {
                "task_id": rec["instance_id"],
                "benchmark": "swe-bench-pro",
                "benchmark_version": "public-731",
                "repository": rec.get("repo"),
                "language": lang,
                "provenance": "PENDING_HUMAN",
                "artifacts_available": {
                    "instruction": bool(rec.get("problem_statement")),
                    "requirements": bool(rec.get("requirements")),
                    "interface": bool(rec.get("interface")),
                    "gold_patch": bool(rec.get("patch")),
                    "test_patch": bool(rec.get("test_patch")),
                    "fail_to_pass": bool(rec.get("fail_to_pass")),
                    "dockerhub_tag": bool(rec.get("dockerhub_tag")),
                    "environment_image": bool(rec.get("dockerhub_tag")),
                    "agent_run_required_for_hidden_tests": True,
                },
                "dockerhub_tag": rec.get("dockerhub_tag"),
                "base_commit": rec.get("base_commit"),
                "features": feats,
                "suspected_family": fam,
                "family_flags": flags,
                "mutation_menu": {
                    "n_file_targets": mutants["n_file_targets"],
                    "n_hunk_mutants": mutants["n_hunk_mutants"],
                    "executed": False,
                },
            }
            fh.write(json.dumps(row) + "\n")
            n += 1
    return {
        "n": n,
        "languages": langs,
        "suspected_family_counts": families,
        "out": str(out_jsonl),
        "source": "https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro",
        "note": "Patches are not stored in the jsonl. Features only. Audit labels are not inputs.",
    }
