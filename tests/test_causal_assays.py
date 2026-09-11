from task_validation.evidence.causality import change_causality
from task_validation.evidence.provenance import contract_provenance, parse_constraints


def test_unwitnessed_gold_file_without_matching_test():
    rec = {
        "patch": "diff --git a/pkg/parser.py b/pkg/parser.py\n@@ -1,1 +1,2 @@\n-x\n+y\n+z\n",
        "test_patch": "diff --git a/tests/test_other.py b/tests/test_other.py\n@@ -0,0 +1,2 @@\n+def test_foo():\n+    assert True\n",
        "FAIL_TO_PASS": '["tests.test_other.test_foo"]',
        "PASS_TO_PASS": "[]",
        "problem_statement": "Fix the parser.",
    }
    c = change_causality(rec)
    assert c.n_gold_hunks >= 1
    assert c.unwitnessed_hunk_frac > 0


def test_witness_when_test_names_gold_module():
    rec = {
        "patch": "diff --git a/pkg/parser.py b/pkg/parser.py\n@@ -1 +1 @@\n-x\n+y\n",
        "test_patch": "diff --git a/tests/test_parser.py b/tests/test_parser.py\n@@ -0,0 +1 @@\n+assert parse()\n",
        "FAIL_TO_PASS": '["tests.test_parser.test_parse"]',
        "PASS_TO_PASS": "[]",
        "problem_statement": "Fix parse().",
    }
    c = change_causality(rec)
    assert c.n_hunks_with_witness >= 1


def test_orphaned_literal_not_in_prompt_or_gold():
    rec = {
        "problem_statement": "Handle empty input.",
        "patch": "diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-x\n+return None\n",
        "test_patch": '+def test_x():\n+    assert foo() == "secret-format-xyz"\n',
        "FAIL_TO_PASS": "[]",
    }
    p = contract_provenance(rec)
    assert p["n_constraints"] >= 1
    assert p["orphaned_frac"] > 0


def test_parse_raises_constraint():
    cs = parse_constraints("+    with pytest.raises(ValueError):\n+        foo()\n")
    kinds = {c.kind for c in cs}
    assert "raises" in kinds or "call" in kinds
