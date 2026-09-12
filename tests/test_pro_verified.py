import json
from pathlib import Path

from task_validation.evidence.pro_verified import (
    auroc,
    bootstrap_auroc,
    enrichment,
    evaluate_predicates,
    head_size,
    join,
    jaccard,
    label_rows,
    main,
    map_instance_ids,
    parse_repaired_markdown,
    residual_in_tail,
    run,
    score_block,
)


README_FIXTURE = """# SWE-Bench Pro Verified

instance_IGNOREME__table-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

## Part I: Anti-hacking

instance_IGNOREME__part1-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

## Part II: Task refinement (102 Tasks)

- **Misleading prompts**: steer the model.
- **Overly narrow tests**: unspecified pins.
- **Overly broad tests**: incomplete coverage.
- **Other issues**: formatting.

- **Misleading prompts** (2 samples)
```text
instance_mis__mis-1
instance_mis__mis-2
```

- **Overly narrow tests** (3 samples)
```text
instance_nar__nar-1
instance_nar__nar-2
instance_nar__nar-3
```

- **Overly borad tests** (1 samples)
```text
instance_brd__brd-1
```

- **Other issues** (1 samples)
```text
instance_oth__oth-1
```

## Contact

instance_IGNOREME__contact-cccccccccccccccccccccccccccccccccccccccc
"""


def test_parse_part_ii_only_and_borad_typo():
    recs = parse_repaired_markdown(README_FIXTURE)
    by = {r["instance_id"]: r["category"] for r in recs}
    assert len(recs) == 7
    assert by["instance_mis__mis-1"] == "misleading_prompts"
    assert by["instance_nar__nar-2"] == "overly_narrow_tests"
    assert by["instance_brd__brd-1"] == "overly_broad_tests"
    assert by["instance_oth__oth-1"] == "other"
    assert "instance_IGNOREME__table-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" not in by
    assert "instance_IGNOREME__part1-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" not in by
    assert "instance_IGNOREME__contact-cccccccccccccccccccccccccccccccccccccccc" not in by


def test_map_exact_and_prefix_strip_add():
    verified = ["instance_a__a-1", "b__b-2", "instance_c__c-3"]
    pro = ["instance_a__a-1", "instance_b__b-2", "c__c-3"]
    m = map_instance_ids(verified, pro)
    assert m["mapping"]["instance_a__a-1"] == "instance_a__a-1"
    assert m["method"]["instance_a__a-1"] == "exact"
    assert m["mapping"]["b__b-2"] == "instance_b__b-2"
    assert m["method"]["b__b-2"] == "prefix_add"
    assert m["mapping"]["instance_c__c-3"] == "c__c-3"
    assert m["method"]["instance_c__c-3"] == "prefix_strip"
    assert m["n_matched"] == 3
    assert m["unmatched"] == []


def test_unique_prefix_maps_one_hit_only():
    verified = ["instance_foo__foo-abc", "instance_bar__bar-xyz"]
    pro = [
        "instance_foo__foo-abc-v111",
        "instance_bar__bar-xyz-v1",
        "instance_bar__bar-xyz-v2",
    ]
    m = map_instance_ids(verified, pro)
    assert m["mapping"]["instance_foo__foo-abc"] == "instance_foo__foo-abc-v111"
    assert m["method"]["instance_foo__foo-abc"] == "unique_prefix"
    assert "instance_bar__bar-xyz" not in m["mapping"]
    assert m["unmatched"] == ["instance_bar__bar-xyz"]


def test_head_size_matches_reconstruction_rounding():
    assert head_size(731, 0.10) == 73
    assert head_size(731, 0.20) == 146
    assert head_size(10, 0.10) == 1


def test_enrichment_and_residual():
    ranked = [f"t{i}" for i in range(10)]
    positive = {"t0", "t1"}
    row = enrichment(ranked, positive, 0.10)
    assert row["k"] == 1
    assert row["n_positive_in_head"] == 1
    assert abs(row["base_rate"] - 0.2) < 1e-12
    assert abs(row["enrichment"] - 5.0) < 1e-12
    tail = residual_in_tail(list(reversed(ranked)), positive, 0.20)
    assert tail["k"] == 2
    assert tail["n_positive"] == 0
    assert tail["residual"] == 0.0


def test_auroc_and_bootstrap_ci():
    y = [0, 0, 1, 1]
    scores = [0.1, 0.2, 0.8, 0.9]
    assert auroc(y, scores) == 1.0
    boot = bootstrap_auroc(y, scores, n_reps=50, seed=0)
    assert boot["value"] == 1.0
    assert boot["ci95"] is not None
    assert boot["ci95"][0] <= boot["ci95"][1]
    assert 0 < boot["n_defined"] <= 50


def test_jaccard():
    assert jaccard({"a", "b", "c"}, {"b", "c", "d"}) == 0.5
    assert jaccard(set(), set()) is None


def _joined(n=10):
    # high score = high index. repaired: 7-9 narrow, 6 misleading, 0 other (so the low tail is dirty)
    rows = []
    for i in range(n):
        cat = None
        repaired = False
        if i >= 7:
            cat = "overly_narrow_tests"
            repaired = True
        elif i == 6:
            cat = "misleading_prompts"
            repaired = True
        elif i == 0:
            cat = "other"
            repaired = True
        rows.append(
            {
                "task_id": f"t{i}",
                "openai_style_risk": i / 10,
                "cheap_risk": (n - 1 - i) / 10,
                "repaired": repaired,
                "category": cat,
                "june_kim": i in {8, 9},
            }
        )
    return rows


