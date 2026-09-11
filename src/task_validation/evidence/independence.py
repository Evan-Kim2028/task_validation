"""Track evidence source. Five copies of one check are not five checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Source = Literal[
    "official_verifier",
    "oracle_derived",
    "independent_probe",
    "mutation",
    "metamorphic",
    "environment_perturbation",
    "static",
    "job_archive",
]


@dataclass
class CheckResult:
    name: str
    source: Source
    passed: bool | None
    detail: dict

    def to_dict(self) -> dict:
        return asdict(self)


def pairwise_agreement(checks: list[CheckResult]) -> list[dict]:
    out = []
    binary = [(c.name, c.source, c.passed) for c in checks if c.passed is not None]
    for i in range(len(binary)):
        for j in range(i + 1, len(binary)):
            n1, s1, p1 = binary[i]
            n2, s2, p2 = binary[j]
            out.append(
                {
                    "a": n1,
                    "b": n2,
                    "source_a": s1,
                    "source_b": s2,
                    "agree": int(p1 == p2),
                    "same_source": s1 == s2,
                }
            )
    return out
