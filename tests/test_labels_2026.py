import json
from pathlib import Path

from task_validation.evidence.labels_2026 import (
    PREDICATES,
    T3_JUDGE_MIN,
    _construct_from_cats,
    _label_from_counts,
    aba_major_ids,
    build_summary,
    census_flags,
    fisher_exact_2x2,
    map_pro_casefold,
    overlap_matrix,
    parse_aba_benchmark,
    parse_benchguard_gold,
    parse_tau2_changelog,
    parse_zai_changes,
    t1_tb2_verifier,
    t2_tb2_census,
    t3_swe_verified_spec,
    t5_swe_random100,
    tb_pre_execution,
    write_jsonl,
)


ABA_FIXTURE = {
    "slug": "tb2",
    "tasks": [
        {
            "task_id": "build-pmars",
            "task_file": "build-pmars__aaa",
            "static_findings_major": 1,
            "static_findings_minor": 0,
            "trajectory_findings_major": 1,
            "trajectory_findings_minor": 0,
            "static_findings_by_category": {
                "instruction": {"major": 0, "minor": 0},
                "evaluation": {"major": 1, "minor": 0},
                "env": {"major": 0, "minor": 0},
            },
            "trajectory_findings_by_category": {
                "instruction": {"major": 0, "minor": 0},
                "evaluation": {"major": 1, "minor": 0},
                "env": {"major": 0, "minor": 0},
            },
        },
        {
            "task_id": "query-optimize",
            "task_file": "query-optimize__bbb",
            "static_findings_major": 0,
            "static_findings_minor": 1,
            "trajectory_findings_major": 0,
            "trajectory_findings_minor": 0,
            "static_findings_by_category": {
                "instruction": {"major": 0, "minor": 1},
                "evaluation": {"major": 0, "minor": 0},
                "env": {"major": 0, "minor": 0},
            },
            "trajectory_findings_by_category": {
                "instruction": {"major": 0, "minor": 0},
                "evaluation": {"major": 0, "minor": 0},
                "env": {"major": 0, "minor": 0},
            },
        },
        {
            "task_id": "polyglot-c-py",
            "task_file": "polyglot-c-py__ccc",
            "static_findings_major": 0,
            "static_findings_minor": 0,
            "trajectory_findings_major": 0,
            "trajectory_findings_minor": 0,
            "static_findings_by_category": {
                "instruction": {"major": 0, "minor": 0},
                "evaluation": {"major": 0, "minor": 0},
                "env": {"major": 0, "minor": 0},
            },
            "trajectory_findings_by_category": {
                "instruction": {"major": 0, "minor": 0},
                "evaluation": {"major": 0, "minor": 0},
                "env": {"major": 0, "minor": 0},
            },
        },
    ],
}


def test_predicates_are_frozen_before_compute():
    assert "T1" in PREDICATES and "T5" in PREDICATES
    assert "Fisher" in PREDICATES["T1"]
    assert ">= 0.70" in PREDICATES["T3"]
    assert T3_JUDGE_MIN == 0.70
    assert "descriptive" in PREDICATES["T4"]


def test_label_and_construct_from_counts():
    assert _label_from_counts(1, 4) == "major_issue"
    assert _label_from_counts(0, 2) == "minor_issue"
    assert _label_from_counts(0, 0) == "none"
    assert (
        _construct_from_cats({"evaluation": {"major": 1, "minor": 0}}, 1, 0)
        == "verifier_invalid"
    )
    assert (
        _construct_from_cats({"instruction": {"major": 0, "minor": 1}}, 0, 1)
        == "spec_invalid"
    )
    assert (
        _construct_from_cats(
            {"instruction": {"major": 1}, "evaluation": {"major": 1}}, 2, 0
        )
        == "mixed"
    )
    assert _construct_from_cats({}, 0, 0) == "unknown"


