from task_validation.evidence.pro_families import pro_family_features, suspected_family
from task_validation.ingest.external_audits import match_prefixes


def test_strict_string_not_in_spec():
    rec = {
        "problem_statement": "Format the table of contents with a single leading space.",
        "requirements": "Keep markdown list structure.",
        "interface": "toc()",
        "patch": "diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-x\n+y\n",
        "test_patch": 'assert toc() == "  heading"\n',
        "fail_to_pass": '["test_toc"]',
        "pass_to_pass": "[]",
    }
    f = pro_family_features(rec)
    assert f["misleading_conflict_tokens"] == 1.0
    assert f["strict_exact_lits_not_in_spec"] >= 1.0
    assert suspected_family(f) in {
        "overly_strict_tests",
        "underspecified_prompts",
        "misleading_prompt",
        "low_coverage_tests",
    }


def test_prefix_match_truncated_claims():
    ids = [
        "instance_internetarchive__openlibrary-e1e502986a3b003899a8347ac8a7ff7b08cbfc39-v08d8"
    ]
    prefixes = ["instance_internetarchive__openlibrary-e1e502986a3b0038"]
    hits = match_prefixes(ids, prefixes)
    assert ids[0] in hits
