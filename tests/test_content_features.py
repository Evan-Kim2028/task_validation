"""Fixture tests for the content feature extractor (content_features.py).

The fixture is a short instruction, reference diff, and test diff whose
feature values are known by hand. Missing fields must yield None, never
zero.
"""

from __future__ import annotations

from task_validation.evidence.content_features import (
    CONTENT_FEATURE_NAMES,
    added_lines,
    diff_files,
    extract_content_features,
    split_sentences,
)

INSTRUCTION = """The function foo in pkg/mod.py fails on empty input.

Steps to reproduce:
1. Call foo([]).
2. Observe the error.

Traceback (most recent call last):
  File "pkg/mod.py", line 3, in foo
ValueError: empty

Expected output: foo([]) should return 0.
Fix the boundary handling.
"""

PATCH = """diff --git a/pkg/mod.py b/pkg/mod.py
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -1,2 +1,3 @@
 def foo(x):
-    return x[0]
+    if not x:
+        return 0
+    return x[0]
"""

TEST_PATCH = """diff --git a/tests/test_mod.py b/tests/test_mod.py
--- a/tests/test_mod.py
+++ b/tests/test_mod.py
@@ -0,0 +1,4 @@
+def test_empty():
+    assert foo([]) == 0
+def test_nonempty():
+    assert foo([3]) == 3
"""


def _feats():
    return extract_content_features(INSTRUCTION, PATCH, TEST_PATCH)


def test_all_features_present():
    f = _feats()
    assert set(f) == set(CONTENT_FEATURE_NAMES)


def test_instruction_counts():
    f = _feats()
    assert f["n_instr_tokens"] > 0
    assert f["n_instr_sentences"] == len(split_sentences(INSTRUCTION))
    # one imperative opener: "Fix the boundary handling."
    assert f["n_instr_imperative_openers"] == 1.0
    assert f["instr_mean_sentence_tokens"] > 0


def test_instruction_flags():
    f = _feats()
    assert f["has_instr_error_text"] == 1.0  # Traceback + ValueError
    assert f["has_instr_repro_steps"] == 1.0  # "Steps to reproduce"
    assert f["has_instr_expected_output"] == 1.0  # "Expected output:"
    assert f["n_instr_acceptance_phrases"] >= 1.0  # "should return"
    assert f["has_instr_code_block"] == 0.0
    assert f["n_instr_code_blocks"] == 0.0


def test_named_files_and_touch_fraction():
    f = _feats()
    # pkg/mod.py is the only instruction-named file (tests/test_mod.py is
    # not in the instruction); the reference patch touches it.
    assert f["n_instr_named_files"] == 1.0
    assert f["instr_named_files_touched_frac"] == 1.0


def test_test_patch_counts():
    f = _feats()
    assert f["n_tests"] == 2.0
    assert f["n_assert_lines"] == 2.0
    assert f["assert_literal_frac"] == 1.0  # both assert against a literal
    assert f["assert_mean_tokens"] is not None


def test_patch_sizes_and_ratio():
    f = _feats()
    assert f["ref_patch_n_files"] == 1.0
    assert f["ref_patch_n_lines"] == 4.0  # 3 added + 1 removed
    # test diff adds 4 lines, reference changes 4
    assert f["test_to_ref_line_ratio"] == 1.0


def test_code_fence_block_counts_open_and_close():
    instr = "Run this:\n```\nfoo()\n```\nand that:\n~~~\nbar()\n~~~\n"
    f = extract_content_features(instr, None, None)
    assert f["n_instr_code_blocks"] == 2.0
    assert f["has_instr_code_block"] == 1.0


def test_missing_fields_yield_none_not_zero():
    f = extract_content_features(INSTRUCTION, None, None)
    assert f["n_tests"] is None
    assert f["n_assert_lines"] is None
    assert f["assert_mean_tokens"] is None
    assert f["assert_literal_frac"] is None
    assert f["ref_patch_n_lines"] is None
    assert f["ref_patch_n_files"] is None
    assert f["test_to_ref_line_ratio"] is None
    # instruction features still present
    assert f["n_instr_tokens"] is not None


def test_untouched_named_files_fraction():
    f = extract_content_features(
        "Fix pkg/mod.py and lib/util.py.",
        PATCH,  # touches pkg/mod.py only
        None,
    )
    assert f["n_instr_named_files"] == 2.0
    assert f["instr_named_files_touched_frac"] == 0.5


def test_dir_mode_reference_files_list():
    # Harbor-style: solution is a file blob plus a file list, not a diff.
    f = extract_content_features(
        "Repair /app/ope/evaluate.py.",
        "def evaluate():\n    return 1\n",
        "def test_eval():\n    assert evaluate() == 1\n",
        reference_files=["solve.sh", "evaluate.py"],
        reference_is_diff=False,
        tests_is_diff=False,
    )
    assert f["ref_patch_n_files"] == 2.0
    assert f["ref_patch_n_lines"] == 2.0
    assert f["instr_named_files_touched_frac"] == 1.0
    assert f["n_tests"] == 1.0


def test_added_lines_and_diff_files():
    assert "def test_empty" in added_lines(TEST_PATCH)
    assert "test_mod.py" not in added_lines(TEST_PATCH).splitlines()[0]
    assert diff_files(PATCH) == ["pkg/mod.py"]
    assert diff_files(TEST_PATCH) == ["tests/test_mod.py"]
