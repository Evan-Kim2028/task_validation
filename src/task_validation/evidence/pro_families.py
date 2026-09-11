"""Cheap static signals for OpenAI's four SWE-Bench Pro failure families.

No LLM. No audit labels as inputs. Visible spec = problem_statement +
requirements + interface.
"""

from __future__ import annotations

import re

from task_validation.evidence.diffstats import diff_stats, identifiers, parse_json_list
from task_validation.evidence.swe_artifacts import swe_cheap_features

STRING_LIT_RE = re.compile(r"""(?<!\\)(['"])(.{8,}?)\1""")
WHITESPACE_ASSERT_RE = re.compile(
    r"(toBe|toEqual|assertEqual|assertEqual|==)\s*\(\s*['\"][^'\"]*\s+[^'\"]*['\"]",
    re.I,
)
EXACT_JSON_RE = re.compile(r"json\.dumps|JSON\.stringify|toJSON|exact dict", re.I)

FAMILY_FEATURE_NAMES = (
    "strict_exact_lits_not_in_spec",
    "strict_exact_lit_frac",
    "strict_match_kw",
    "strict_warning_assert",
    "strict_whitespace_assert",
    "strict_json_exact",
    "underspec_test_only_id_frac",
    "underspec_f2p_not_in_spec_frac",
    "underspec_spec_to_test_ratio",
    "coverage_gold_files_unmentioned",
    "coverage_gold_to_test_line_ratio",
    "coverage_few_fail_to_pass",
    "misleading_conflict_tokens",
    "prompt_missing_lit_frac",
    "prompt_test_only_id_frac",
    "requirements_pin_prompt_gap",
    "requirements_defers_to_tests",
    "family_strict",
    "family_underspec",
    "family_low_coverage",
    "family_misleading",
    "cheap_risk",
    "openai_style_risk",
)


def _visible_spec(rec: dict) -> str:
    return "\n".join(
        str(rec.get(k) or "")
        for k in ("problem_statement", "requirements", "interface", "hints_text")
    )


def _string_lits(text: str) -> list[str]:
    out = []
    for _, body in STRING_LIT_RE.findall(text or ""):
        if any(ch.isalpha() for ch in body):
            out.append(body)
    return out


def _norm_rec(rec: dict) -> dict:
    """Map Pro field names onto the SWE-bench cheap-feature adapter."""
    return {
        "problem_statement": rec.get("problem_statement") or "",
        "patch": rec.get("patch") or "",
        "test_patch": rec.get("test_patch") or "",
        "hints_text": rec.get("hints_text") or rec.get("requirements") or "",
        "FAIL_TO_PASS": rec.get("FAIL_TO_PASS") or rec.get("fail_to_pass") or "[]",
        "PASS_TO_PASS": rec.get("PASS_TO_PASS") or rec.get("pass_to_pass") or "[]",
    }


