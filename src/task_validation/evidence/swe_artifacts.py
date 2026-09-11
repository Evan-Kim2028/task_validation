"""Cheap SWE-bench evidence from public artifacts. No Docker, no human labels.

These features are computed from problem_statement, gold patch, and test
patch. They are allowed as predictors of the 2024 filter_out label. The
human severity axes are not.
"""

from __future__ import annotations

from task_validation.evidence.diffstats import diff_stats, identifiers, parse_json_list

# Frozen. Adding a name is a new protocol version.
CHEAP_FEATURE_NAMES = (
    "stmt_chars",
    "stmt_lines",
    "stmt_n_identifiers",
    "has_code_fence",
    "has_traceback",
    "has_http_url",
    "has_reproduction_hint",
    "hints_chars",
    "n_fail_to_pass",
    "n_pass_to_pass",
    "patch_n_files",
    "patch_n_hunks",
    "patch_n_changed_lines",
    "test_n_files",
    "test_n_hunks",
    "test_n_changed_lines",
    "test_stmt_id_overlap",
    "test_only_id_frac",
    "f2p_in_statement_frac",
    "test_has_warning_assert",
    "test_has_match_kw",
    "test_has_exact_string_literal",
    "gold_mentions_deprecation",
    "gold_to_test_line_ratio",
)


def swe_cheap_features(rec: dict) -> dict[str, float]:
    stmt = rec.get("problem_statement") or ""
    patch = rec.get("patch") or ""
    tpatch = rec.get("test_patch") or ""
    hints = rec.get("hints_text") or ""
    f2p = parse_json_list(rec.get("FAIL_TO_PASS"))
    p2p = parse_json_list(rec.get("PASS_TO_PASS"))
    pstats = diff_stats(patch)
    tstats = diff_stats(tpatch)
    stmt_ids = identifiers(stmt)
    test_ids = identifiers(tpatch)
    for name in f2p:
        test_ids |= identifiers(name)
    overlap = (len(stmt_ids & test_ids) / len(test_ids)) if test_ids else 0.0
    only = (len(test_ids - stmt_ids) / len(test_ids)) if test_ids else 0.0
    f2p_in = 0.0
    if f2p:
        hits = sum(1 for n in f2p if n.split(".")[-1] in stmt or n in stmt)
        f2p_in = hits / len(f2p)
    gold_lines = max(pstats["n_changed_lines"], 1)
    test_lines = tstats["n_changed_lines"]
    return {
        "stmt_chars": float(len(stmt)),
        "stmt_lines": float(stmt.count("\n") + 1),
        "stmt_n_identifiers": float(len(stmt_ids)),
        "has_code_fence": 1.0 if ("```" in stmt or "~~~" in stmt) else 0.0,
        "has_traceback": 1.0 if ("Traceback" in stmt or "Error:" in stmt) else 0.0,
        "has_http_url": 1.0 if ("http://" in stmt or "https://" in stmt) else 0.0,
        "has_reproduction_hint": 1.0
        if any(w in stmt.lower() for w in ("reproduce", "to reproduce", "minimal example"))
        else 0.0,
        "hints_chars": float(len(hints)),
        "n_fail_to_pass": float(len(f2p)),
        "n_pass_to_pass": float(len(p2p)),
        "patch_n_files": float(pstats["n_files"]),
        "patch_n_hunks": float(pstats["n_hunks"]),
        "patch_n_changed_lines": float(pstats["n_changed_lines"]),
        "test_n_files": float(tstats["n_files"]),
        "test_n_hunks": float(tstats["n_hunks"]),
        "test_n_changed_lines": float(test_lines),
        "test_stmt_id_overlap": float(overlap),
        "test_only_id_frac": float(only),
        "f2p_in_statement_frac": float(f2p_in),
        "test_has_warning_assert": 1.0
        if any(w in tpatch for w in ("DeprecationWarning", "FutureWarning", "pytest.warns"))
        else 0.0,
        "test_has_match_kw": 1.0 if "match=" in tpatch else 0.0,
        "test_has_exact_string_literal": 1.0 if tpatch.count('assert') and ("== '" in tpatch or '== "' in tpatch) else 0.0,
        "gold_mentions_deprecation": 1.0 if "deprecat" in patch.lower() else 0.0,
        "gold_to_test_line_ratio": float(test_lines / gold_lines),
    }


FORBIDDEN_PREDICTORS = frozenset(
    {
        "underspecified",
        "false_negative",
        "other_major_issues",
        "filter_out",
        "underspecified_notes",
        "false_negative_notes",
        "other_notes",
        "difficulty",
        "human_validity_label",
        "human_severity",
    }
)
