"""Public Terminal-Bench 2.1 maintenance history. HISTORICAL_MAINTENANCE, not TVB."""

from __future__ import annotations

import json
from pathlib import Path

# From https://www.tbench.ai/news/terminal-bench-2-1 (fetched 2026-09-11).
# 28 tasks changed in TB 2.0 → 2.1. Named misspec example: query-optimize.
# Categories in the post: 9 external-dependency, 8 resource-mismatch, remainder misspecification.
# Per-task category is NOT fully public in that post except query-optimize. Do not invent it.

TB21_CHANGED = (
    "polyglot-c-py",
    "polyglot-rust-c",
    "caffe-cifar-10",
    "torch-tensor-parallelism",
    "adaptive-rejection-sampler",
    "mteb-retrieve",
    "build-pmars",
    "install-windows-3.11",
    "compile-compcert",
    "mteb-leaderboard",
    "rstan-to-pystan",
    "extract-moves-from-video",
    "crack-7z-hash",
    "configure-git-webserver",
    "filter-js-from-html",
    "sam-cell-seg",
    "gpt2-codegolf",
    "financial-document-processor",
    "hf-model-inference",
    "make-doom-for-mips",
    "build-pov-ray",
    "torch-pipeline-parallelism",
    "train-fasttext",
    "fix-git",
    "protein-assembly",
    "query-optimize",
    "mcmc-sampling-stan",
    "overfull-hbox",
)

NAMED_MISSPEC = {
    "query-optimize": "tests expected Spark SQL; instructions asked for PostgreSQL",
}

SOURCE = {
    "url": "https://www.tbench.ai/news/terminal-bench-2-1",
    "pr": "https://github.com/harbor-framework/terminal-bench-2/pull/53",
    "n_changed_claimed": 28,
    "n_tb20": 89,
    "tv_not_used": True,
}


def rows() -> list[dict]:
    out = []
    for name in TB21_CHANGED:
        out.append(
            {
                "task_id": name,
                "benchmark": "terminal-bench",
                "benchmark_version": "2.0-to-2.1",
                "protocol": "historical_maintenance",
                "label": "INVALID_THEN_REPAIRED",
                "provenance": "HISTORICAL_MAINTENANCE",
                "confidence": "author_maintainer_confirmed_defect",
                "estimand": "task_or_evaluator_defect_later_acknowledged",
                "not_estimand": "openai_2024_f2p_fairness",
                "named_misspec": NAMED_MISSPEC.get(name),
                "pre_post": "tb2.0_broken_vs_tb2.1_repaired",
                "category_public": "misspecification" if name in NAMED_MISSPEC else "unlisted_in_news_post",
                "source": SOURCE["url"],
                "executed": False,
            }
        )
    return out


def write_jsonl(path: Path) -> dict:
    recs = rows()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    summary = {
        "n": len(recs),
        "n_named_misspec": len(NAMED_MISSPEC),
        "source": SOURCE,
        "out": str(path),
        "note": (
            "28 names from the public 2.1 post. Only query-optimize is typed as "
            "misspecification in that post. Do not treat resource/dep fixes as "
            "evaluator-invalidity without the PR breakdown. TVB not used."
        ),
    }
    path.with_name(path.stem + ".summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary
