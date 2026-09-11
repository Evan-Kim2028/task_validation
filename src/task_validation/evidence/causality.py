"""Change causality: does the verifier respond to the gold behavioral change?

Static first version. Execution (fail-before / pass-after) is a later fill.
This is file/hunk structure, not token overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from task_validation.evidence.diffstats import file_hunks, parse_json_list


def gold_files(diff: str) -> list[str]:
    files = []
    for line in (diff or "").splitlines():
        if line.startswith("diff --git") and " b/" in line:
            files.append(line.split(" b/", 1)[-1].strip())
    return files


def test_files(diff: str) -> list[str]:
    return [f for f in gold_files(diff) if _looks_like_test(f)]


def _looks_like_test(path: str) -> bool:
    name = path.replace("\\", "/").split("/")[-1].lower()
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith("_tests.py")
        or "/tests/" in path.replace("\\", "/").lower()
        or "/test/" in path.replace("\\", "/").lower()
    )


def _stem(path: str) -> str:
    name = path.replace("\\", "/").split("/")[-1]
    name = re.sub(r"\.(py|js|ts|go|java)$", "", name, flags=re.I)
    name = re.sub(r"^test_", "", name, flags=re.I)
    name = re.sub(r"_test$", "", name, flags=re.I)
    return name.lower()


def hunk_has_test_witness(gold_path: str, test_paths: list[str], f2p: list[str]) -> bool:
    g = _stem(gold_path)
    if not g:
        return False
    for t in test_paths:
        if g and (g in t.lower() or _stem(t) == g):
            return True
    blob = " ".join(f2p).lower()
    return g in blob


@dataclass
class CausalityProfile:
    n_gold_files: int
    n_gold_hunks: int
    n_test_files_in_test_patch: int
    n_fail_to_pass: int
    n_pass_to_pass: int
    n_hunks_with_witness: int
    n_hunks_unwitnessed: int
    declared_f2p_nonempty: bool
    executed: bool = False

    @property
    def unwitnessed_hunk_frac(self) -> float:
        d = max(self.n_gold_hunks, 1)
        return self.n_hunks_unwitnessed / d

    def risk(self) -> float:
        """Higher = gold change has weaker test witness. Untrained."""
        parts = [self.unwitnessed_hunk_frac]
        if not self.declared_f2p_nonempty:
            parts.append(1.0)
        if self.n_test_files_in_test_patch == 0:
            parts.append(1.0)
        return sum(parts) / len(parts)

    def to_dict(self) -> dict:
        return {
            "n_gold_files": self.n_gold_files,
            "n_gold_hunks": self.n_gold_hunks,
            "n_test_files_in_test_patch": self.n_test_files_in_test_patch,
            "n_fail_to_pass": self.n_fail_to_pass,
            "n_pass_to_pass": self.n_pass_to_pass,
            "n_hunks_with_witness": self.n_hunks_with_witness,
            "n_hunks_unwitnessed": self.n_hunks_unwitnessed,
            "unwitnessed_hunk_frac": self.unwitnessed_hunk_frac,
            "declared_f2p_nonempty": self.declared_f2p_nonempty,
            "executed_fail_before_pass_after": self.executed,
            "risk": self.risk(),
        }


def change_causality(rec: dict) -> CausalityProfile:
    patch = rec.get("patch") or ""
    tpatch = rec.get("test_patch") or ""
    f2p = parse_json_list(rec.get("FAIL_TO_PASS") or rec.get("fail_to_pass"))
    p2p = parse_json_list(rec.get("PASS_TO_PASS") or rec.get("pass_to_pass"))
    g_files = [f for f in gold_files(patch) if not _looks_like_test(f)]
    t_files = test_files(tpatch) or [f for f in gold_files(tpatch) if _looks_like_test(f)]
    hunks = file_hunks(patch)
    prod_hunks = {f: n for f, n in hunks.items() if not _looks_like_test(f)}
    n_h = sum(prod_hunks.values()) or 0
    witnessed = 0
    for f, n in prod_hunks.items():
        if hunk_has_test_witness(f, t_files, f2p):
            witnessed += n
    return CausalityProfile(
        n_gold_files=len(g_files),
        n_gold_hunks=n_h,
        n_test_files_in_test_patch=len(t_files),
        n_fail_to_pass=len(f2p),
        n_pass_to_pass=len(p2p),
        n_hunks_with_witness=witnessed,
        n_hunks_unwitnessed=max(n_h - witnessed, 0),
        declared_f2p_nonempty=bool(f2p),
        executed=False,
    )
