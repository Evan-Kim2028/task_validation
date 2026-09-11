"""Contract atoms: stated vs enforced. Not a bag of correlates.

An atom is a concrete, checkable unit of behavior: identifier, error type,
numeric threshold, format literal, ordering constraint, or error action.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from task_validation.evidence.diffstats import IDENT_RE

ERROR_RE = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:Error|Exception|Warning|Fault))\b")
CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(")
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
STRING_RE = re.compile(r"""(?<!\\)(['"])(.{4,}?)\1""")
ORDER_RE = re.compile(
    r"\b(in order|before|after|sorted|ascending|descending|left.?to.?right|stable sort)\b",
    re.I,
)
ERROR_ACT_RE = re.compile(
    r"\b(raise|throws?|must fail|should fail|reject|return none|return null|errno)\b",
    re.I,
)
SIDE_RE = re.compile(
    r"\b(write|persist|emit|log|delete|create file|chmod|mkdir|network|http)\b",
    re.I,
)

STOP = {
    "the", "and", "for", "that", "this", "with", "from", "not", "are", "was",
    "were", "have", "has", "had", "but", "you", "all", "can", "def", "class",
    "return", "import", "test", "assert", "self", "none", "true", "false",
    "int", "str", "list", "dict", "print", "pytest", "unittest", "should",
    "would", "could", "must", "when", "then", "than", "into", "also", "just",
    "like", "only", "some", "them", "they", "does", "done", "make", "used",
    "using", "will", "been", "being", "each", "more", "such", "same", "both",
}


def _keep_ident(tok: str) -> bool:
    if tok.lower() in STOP or len(tok) < 3:
        return False
    if tok.lower() in {"args", "kwargs", "main", "data", "value", "result", "output"}:
        return False
    return True


@dataclass
class AtomSet:
    identifiers: set[str] = field(default_factory=set)
    errors: set[str] = field(default_factory=set)
    numbers: set[str] = field(default_factory=set)
    literals: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)
    ordering: bool = False
    error_action: bool = False
    side_effect: bool = False

    def contract_tokens(self) -> set[str]:
        """Pins a verifier can actually fail on: literals, errors, numbers, API calls.

        Fixture identifiers (path, strip, self) are not the contract.
        """
        out = {x.lower() for x in self.literals}
        out |= {x.lower() for x in self.errors}
        out |= {x.lower() for x in self.numbers if len(x) >= 2}
        for c in self.calls:
            if "_" in c or (c[0].isupper() and len(c) > 3):
                out.add(c.lower())
        if self.ordering:
            out.add("__ordering__")
        if self.error_action:
            out.add("__error_action__")
        return out

    def all_tokens(self) -> set[str]:
        out = set()
        out |= {x.lower() for x in self.identifiers}
        out |= {x.lower() for x in self.errors}
        out |= {x.lower() for x in self.numbers}
        out |= {x.lower() for x in self.literals}
        out |= {x.lower() for x in self.calls}
        if self.ordering:
            out.add("__ordering__")
        if self.error_action:
            out.add("__error_action__")
        if self.side_effect:
            out.add("__side_effect__")
        return out

    def count(self) -> int:
        return len(self.all_tokens())


def extract_atoms(text: str) -> AtomSet:
    text = text or ""
    atoms = AtomSet()
    for tok in IDENT_RE.findall(text):
        if _keep_ident(tok):
            atoms.identifiers.add(tok)
    atoms.errors |= set(ERROR_RE.findall(text))
    atoms.numbers |= set(NUMBER_RE.findall(text))
    for _, body in STRING_RE.findall(text):
        if any(ch.isalpha() or ch in " |*_." for ch in body):
            atoms.literals.add(body.strip()[:80])
    for c in CALL_RE.findall(text):
        if _keep_ident(c):
            atoms.calls.add(c)
    atoms.ordering = bool(ORDER_RE.search(text))
    atoms.error_action = bool(ERROR_ACT_RE.search(text))
    atoms.side_effect = bool(SIDE_RE.search(text))
    return atoms


def alignment(stated: AtomSet, enforced: AtomSet) -> dict:
    s = stated.all_tokens()
    e = enforced.all_tokens()
    ungrounded = e - s
    untested = s - e
    n_e = max(len(e), 1)
    n_s = max(len(s), 1)
    return {
        "n_stated": len(s),
        "n_enforced": len(e),
        "n_enforced_ungrounded": len(ungrounded),
        "n_stated_untested": len(untested),
        "enforced_ungrounded_rate": len(ungrounded) / n_e,
        "stated_untested_rate": len(untested) / n_s,
        "ungrounded_sample": sorted(ungrounded)[:12],
        "untested_sample": sorted(untested)[:12],
    }


ASSERT_LINE_RE = re.compile(
    r"assert|expect\(|toBe|toEqual|toStrictEqual|pytest\.raises|self\.assert|raises\(",
    re.I,
)


def assertion_slice(text: str) -> str:
    """Keep lines that look like checks, not fixtures and helpers."""
    keep = []
    for line in (text or "").splitlines():
        if ASSERT_LINE_RE.search(line):
            keep.append(line)
    return "\n".join(keep)


def spec_from_record(rec: dict) -> dict:
    """Prompt = issue text. Enforced = tests + fail_to_pass names.

    Requirements/interface are recorded separately so Scale-style pins
    cannot hide a prompt/test gap.
    """
    prompt = rec.get("problem_statement") or rec.get("instruction") or ""
    req = rec.get("requirements") or ""
    interface = rec.get("interface") or ""
    tests = rec.get("test_patch") or rec.get("tests") or ""
    f2p = rec.get("fail_to_pass") or rec.get("FAIL_TO_PASS") or ""
    if not isinstance(f2p, str):
        f2p = " ".join(str(x) for x in f2p)
    stated = extract_atoms(prompt)
    enforced = extract_atoms(assertion_slice(tests) + "\n" + str(f2p))
    extra = extract_atoms(req + "\n" + interface)
    align = alignment(stated, enforced)
    extra_pins = enforced.all_tokens() - stated.all_tokens()
    extra_pins &= extra.all_tokens()
    sc, ec = stated.contract_tokens(), enforced.contract_tokens()
    ungrounded_c = ec - sc
    return {
        "prompt_atoms": {
            "n": stated.count(),
            "n_calls": len(stated.calls),
            "n_errors": len(stated.errors),
            "n_literals": len(stated.literals),
        },
        "enforced_atoms": {
            "n": enforced.count(),
            "n_calls": len(enforced.calls),
            "n_errors": len(enforced.errors),
            "n_literals": len(enforced.literals),
        },
        **align,
        "n_requirements_pin_ungrounded": len(extra_pins),
        "requirements_cover_gap_rate": (
            len(extra_pins) / max(align["n_enforced_ungrounded"], 1)
        ),
        # Direct invariant used as an untrained risk: fraction of test-enforced
        # contract atoms with no prompt grounding.
        "spec_gap": align["enforced_ungrounded_rate"],
        "spec_gap_contract": (len(ungrounded_c) / max(len(ec), 1)),
        "n_enforced_contract": len(ec),
        "n_ungrounded_contract": len(ungrounded_c),
        "coverage_gap": align["stated_untested_rate"],
    }
