"""Content features of a task's text artifacts (doc 62).

No taste model in this repository has used task text directly. The
doc-40 artifact features count sizes and overlaps; this module reads the
instruction, the reference patch, and the test patch as text and derives
a fixed feature list from them:

- instruction: token count, sentence count, mean sentence length in
  tokens, imperative openers, fenced code blocks (presence and count),
  expected-output examples, acceptance-criteria phrasings, reproduction
  steps, error text, named files and the fraction of them the reference
  patch touches.
- test patch: test count, assertion count, mean assertion length in
  tokens, fraction of assertions comparing a literal.
- reference patch: size in lines and files, and the ratio of test lines
  to reference lines.

The extractor accepts either a unified diff (SWE-bench ``patch`` and
``test_patch`` columns) or a plain file blob plus the file list (Harbor
task directories, where ``solution/`` and ``tests/`` are directories, not
diffs). A field the source does not carry yields None, never a zero, so
missingness stays visible per source.

Tokenization is the decontam word tokenizer (``decontam.tokenize``).
Everything here is descriptive; no label is imputed and nothing enters a
bound (doc 43).

Run: ``python -m task_validation.evidence.content_features run`` writes
``data/gold/content_features.jsonl`` and a summary.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from task_validation.evidence.decontam import harbor_fields, swe_fields, tokenize
from task_validation.evidence.diffstats import diff_stats
from task_validation.evidence.footprint import (
    _dir_blob,
    load_jsonl,
    write_json,
    write_jsonl,
)
from task_validation.evidence.spec_atoms import ASSERT_LINE_RE, STRING_RE

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD = REPO_ROOT / "data" / "gold"
EVAL_TASKS_ROOT = Path("/home/evan/Documents/eval_tasks")

SWE_PARQUET = REPO_ROOT / "data" / "raw" / "swe-bench" / "test.parquet"
SWE_LABELS_PATH = GOLD / "swe_taste_labels.jsonl"
LOT001_ROOT = EVAL_TASKS_ROOT / "lots" / "lot-001"
OUT_PATH = GOLD / "content_features.jsonl"
OUT_SUMMARY_PATH = GOLD / "content_features.summary.json"

PROTOCOL = "content_features.text_artifacts.2026-09-14"

CONTENT_FEATURE_NAMES = (
    "n_instr_tokens",
    "n_instr_sentences",
    "instr_mean_sentence_tokens",
    "n_instr_imperative_openers",
    "has_instr_code_block",
    "n_instr_code_blocks",
    "has_instr_expected_output",
    "n_instr_acceptance_phrases",
    "has_instr_repro_steps",
    "has_instr_error_text",
    "n_instr_named_files",
    "instr_named_files_touched_frac",
    "n_tests",
    "n_assert_lines",
    "assert_mean_tokens",
    "assert_literal_frac",
    "ref_patch_n_lines",
    "ref_patch_n_files",
    "test_to_ref_line_ratio",
)

# Count-like content features take log1p on the model scale, the same
# convention footprint.py and typicality.py apply to heavy-tailed counts.
CONTENT_LOG1P = frozenset(
    {
        "n_instr_tokens",
        "n_instr_sentences",
        "instr_mean_sentence_tokens",
        "n_instr_imperative_openers",
        "n_instr_code_blocks",
        "n_instr_acceptance_phrases",
        "n_instr_named_files",
        "n_tests",
        "n_assert_lines",
        "assert_mean_tokens",
        "ref_patch_n_lines",
        "ref_patch_n_files",
    }
)

# Sentence openers that read as imperatives. Fixed list, matched on the
# first token of a sentence after bullet markers are stripped.
IMPERATIVE_VERBS = frozenset(
    {
        "add", "adjust", "allow", "avoid", "change", "check", "compute",
        "convert", "correct", "create", "deprecate", "disable", "enable",
        "ensure", "extend", "fail", "fix", "handle", "implement",
        "improve", "introduce", "keep", "make", "modify", "move",
        "patch", "prevent", "produce", "provide", "raise", "refactor",
        "reject", "remove", "rename", "repair", "replace", "restore",
        "return", "set", "stop", "support", "update", "upgrade", "use",
        "validate", "verify", "write",
    }
)

_SENTENCE_SPLIT_RE = re.compile(r"(?:[.!?]+[\"')\]]*\s+)|(?:\n+)")
_BULLET_PREFIX_RE = re.compile(r"^[\s>*+-]*(?:\d+[.)]\s+)?")
_FENCE_RE = re.compile(r"(?m)^\s*(```|~~~)")
_EXPECTED_OUTPUT_RE = re.compile(
    r"(expected\s+(output|result|behaviou?r)|^outputs?:|should\s+(output|return|print|produce)|>>>|\bactual\b\s*(output|result)?\s*:)",
    re.I | re.M,
)
_ACCEPTANCE_RE = re.compile(
    r"(acceptance criteria|the\s+(fix|solution|patch|implementation|change)\s+(should|must|needs to)|\bshould\b|\bmust\b|\bshall\b|needs to|is expected to|are expected to|ensure(s|d)?\s+that|verify that|required to|expected behaviou?r|correct behaviou?r)",
    re.I,
)
_REPRO_RE = re.compile(
    r"(steps to reproduce|to reproduce|reproduction|minimal\s+(working\s+)?(example|repro)|reproduce the)",
    re.I,
)
_ERROR_TEXT_RE = re.compile(
    r"(Traceback \(most recent call last\)|^[\w.]*Error\b|^\s*[\w.]*Exception\b|\bFAILED\b|stack trace|error message)",
    re.M,
)
# A named file is a path with a code-ish extension, or a bare filename
# with one. Trailing punctuation is stripped after the match.
_FILE_EXT = (
    "py|pyx|pxd|c|cc|cpp|cxx|h|hpp|js|jsx|ts|tsx|mjs|sh|bash|zsh|toml|yaml|yml|"
    "json|jsonl|md|rst|txt|cfg|ini|html|css|sql|java|rb|go|rs|f90|f95|f|ipynb|"
    "csv|tsv|xml|jl|scala|php|pl|lua|R|r|m|jl"
)
_NAMED_FILE_RE = re.compile(
    rf"(?:[\w.~@-]+/)+[\w.@-]+\.(?:{_FILE_EXT})\b|\b[\w@-]+\.(?:{_FILE_EXT})\b"
)
_TEST_DEF_RE = re.compile(
    r"(?m)^\s*(?:async\s+)?def\s+test\w*|^\s*(?:it|test)\s*\(|^\s*func\s+Test\w*|^\s*test\w*\s*\(\s*\)\s*\{"
)
_NUMERIC_LITERAL_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_ADDED_LINE_RE = re.compile(r"(?m)^\+(?!\+)")


def added_lines(diff_text: str) -> str:
    """Added lines of a unified diff, ``+`` markers stripped."""
    return "\n".join(
        line[1:] for line in (diff_text or "").splitlines() if _ADDED_LINE_RE.match(line)
    )


def diff_files(diff_text: str) -> list[str]:
    """Files a unified diff touches, from ``diff --git`` headers."""
    files = []
    for line in (diff_text or "").splitlines():
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 4:
                name = parts[-1]
                files.append(name[2:] if name.startswith("b/") else name)
    return files


def split_sentences(text: str) -> list[str]:
    """Split on sentence enders and newlines; bullets count as sentences."""
    out = []
    for chunk in _SENTENCE_SPLIT_RE.split(text or ""):
        chunk = _BULLET_PREFIX_RE.sub("", chunk).strip()
        if chunk:
            out.append(chunk)
    return out


def _count_imperatives(sentences: list[str]) -> int:
    n = 0
    for sent in sentences:
        toks = tokenize(sent)
        if toks and toks[0] in IMPERATIVE_VERBS:
            n += 1
    return n


def _count_code_blocks(text: str) -> int:
    n_fences = len(_FENCE_RE.findall(text or ""))
    return (n_fences + 1) // 2


def _named_files(text: str) -> set[str]:
    out = set()
    for m in _NAMED_FILE_RE.finditer(text or ""):
        out.add(m.group(0).rstrip(".,;:)"))
    return out


def _basename(name: str) -> str:
    return name.replace("\\", "/").rsplit("/", 1)[-1]


def _touched_fraction(named: set[str], ref_files: list[str]) -> float | None:
    """Share of instruction-named files the reference touches. A named
    file counts as touched when its full path is a suffix of a reference
    path, or its basename matches a reference basename."""
    if not named:
        return None
    ref_set = set(ref_files)
    ref_bases = {_basename(f) for f in ref_files}
    hits = 0
    for name in named:
        norm = name.replace("\\", "/").lstrip("/")
        if norm in ref_set or _basename(norm) in ref_bases:
            hits += 1
            continue
        if any(r.endswith(norm) or norm.endswith(r) for r in ref_set):
            hits += 1
    return hits / len(named)


def _assert_lines(text: str) -> list[str]:
    return [line for line in (text or "").splitlines() if ASSERT_LINE_RE.search(line)]


def _assert_is_literal(line: str) -> bool:
    """An assertion compares a literal when it carries a quoted string or
    a bare numeric literal next to a comparison or argument boundary."""
    if STRING_RE.search(line):
        return True
    if _NUMERIC_LITERAL_RE.search(line):
        return True
    return False


def extract_content_features(
    instruction: str | None,
    reference: str | None,
    tests: str | None,
    *,
    reference_files: list[str] | None = None,
    reference_is_diff: bool = True,
    tests_is_diff: bool = True,
) -> dict:
    """The 19 content features for one task.

    ``reference`` and ``tests`` are unified diffs when ``*_is_diff`` and
    plain concatenated file text otherwise (Harbor ``solution/`` and
    ``tests/`` directories). ``reference_files`` carries the directory
    file list for the non-diff case; for diffs the file list is parsed
    from the diff itself. A missing field yields None features, never
    zeros.
    """
    feats = {name: None for name in CONTENT_FEATURE_NAMES}

    instr = instruction or ""
    ref = reference or ""
    tes = tests or ""
    ref_files = (
        list(reference_files) if reference_files is not None else diff_files(ref)
    )
    ref_stats = diff_stats(ref) if reference_is_diff else None
    ref_n_lines = (
        ref_stats["n_changed_lines"]
        if ref_stats is not None
        else (sum(1 for _ in ref.splitlines()) if ref else 0)
    )
    ref_n_files = len(set(ref_files))
    test_text = added_lines(tes) if tests_is_diff else tes
    test_stats = diff_stats(tes) if tests_is_diff else None
    test_n_lines = (
        test_stats["n_changed_lines"]
        if test_stats is not None
        else (sum(1 for _ in tes.splitlines()) if tes else 0)
    )

    if instr:
        sentences = split_sentences(instr)
        n_tok = len(tokenize(instr))
        named = _named_files(instr)
        feats.update(
            {
                "n_instr_tokens": float(n_tok),
                "n_instr_sentences": float(len(sentences)),
                "instr_mean_sentence_tokens": (
                    float(n_tok) / len(sentences) if sentences else None
                ),
                "n_instr_imperative_openers": float(_count_imperatives(sentences)),
                "has_instr_code_block": 1.0 if _count_code_blocks(instr) else 0.0,
                "n_instr_code_blocks": float(_count_code_blocks(instr)),
                "has_instr_expected_output": (
                    1.0 if _EXPECTED_OUTPUT_RE.search(instr) else 0.0
                ),
                "n_instr_acceptance_phrases": float(
                    len(_ACCEPTANCE_RE.findall(instr))
                ),
                "has_instr_repro_steps": 1.0 if _REPRO_RE.search(instr) else 0.0,
                "has_instr_error_text": 1.0 if _ERROR_TEXT_RE.search(instr) else 0.0,
                "n_instr_named_files": float(len(named)),
                "instr_named_files_touched_frac": _touched_fraction(named, ref_files),
            }
        )

    if tes:
        asserts = _assert_lines(test_text)
        n_tests = len(_TEST_DEF_RE.findall(test_text))
        tok_lens = [len(tokenize(line)) for line in asserts]
        feats.update(
            {
                "n_tests": float(n_tests),
                "n_assert_lines": float(len(asserts)),
                "assert_mean_tokens": (
                    sum(tok_lens) / len(tok_lens) if tok_lens else None
                ),
                "assert_literal_frac": (
                    sum(1 for line in asserts if _assert_is_literal(line)) / len(asserts)
                    if asserts
                    else None
                ),
            }
        )

    if ref:
        feats["ref_patch_n_lines"] = float(ref_n_lines)
        feats["ref_patch_n_files"] = float(ref_n_files)

    if tes and ref:
        feats["test_to_ref_line_ratio"] = float(test_n_lines) / max(
            float(ref_n_lines), 1.0
        )

    return feats


# ---------------------------------------------------------------------------
# Population assembly
# ---------------------------------------------------------------------------


def swe_content_rows(parquet_path: Path = SWE_PARQUET) -> list[dict]:
    """Content features for the 1,699 annotated SWE-bench instances."""
    import pandas as pd

    ids = {r["task_id"] for r in load_jsonl(SWE_LABELS_PATH)}
    df = pd.read_parquet(parquet_path)
    df = df[df["instance_id"].isin(ids)]
    rows = []
    for rec in df.itertuples(index=False):
        fields = swe_fields(
            {
                "problem_statement": rec.problem_statement,
                "test_patch": rec.test_patch,
                "patch": rec.patch,
            }
        )
        feats = extract_content_features(
            fields["instruction"],
            fields["solution"],
            fields["tests"],
            reference_is_diff=True,
            tests_is_diff=True,
        )
        rows.append(
            {
                "task_id": rec.instance_id,
                "source": "swe",
                "features": feats,
            }
        )
    rows.sort(key=lambda r: r["task_id"])
    return rows


def _dir_file_list(root: Path) -> list[str]:
    out = []
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file() and not any(
            part in {".git", "__pycache__"} for part in p.parts
        ):
            out.append(p.relative_to(root).as_posix())
    return out


def lot001_content_rows(lot_root: Path = LOT001_ROOT) -> list[dict]:
    """Content features for the 20 lot-001 Harbor task directories. The
    tests blob uses the same test-file filter as the doc-40 footprint so
    helper and reference subtrees under ``tests/`` do not count as tests."""
    rows = []
    tasks_root = lot_root / "tasks"
    for task_dir in sorted(p for p in tasks_root.iterdir() if p.is_dir()):
        fields = harbor_fields(task_dir)
        _n_test, tests_blob, _tb = _dir_blob(task_dir / "tests", "tests")
        _n_sol, sol_blob, _sb = _dir_blob(task_dir / "solution", "solution")
        feats = extract_content_features(
            fields.get("instruction"),
            sol_blob,
            tests_blob,
            reference_files=_dir_file_list(task_dir / "solution"),
            reference_is_diff=False,
            tests_is_diff=False,
        )
        rows.append(
            {
                "task_id": task_dir.name,
                "source": "lot001",
                "features": feats,
            }
        )
    return rows


def unavailable_by_source(rows: list[dict]) -> dict:
    """Per source: features with no observed value on any task, and the
    per-task count of missing features."""
    out: dict = {}
    by_source: dict[str, list[dict]] = {}
    for r in rows:
        by_source.setdefault(r["source"], []).append(r)
    for src, src_rows in sorted(by_source.items()):
        never = [
            f
            for f in CONTENT_FEATURE_NAMES
            if all(r["features"].get(f) is None for r in src_rows)
        ]
        partial = {
            f: sum(1 for r in src_rows if r["features"].get(f) is None)
            for f in CONTENT_FEATURE_NAMES
        }
        out[src] = {
            "n_tasks": len(src_rows),
            "features_never_observed": never,
            "n_missing_by_feature": {
                f: n for f, n in partial.items() if n
            },
        }
    return out


def run() -> dict:
    rows = swe_content_rows() + lot001_content_rows()
    write_jsonl(OUT_PATH, rows)
    summary = {
        "protocol": PROTOCOL,
        "code": "src/task_validation/evidence/content_features.py",
        "n_rows": len(rows),
        "features": list(CONTENT_FEATURE_NAMES),
        "unavailable_by_source": unavailable_by_source(rows),
        "inputs": {
            "swe_parquet": str(SWE_PARQUET),
            "swe_labels": str(SWE_LABELS_PATH),
            "lot_root": str(LOT001_ROOT),
        },
        "outputs": {"rows": str(OUT_PATH)},
    }
    write_json(OUT_SUMMARY_PATH, summary)
    return summary


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "run":
        summary = run()
        for src, s in summary["unavailable_by_source"].items():
            print(
                f"[{src}] n={s['n_tasks']} never_observed={s['features_never_observed']}"
            )
    else:
        print("usage: python -m task_validation.evidence.content_features run")


if __name__ == "__main__":
    main()