def test_predicates_pass_on_fixture():
    block = score_block(_joined(), "openai_style_risk", n_bootstrap=20, seed=0)
    pred = evaluate_predicates(block)
    assert block["all"]["enrichment"] >= 1.5
    assert block["overly_narrow_tests"]["enrichment"] > block["misleading_prompts"]["enrichment"]
    assert block["tail"]["residual"] > 0.05
    assert pred["YES"] is True
    assert pred["P2_note"] is None


def test_p2_fails_when_not_category_specific():
    rows = _joined()
    for r in rows:
        r["openai_style_risk"] = 0.5
        if r["category"] == "misleading_prompts":
            r["openai_style_risk"] = 0.99
    block = score_block(rows, "openai_style_risk")
    pred = evaluate_predicates(block)
    assert pred["P2"] is False
    assert pred["P2_note"] == "score is not category-specific"


def test_join_does_not_change_scores():
    feats = [
        {
            "task_id": "t0",
            "features": {"openai_style_risk": 0.2, "cheap_risk": 0.4},
        },
        {
            "task_id": "t1",
            "features": {"openai_style_risk": 0.9, "cheap_risk": 0.1},
        },
    ]
    joined = join(feats, {"t1": "overly_narrow_tests"}, {"t0"})
    assert joined[0]["openai_style_risk"] == 0.2
    assert joined[1]["repaired"] is True
    assert joined[0]["june_kim"] is True
    assert joined[1]["category"] == "overly_narrow_tests"


def test_labels_eval_only_flag():
    repaired = [
        {"instance_id": "instance_a__a-1", "category": "overly_narrow_tests"},
        {"instance_id": "instance_b__b-2", "category": "misleading_prompts"},
    ]
    rows = label_rows(repaired, {"instance_a__a-1": "instance_a__a-1"})
    assert all(r["eval_only"] is True for r in rows)
    assert all(r["provenance"] == "opencompass_swebench_pro_verified_2026" for r in rows)
    assert rows[0]["category"] == "misleading_prompts"
    assert rows[1]["matched_to_pro"] is True
    assert rows[0]["matched_to_pro"] is False


def test_mapping_below_threshold_stops(tmp_path: Path):
    feat = tmp_path / "feat.jsonl"
    rows = []
    for i in range(10):
        rows.append(
            {
                "task_id": f"instance_ok__ok-{i}",
                "features": {"openai_style_risk": i / 10, "cheap_risk": 0.1},
            }
        )
    feat.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    verified = tmp_path / "README.md"
    verified.write_text(
        "## Part II\n- **Misleading prompts** (3 samples)\n```text\n"
        "instance_ok__ok-0\ninstance_missing__x-1\ninstance_missing__x-2\n```\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    labels = tmp_path / "labels.jsonl"
    report = run(
        feat,
        verified,
        out,
        labels_path=labels,
        min_matched=3,
        n_bootstrap=5,
        seed=0,
    )
    assert report["error"] == "mapping_below_threshold"
    assert report["mapping"]["n_matched"] == 1
    assert labels.is_file()


def test_cli_on_small_fixture(tmp_path: Path):
    feat = tmp_path / "feat.jsonl"
    ids = [
        "instance_mis__mis-1",
        "instance_mis__mis-2",
        "instance_nar__nar-1",
        "instance_nar__nar-2",
        "instance_nar__nar-3",
        "instance_brd__brd-1",
        "instance_oth__oth-1",
        "instance_ok__ok-1",
        "instance_ok__ok-2",
        "instance_ok__ok-3",
    ]
    lines = []
    for i, tid in enumerate(ids):
        lines.append(
            json.dumps(
                {
                    "task_id": tid,
                    "features": {
                        "openai_style_risk": i / 10,
                        "cheap_risk": (9 - i) / 10,
                    },
                }
            )
            + "\n"
        )
    feat.write_text("".join(lines), encoding="utf-8")
    vdir = tmp_path / "verified"
    vdir.mkdir()
    (vdir / "README.md").write_text(README_FIXTURE, encoding="utf-8")
    claims = tmp_path / "june.md"
    claims.write_text(
        "`instance_nar__nar-1` `instance_nar__nar-2` `instance_ok__ok-1`\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    labels = tmp_path / "labels.jsonl"
    rc = main(
        [
            "--features",
            str(feat),
            "--verified",
            str(vdir),
            "--out",
            str(out),
            "--june-kim",
            str(claims),
            "--labels-out",
            str(labels),
            "--min-matched",
            "6",
            "--bootstrap",
            "30",
            "--seed",
            "0",
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["mapping"]["n_matched"] == 7
    assert report["constraints"]["eval_only"] is True
    assert report["constraints"]["used_audit_labels_as_predictors"] is False
    assert report["openai_style_risk"]["auroc"]["n_bootstrap"] == 30
    lab = [json.loads(l) for l in labels.read_text(encoding="utf-8").splitlines() if l]
    assert len(lab) == 7
    assert all(r["eval_only"] is True for r in lab)
    assert report["june_kim_overlap"]["n_intersection"] >= 1