def test_parse_aba_one_row_per_task():
    rows = parse_aba_benchmark(
        ABA_FIXTURE,
        provenance="https://data.autobenchaudit.com/benchmarks/tb2/benchmark.json",
        date="2026-05-18",
        slug="tb2",
    )
    assert len(rows) == 3
    by = {r["task_id"]: r for r in rows}
    assert by["build-pmars"]["label"] == "major_issue"
    assert by["build-pmars"]["construct"] == "verifier_invalid"
    assert by["build-pmars"]["eval_only"] is True
    assert by["build-pmars"]["join_key_kind"] == "tb_directory_name"
    assert by["query-optimize"]["label"] == "minor_issue"
    assert by["query-optimize"]["construct"] == "spec_invalid"
    assert by["polyglot-c-py"]["label"] == "none"
    assert by["polyglot-c-py"]["construct"] == "unknown"
    assert all(r["eval_only"] is True for r in rows)


def test_fisher_matches_known_table():
    # scipy.stats.fisher_exact([[1, 9], [11, 3]]) two-sided ~ 0.002759
    rec = fisher_exact_2x2(1, 9, 11, 3)
    assert rec["table"] == [[1, 9], [11, 3]]
    assert 0.0025 < rec["p_two_sided"] < 0.0031
    rec2 = fisher_exact_2x2(3, 1, 1, 3)
    assert rec2["p_two_sided"] > 0.4


def test_tau2_parses_domain_and_ranges():
    text = """
## [1.0.0] - 2026-MM-DD
### Fixed
#### Airline task fixes (27 tasks)
- Tasks 2, 27, 38: Removed incorrect delayed flight compensation
- Task 7: Corrected cancellation
- Tasks 15, 16: Disambiguated economy
#### Retail task fixes (26 tasks)
- Tasks 0, 1: Changed similar one
- Task 12, 13: Removed invalid PayPal
#### Banking Knowledge Domain (20+ tasks)
- Required documents corrections across tasks 027, 046, 056
- **`banking_knowledge` tasks 077–086 (lost/stolen card)
- **`banking_knowledge` task_074: Light Blue ATM-fee refund (#374)
## [0.2.1] - 2025-11-07
- Task 99: should be ignored, old version
"""
    rows = parse_tau2_changelog(text)
    ids = {r["task_id"] for r in rows}
    assert "airline-2" in ids and "airline-38" in ids and "airline-7" in ids
    assert "airline-15" in ids and "airline-16" in ids
    assert "retail-0" in ids and "retail-13" in ids
    assert "banking_knowledge-027" in ids
    assert "banking_knowledge-074" in ids
    assert "banking_knowledge-077" in ids and "banking_knowledge-086" in ids
    assert "banking_knowledge-374" not in ids
    assert "retail-99" not in ids
    assert all(r["label"] == "errata" and r["eval_only"] for r in rows)
    assert all(r["join_key_kind"] == "tau2_domain_task_number" for r in rows)


def test_zai_named_tasks_drop_env_only():
    text = """
# 2026.08.18 Review Fixes
## Part I: Grading/Test Fixes
### 1. dna-insert — Primer annealing
### 2. make-doom-for-mips — Fragile startup
| Task | Synced change | Type |
| mteb-leaderboard | Instruction adds | Instruction |
| caffe-cifar-10 | Test accepts cmake | Test |
- **Category A: Test hardcodes** (4 tasks) — build-pmars, hf-model-inference, install-windows-3.11, caffe-cifar-10
Environment Fixes: Updated Dockerfiles (89 tasks)
"""
    rows = parse_zai_changes(text)
    ids = {r["task_id"] for r in rows}
    assert "dna-insert" in ids
    assert "make-doom-for-mips" in ids
    assert "mteb-leaderboard" in ids
    assert "build-pmars" in ids
    assert "hf-model-inference" in ids
    assert len(ids) < 20
    assert all(r["label"] == "repaired" for r in rows)
    assert all(r["eval_only"] for r in rows)


def test_benchguard_keys():
    sab = {
        "tasks": {
            "9": {
                "issues": [
                    {"id": "9_issue_1", "change_type": "instruction", "category": "INST"}
                ]
            }
        }
    }
    rows = parse_benchguard_gold(
        sab,
        source="benchguard_sab",
        benchmark="science-agent-bench",
        join_key_kind="sab_task_key",
        construct="mixed",
        provenance="https://example",
        date="2026-03-10",
    )
    assert len(rows) == 1
    assert rows[0]["task_id"] == "9"
    assert rows[0]["label"] == "repaired"
    assert "instruction" in rows[0]["finding_class"] or "INST" in rows[0]["finding_class"]


