"""EvalQA-Gold row shape.

One row is one task. The primary statistical variable is material invalidity,
stored as `human_validity_label`. Everything else is either provenance or
evidence used to allocate review, not the estimand.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ValidityLabel = Literal["valid", "invalid", "ambiguous", "pending"]
LabelProvenance = Literal[
    "EXPERT_VERIFIED",
    "AUTHOR_ACKNOWLEDGED_FIX",
    "PENDING_HUMAN",
    "HISTORICAL_MAINTENANCE",
]


@dataclass
class EvidenceVector:
    """Machine-generated signals. Missing keys mean the check was not run."""

    oracle_pass: bool | None = None
    nop_fail: bool | None = None
    environment_builds: bool | None = None
    evaluation_deterministic: bool | None = None
    reference_changes_behavior: bool | None = None
    independent_test_agreement: bool | None = None
    mutation_kill_rate: float | None = None
    fuzz_agreement: bool | None = None
    metamorphic_hold: bool | None = None
    exploit_probe_rejected: bool | None = None
    llm_audit: dict[str, Any] | None = None
    static_checks: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class GoldRow:
    task_id: str
    benchmark: str
    benchmark_version: str
    provenance: LabelProvenance
    language: str | None = None
    repository: str | None = None
    domain: str | None = None
    human_validity_label: ValidityLabel = "pending"
    human_label_provenance: LabelProvenance | None = None
    human_severity: dict[str, Any] | None = None
    n_raters: int | None = None
    difficulty: str | None = None
    evidence: EvidenceVector = field(default_factory=EvidenceVector)
    artifacts: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def material_invalid_from_swe_filter(
    *,
    filter_out: bool,
    underspecified: float,
    false_negative: float,
    other_major_issues: float,
) -> tuple[ValidityLabel, dict[str, Any]]:
    """Map OpenAI SWE-bench Verified ensemble labels onto the binary estimand.

    OpenAI discarded a sample when any of underspecification, FAIL_TO_PASS
    unfairness, or other major issues had ensemble severity >= 2, or when
    `filter_out` was set. That is a conservative 2024 protocol, not a 2026
    residual-error label. Keep both the binary label and the raw severities.
    """

    severity = {
        "underspecified": underspecified,
        "false_negative": false_negative,
        "other_major_issues": other_major_issues,
        "filter_out": filter_out,
        "protocol": "openai-swe-bench-verified-2024-conservative",
    }
    if filter_out:
        return "invalid", severity
    return "valid", severity
