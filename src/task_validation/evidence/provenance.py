"""Contract provenance: where each *assertion* is grounded.

Start from the test assertion, then look up the payload in prompt, gold
added lines, or nowhere. Not Jaccard on the whole files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ASSERT_RE = re.compile(
    r"^\s*(assert|self\.assert\w+|expect\(|pytest\.raises|raises\()",
    re.I,
)
RAISES_RE = re.compile(
    r"raises\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)|pytest\.raises\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)",
    re.I,
)
EQ_STR_RE = re.compile(r"""(?:==|!=|toBe|toEqual|match\s*=)\s*(['"])(.{3,}?)\1""")
EQ_NUM_RE = re.compile(r"(?:==|!=|toBe|toEqual)\s*(-?\d+(?:\.\d+)?)")
IMPORT_RE = re.compile(r"^\s+(?:from\s+\S+\s+)?import\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(")

SKIP_CALLS = {
    "assert", "expect", "raises", "range", "len", "str", "int", "list", "dict",
    "print", "isinstance", "hasattr", "getattr", "set", "sorted", "any", "all",
}


@dataclass
class Constraint:
    kind: str
    payload: str
    line: str
    grounding: str  # prompt | gold_change | requirements | nowhere | contradictory


def parse_constraints(test_patch: str) -> list[Constraint]:
    out: list[Constraint] = []
    for raw in (test_patch or "").splitlines():
        line = raw[1:] if raw[:1] in "+-" else raw
        if not ASSERT_RE.search(line) and "pytest.raises" not in line:
            continue
        m = RAISES_RE.search(line)
        if m:
            name = m.group(1) or m.group(2)
            out.append(Constraint("raises", name, line, "nowhere"))
        for _, body in EQ_STR_RE.findall(line):
            out.append(Constraint("eq_literal", body, line, "nowhere"))
        for num in EQ_NUM_RE.findall(line):
            out.append(Constraint("eq_number", num, line, "nowhere"))
        for call in CALL_RE.findall(line):
            if call.lower() not in SKIP_CALLS and len(call) > 3:
                out.append(Constraint("call", call, line, "nowhere"))
    # Gold-only imports in the test patch (get_annotation pattern)
    for name in IMPORT_RE.findall(test_patch or ""):
        if name[0].islower() or "_" in name:
            out.append(Constraint("import_name", name, name, "nowhere"))
    return out


def _contains(hay: str, needle: str) -> bool:
    if not needle:
        return False
    return needle.lower() in (hay or "").lower()


def ground_constraint(c: Constraint, prompt: str, gold_added: str, requirements: str) -> str:
    in_p = _contains(prompt, c.payload)
    in_g = _contains(gold_added, c.payload)
    in_r = _contains(requirements, c.payload)
    if in_p and in_g:
        return "prompt"
    if in_p:
        return "prompt"
    if in_r and not in_p:
        return "requirements"
    if in_g:
        return "gold_change"
    return "nowhere"


def gold_added_lines(patch: str) -> str:
    lines = []
    for line in (patch or "").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
    return "\n".join(lines)


def contract_provenance(rec: dict) -> dict:
    prompt = rec.get("problem_statement") or rec.get("instruction") or ""
    req = rec.get("requirements") or rec.get("interface") or ""
    tests = rec.get("test_patch") or ""
    gold = gold_added_lines(rec.get("patch") or "")
    constraints = parse_constraints(tests)
    counts = {
        "prompt": 0,
        "requirements": 0,
        "gold_change": 0,
        "nowhere": 0,
        "contradictory": 0,
    }
    grounded = []
    for c in constraints:
        g = ground_constraint(c, prompt, gold, req)
        c.grounding = g
        counts[g] = counts.get(g, 0) + 1
        grounded.append({"kind": c.kind, "payload": c.payload[:80], "grounding": g})
    n = max(len(constraints), 1)
    orphaned = counts["nowhere"] / n
    return {
        "n_constraints": len(constraints),
        "counts": counts,
        "orphaned_frac": orphaned,
        "gold_only_frac": counts["gold_change"] / n,
        "requirements_only_frac": counts["requirements"] / n,
        "prompt_frac": counts["prompt"] / n,
        "sample": grounded[:8],
        "risk": orphaned + 0.5 * (counts["gold_change"] / n),
        "executed_trace": False,
    }
