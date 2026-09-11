"""Validity Evidence Vector: bounded invariants, not a feature soup.

Missing primitives stay null. A null is not a pass.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal["not_run", "pass", "fail", "inconclusive"]


@dataclass
class Primitive:
    name: str
    status: Status = "not_run"
    value: float | None = None
    n: int | None = None
    d: int | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PRIMITIVE_NAMES = (
    "specification_sufficiency",
    "positive_control",
    "negative_control",
    "implementation_invariance",
    "mutation_sensitivity",
    "independent_behavior",
    "determinism",
    "environment_integrity",
    "requirement_to_test_coverage",
)


@dataclass
class ValidityEvidenceVector:
    task_id: str
    primitives: dict[str, Primitive] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in PRIMITIVE_NAMES:
            self.primitives.setdefault(name, Primitive(name=name))

    def set(self, name: str, **kwargs: Any) -> None:
        cur = self.primitives[name]
        for k, v in kwargs.items():
            setattr(cur, k, v)

    def untrained_risk(self) -> float:
        """Higher = more likely invalid. Uses only measured primitives.

        Gaps and failed controls push risk up. Passes push it down. Unrun
        primitives do not pretend to be evidence.
        """
        p = self.primitives
        parts = []
        spec = p["specification_sufficiency"]
        if spec.value is not None:
            parts.append(spec.value)
        cov = p["requirement_to_test_coverage"]
        if cov.value is not None:
            parts.append(cov.value)
        for key, fail_is_bad in (
            ("positive_control", True),
            ("negative_control", True),
            ("determinism", True),
            ("environment_integrity", True),
        ):
            st = p[key].status
            if st == "fail":
                parts.append(1.0 if fail_is_bad else 0.0)
            elif st == "pass":
                parts.append(0.0)
        mut = p["mutation_sensitivity"]
        if mut.value is not None:
            parts.append(1.0 - mut.value)  # low kill rate → high risk
        inv = p["implementation_invariance"]
        if inv.value is not None:
            parts.append(inv.value)  # fraction of legit alts rejected
        ind = p["independent_behavior"]
        if ind.value is not None:
            parts.append(1.0 - ind.value)  # disagreement
        if not parts:
            return 0.5
        return sum(parts) / len(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "primitives": {k: v.to_dict() for k, v in self.primitives.items()},
            "untrained_risk": self.untrained_risk(),
            "n_measured": sum(
                1 for v in self.primitives.values() if v.status != "not_run"
            ),
        }


def vev_from_spec(task_id: str, spec: dict) -> ValidityEvidenceVector:
    vev = ValidityEvidenceVector(task_id=task_id)
    gap = float(spec.get("spec_gap_contract", spec["spec_gap"]))
    cov = float(spec["coverage_gap"])
    vev.set(
        "specification_sufficiency",
        status="fail" if gap >= 0.5 else "pass" if gap < 0.25 else "inconclusive",
        value=gap,
        n=spec["n_enforced_ungrounded"],
        d=spec["n_enforced"],
        detail={k: spec[k] for k in spec if k not in {"ungrounded_sample", "untested_sample"}}
        | {
            "ungrounded_sample": spec.get("ungrounded_sample"),
            "untested_sample": spec.get("untested_sample"),
        },
    )
    vev.set(
        "requirement_to_test_coverage",
        status="fail" if cov >= 0.7 else "pass" if cov < 0.4 else "inconclusive",
        value=cov,
        n=spec["n_stated_untested"],
        d=spec["n_stated"],
        detail={"stated_untested_rate": cov},
    )
    return vev