def _pairs():
    tasks = {}
    for tid in [
        "build-pmars",
        "caffe-cifar-10",
        "query-optimize",
        "polyglot-c-py",
        "adaptive-rejection-sampler",
    ]:
        fail = tid in {"build-pmars", "caffe-cifar-10"}
        tasks[tid] = {
            "false_reject_pre": fail,
            "pre_oracle_pass": not fail,
            "pre_status": ["executed", "executed"],
            "infra": False,
            "pre": {"oracle": 0.0 if fail else 1.0},
        }
    tasks["make-doom-for-mips"] = {
        "false_reject_pre": False,
        "pre_oracle_pass": None,
        "pre_status": ["infra"],
        "infra": True,
        "pre": {"oracle": None},
    }
    return {"tasks": tasks, "n_pairs_diffable": 5, "n_infra": 1}


def test_t1_higher_major_rate_on_pre_fail():
    rows = parse_aba_benchmark(
        ABA_FIXTURE, provenance="u", date="2026-05-18", slug="tb2"
    )
    # add caffe as major so 2/2 fail vs 0/3 pass
    extra = parse_aba_benchmark(
        {
            "slug": "tb2",
            "tasks": [
                {
                    "task_id": "caffe-cifar-10",
                    "task_file": "caffe__x",
                    "static_findings_major": 1,
                    "static_findings_minor": 0,
                    "trajectory_findings_major": 0,
                    "trajectory_findings_minor": 0,
                    "static_findings_by_category": {
                        "evaluation": {"major": 1, "minor": 0}
                    },
                    "trajectory_findings_by_category": {},
                },
                {
                    "task_id": "adaptive-rejection-sampler",
                    "task_file": "ars__x",
                    "static_findings_major": 0,
                    "static_findings_minor": 0,
                    "trajectory_findings_major": 0,
                    "trajectory_findings_minor": 0,
                    "static_findings_by_category": {},
                    "trajectory_findings_by_category": {},
                },
            ],
        },
        provenance="u",
        date="2026-05-18",
        slug="tb2",
    )
    rec = t1_tb2_verifier(rows + extra, _pairs())
    assert rec["n_fail"] == 2
    assert rec["n_pass"] == 3
    assert rec["table"]["counts"] == [[2, 0], [0, 3]]
    assert rec["higher_rate_on_fail"] is True
    assert rec["pass_predicate"] is True
    groups = tb_pre_execution(_pairs())
    assert groups["skipped"] == ["make-doom-for-mips"]


def test_t2_incomplete_census_note():
    rows = parse_aba_benchmark(
        ABA_FIXTURE, provenance="u", date="2026-05-18", slug="tb2"
    )
    census = [
        {
            "task_id": "build-pmars",
            "probe": "oracle",
            "intended": "accept",
            "accepted": False,
            "status": "executed",
        },
        {
            "task_id": "build-pmars",
            "probe": "nop",
            "intended": "reject",
            "accepted": False,
            "status": "executed",
        },
        {
            "task_id": "polyglot-c-py",
            "probe": "oracle",
            "intended": "accept",
            "accepted": True,
            "status": "executed",
        },
        {
            "task_id": "polyglot-c-py",
            "probe": "nop",
            "intended": "reject",
            "accepted": False,
            "status": "executed",
        },
    ]
    rec = t2_tb2_census(rows, census, catalog_n=89)
    assert rec["census_incomplete"] is True
    assert rec["n_flagged"] == 1
    assert rec["table"]["counts"][0][0] == 1  # flagged and ABA major
    assert "rows available" in rec["note"]
    flags = census_flags(census)
    assert flags["n_tasks_in_census"] == 2


