import json
from pathlib import Path

from task_validation.ingest.corpus import catalog
from task_validation.ingest.rater_noise import rater_noise
from task_validation.sampling.coverage_lab import run_lab, simulate_srs_lab


def test_srs_lab_covers_on_toy():
    pop = {f"t{i}": int(i < 2) for i in range(40)}  # 2/40 = 5%
    row = simulate_srs_lab(pop, n=10, reps=30, seed="toy")
    assert row.design == "srs-hypergeometric"
    assert 0.0 <= row.coverage <= 1.0
    assert row.n_false_certify["0.05"] == 0.0 or row.true_p >= 0.05


def test_rater_noise_single_vs_majority(tmp_path: Path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        json.dumps(
            {
                "task_id": "a",
                "votes": [1, 0, 0],
                "majority_invalid": 0,
                "openai_2024_conservative": 1,
                "unanimous_invalid": 0,
            }
        )
        + "\n"
        + json.dumps(
            {
                "task_id": "b",
                "votes": [1, 1, 1],
                "majority_invalid": 1,
                "openai_2024_conservative": 1,
                "unanimous_invalid": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rep = rater_noise(p)
    assert rep["n_tasks"] == 2
    assert "mean_fnr" in rep["single_rater_vs_majority"]


def test_corpus_does_not_merge(tmp_path: Path):
    (tmp_path / "data" / "gold").mkdir(parents=True)
    report = catalog(tmp_path)
    assert report["merged_into_one_y"] is False
    names = [s["name"] for s in report["sources"]]
    assert "task-verification-bench" in names
    tvb = [s for s in report["sources"] if s["name"] == "task-verification-bench"][0]
    assert tvb["n"] == 0


def test_run_lab_smoke(tmp_path: Path):
    gold = tmp_path / "gold.jsonl"
    lines = []
    for i in range(30):
        lines.append(
            json.dumps(
                {
                    "task_id": f"r{i % 3}__{i}",
                    "repository": f"r{i % 3}",
                    "human_validity_label": "invalid" if i < 6 else "valid",
                    "human_severity": {"false_negative": 1.0 if i < 6 else 0.0},
                }
            )
        )
    gold.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = run_lab(gold, None, n=8, replicates=5, seed="s", prevalences=(0.20,))
    assert out["stratified_normal_is_release_rule"] is False
    assert out["final_estimator_requires_replicates"] == 5000
    assert out["rows"]