def pro_family_features(rec: dict) -> dict[str, float]:
    cheap = swe_cheap_features(_norm_rec(rec))
    spec = _visible_spec(rec)
    spec_l = spec.lower()
    prompt = rec.get("problem_statement") or ""
    prompt_l = prompt.lower()
    req = rec.get("requirements") or ""
    req_l = req.lower()
    tpatch = rec.get("test_patch") or ""
    patch = rec.get("patch") or ""
    f2p = parse_json_list(rec.get("fail_to_pass") or rec.get("FAIL_TO_PASS"))
    spec_ids = identifiers(spec)
    test_ids = identifiers(tpatch)
    for name in f2p:
        test_ids |= identifiers(name)
    lits = _string_lits(tpatch)
    missing_lits = [s for s in lits if s.lower() not in spec_l]
    n_lits = max(len(lits), 1)
    prompt_missing = [s for s in lits if s.lower() not in prompt_l]
    req_pins = [s for s in prompt_missing if s.lower() in req_l]
    prompt_ids = identifiers(prompt)
    prompt_only_frac = (len(test_ids - prompt_ids) / max(len(test_ids), 1)) if test_ids else 0.0
    defers = 1.0 if any(
        w in req_l
        for w in (
            "enforced by the tests",
            "exact spacing",
            "mandatory examples",
            "exactly as in the tests",
            "must match the tests",
        )
    ) else 0.0
    f2p_not = 0.0
    if f2p:
        f2p_not = sum(1 for n in f2p if n.split(".")[-1] not in spec and n not in spec) / len(f2p)
    pstats = diff_stats(patch)
    gold_files = []
    for line in (patch or "").splitlines():
        if line.startswith("diff --git") and " b/" in line:
            gold_files.append(line.split(" b/", 1)[-1].strip())
    unmentioned = sum(1 for f in gold_files if f.split("/")[-1] not in spec and f not in tpatch)
    spec_len = max(len(spec), 1)
    test_len = max(len(tpatch), 1)
    conflict = 0.0
    for a, b in (("single space", "  "), ("one space", "  "), ("leading space", "  ")):
        if a in spec_l and b in tpatch:
            conflict = 1.0
    if "exactly one" in spec_l and ("== 2" in tpatch or "toBe(2)" in tpatch):
        conflict = 1.0

    family_strict = min(
        1.0,
        0.35 * (len(missing_lits) / n_lits)
        + 0.20 * cheap["test_has_match_kw"]
        + 0.15 * cheap["test_has_exact_string_literal"]
        + 0.15 * (1.0 if WHITESPACE_ASSERT_RE.search(tpatch) else 0.0)
        + 0.15 * (1.0 if EXACT_JSON_RE.search(tpatch) else 0.0),
    )
    family_underspec = min(
        1.0,
        0.45 * (len(test_ids - spec_ids) / max(len(test_ids), 1))
        + 0.35 * f2p_not
        + 0.20 * min(test_len / spec_len / 20.0, 1.0),
    )
    family_cov = min(
        1.0,
        0.40 * (unmentioned / max(len(gold_files), 1))
        + 0.35 * min(cheap["gold_to_test_line_ratio"] / 8.0, 1.0)
        + 0.25 * (1.0 if cheap["n_fail_to_pass"] <= 1 else 0.0),
    )
    family_mis = min(1.0, 0.70 * conflict + 0.30 * cheap["test_has_exact_string_literal"] * family_underspec)

    cheap_risk = (
        0.35 * family_strict
        + 0.30 * family_underspec
        + 0.20 * family_cov
        + 0.15 * family_mis
    )
    # OpenAI audited the *prompt* against hidden tests, not Scale's
    # requirements field (which often restates test pins).
    openai_style_risk = min(
        1.0,
        0.45 * (len(prompt_missing) / n_lits)
        + 0.20 * cheap["test_has_match_kw"]
        + 0.15 * (1.0 if WHITESPACE_ASSERT_RE.search(tpatch) or EXACT_JSON_RE.search(tpatch) else 0.0)
        + 0.10 * prompt_only_frac
        + 0.10 * defers,
    )
    return {
        **{k: cheap[k] for k in cheap},
        "strict_exact_lits_not_in_spec": float(len(missing_lits)),
        "strict_exact_lit_frac": float(len(missing_lits) / n_lits),
        "strict_match_kw": cheap["test_has_match_kw"],
        "strict_warning_assert": cheap["test_has_warning_assert"],
        "strict_whitespace_assert": 1.0 if WHITESPACE_ASSERT_RE.search(tpatch) else 0.0,
        "strict_json_exact": 1.0 if EXACT_JSON_RE.search(tpatch) else 0.0,
        "underspec_test_only_id_frac": float(len(test_ids - spec_ids) / max(len(test_ids), 1)),
        "underspec_f2p_not_in_spec_frac": float(f2p_not),
        "underspec_spec_to_test_ratio": float(spec_len / test_len),
        "coverage_gold_files_unmentioned": float(unmentioned),
        "coverage_gold_to_test_line_ratio": cheap["gold_to_test_line_ratio"],
        "coverage_few_fail_to_pass": 1.0 if cheap["n_fail_to_pass"] <= 1 else 0.0,
        "misleading_conflict_tokens": conflict,
        "prompt_missing_lit_frac": float(len(prompt_missing) / n_lits),
        "prompt_test_only_id_frac": float(prompt_only_frac),
        "requirements_pin_prompt_gap": float(len(req_pins) / n_lits),
        "requirements_defers_to_tests": defers,
        "family_strict": family_strict,
        "family_underspec": family_underspec,
        "family_low_coverage": family_cov,
        "family_misleading": family_mis,
        "cheap_risk": cheap_risk,
        "openai_style_risk": openai_style_risk,
    }


def family_flags(feats: dict[str, float], threshold: float = 0.45) -> list[str]:
    scores = {
        "overly_strict_tests": feats["family_strict"],
        "underspecified_prompts": feats["family_underspec"],
        "low_coverage_tests": feats["family_low_coverage"],
        "misleading_prompt": feats["family_misleading"],
    }
    return [k for k, v in scores.items() if v >= threshold]


def suspected_family(feats: dict[str, float], threshold: float = 0.45) -> str:
    """Argmax only if it clears a floor. Otherwise 'none'.

    Without a floor, underspec wins almost every row and the family
    counts are not a reconstruction of OpenAI's taxonomy.
    """
    flags = family_flags(feats, threshold)
    if not flags:
        return "none"
    scores = {
        "overly_strict_tests": feats["family_strict"],
        "underspecified_prompts": feats["family_underspec"],
        "low_coverage_tests": feats["family_low_coverage"],
        "misleading_prompt": feats["family_misleading"],
    }
    return max(flags, key=lambda k: scores[k])
