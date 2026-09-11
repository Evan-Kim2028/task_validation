"""Verifier discrimination *profile* — do not collapse to one number.

Static stand-in until counterfactual implementations are executed.
Executed Harbor runs fill the rate fields; otherwise they stay null.
"""

from __future__ import annotations

from task_validation.evidence.causality import change_causality
from task_validation.evidence.provenance import contract_provenance


def discrimination_profile(rec: dict, executed: dict | None = None) -> dict:
    caus = change_causality(rec)
    prov = contract_provenance(rec)
    executed = executed or {}
    return {
        "n_revert_mutants_available": caus.n_gold_hunks,
        "n_unwitnessed_reverts": caus.n_hunks_unwitnessed,
        "n_gold_only_constraints": int(
            round(prov["gold_only_frac"] * max(prov["n_constraints"], 1))
        ),
        "correct_accept_rate": executed.get("correct_accept_rate"),  # reference
        "legitimate_variant_accept_rate": executed.get("legitimate_variant_accept_rate"),
        "incorrect_reject_rate": executed.get("incorrect_reject_rate"),
        "false_accept_rate": executed.get("false_accept_rate"),
        "false_reject_rate": executed.get("false_reject_rate"),
        "executed": bool(executed),
        # Untrained risk: unwitnessed gold + gold-only asserts (narrow tests)
        "risk": min(
            1.0,
            0.5 * caus.unwitnessed_hunk_frac + 0.5 * prov["gold_only_frac"],
        ),
    }