def test_t3_judge_auroc_predicate():
    labels = [
        {
            "source": "aba",
            "benchmark": "swe-bench-verified",
            "task_id": "a",
            "label": "major_issue",
        },
        {
            "source": "aba",
            "benchmark": "swe-bench-verified",
            "task_id": "b",
            "label": "none",
        },
        {
            "source": "aba",
            "benchmark": "swe-bench-verified",
            "task_id": "c",
            "label": "none",
        },
        {
            "source": "aba",
            "benchmark": "swe-bench-verified",
            "task_id": "d",
            "label": "major_issue",
        },
    ]
    judge = [
        {"task_id": "a", "p_invalid": 0.9, "openai_2024_conservative": 1},
        {"task_id": "b", "p_invalid": 0.1, "openai_2024_conservative": 0},
        {"task_id": "c", "p_invalid": 0.2, "openai_2024_conservative": 0},
        {"task_id": "d", "p_invalid": 0.8, "openai_2024_conservative": 1},
    ]
    irt = [
        {"task_id": "a", "p_i": 0.0},
        {"task_id": "b", "p_i": 0.9},
        {"task_id": "c", "p_i": 0.8},
        {"task_id": "d", "p_i": 0.1},
    ]
    rec = t3_swe_verified_spec(labels, judge, irt, n_bootstrap=20, seed=0)
    assert rec["n_joined"] == 4
    assert rec["judge_p_invalid"]["value"] == 1.0
    assert rec["pass_predicate"] is True
    assert rec["solve_rate_1_minus_pi"]["value"] == 1.0


def test_t5_reports_missing_and_present():
    labels = parse_aba_benchmark(
        {
            "slug": "swe_bench_verified",
            "tasks": [
                {
                    "task_id": "django__django-10097",
                    "task_file": "django__django-10097__x",
                    "static_findings_major": 0,
                    "static_findings_minor": 0,
                    "trajectory_findings_major": 0,
                    "trajectory_findings_minor": 0,
                    "static_findings_by_category": {},
                    "trajectory_findings_by_category": {},
                }
            ],
        },
        provenance="u",
        date="2026-05-18",
        slug="swe_bench_verified",
    )
    rec = t5_swe_random100(labels)
    by = {f["task_id"]: f for f in rec["flags"]}
    assert by["django__django-10097"]["in_aba_verified"] is True
    assert by["django__django-10097"]["any_finding"] is False
    assert by["django__django-12503"]["in_aba_verified"] is False


def test_pro_casefold_maps_nodebb():
    rows = [
        {
            "source": "aba",
            "join_key_kind": "swe_pro_instance_id",
            "task_id": "instance_nodebb__nodebb-abc-vnan",
            "label": "major_issue",
        }
    ]
    mapped = map_pro_casefold(rows, ["instance_NodeBB__NodeBB-abc-vnan"])
    assert mapped[0]["task_id"] == "instance_NodeBB__NodeBB-abc-vnan"
    assert mapped[0]["join_note"] == "casefold"
    assert mapped[0]["task_id_source"] == "instance_nodebb__nodebb-abc-vnan"


def test_overlap_matrix_same_join_kind(tmp_path: Path):
    rows = [
        {
            "source": "aba",
            "benchmark": "terminal-bench-2",
            "task_id": "a",
            "join_key_kind": "tb_directory_name",
            "label": "major_issue",
            "construct": "mixed",
        },
        {
            "source": "aba",
            "benchmark": "terminal-bench-2",
            "task_id": "b",
            "join_key_kind": "tb_directory_name",
            "label": "none",
            "construct": "unknown",
        },
        {
            "source": "zai_tb2_verified",
            "benchmark": "terminal-bench-2",
            "task_id": "a",
            "join_key_kind": "tb_directory_name",
            "label": "repaired",
            "construct": "mixed",
        },
        {
            "source": "zai_tb2_verified",
            "benchmark": "terminal-bench-2",
            "task_id": "c",
            "join_key_kind": "tb_directory_name",
            "label": "repaired",
            "construct": "mixed",
        },
    ]
    mat = overlap_matrix(rows)
    pair = mat["pairs"]["aba"]["zai_tb2_verified"]
    assert pair["n_intersection"] == 1
    assert pair["n_a"] == 1
    assert pair["n_b"] == 2
    assert abs(pair["jaccard"] - 0.5) < 1e-12
    path = tmp_path / "labels.jsonl"
    write_jsonl(path, rows)
    assert path.read_text().count("\n") == 4
    summary = build_summary(rows, transfer=None)
    assert summary["eval_only"] is True
    assert summary["n_rows"] == 4
    assert aba_major_ids(rows, source="aba", benchmark="terminal-bench-2") == {"a"}
