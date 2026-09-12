"""Intended-label strength for interrogation treatments.

A = mechanically guaranteed
B = strongly justified from task semantics / reference / instruction
C = heuristic
D = unknown

Only A/B enter a future validity-assay. C/D stay in the raw log.
remove_required is C: a verifier failure does not make the treatment a valid negative.
"""

from __future__ import annotations

from task_validation.evidence.interrogate import _mean, discrimination_rates

# family -> (grade, why, intended_justified)
FAMILY_GRADE = {
    "nop": (
        "A",
        "empty agent applies no solution",
        True,
    ),
    "preserve": (
        "A",
        "comment-only change is a no-op relative to the reference script, not an independent correctness claim",
        True,
    ),
    "reference": (
        "B",
        "author/oracle solution; not mechanically guaranteed",
        True,
    ),
    "revert_gold": (
        "B",
        "environment file is the constructed pre-fix state when it differs from solution",
        True,
    ),
    "preserve_equivalent": (
        "B",
        "equivalent rewrite grounded in the instruction (hello-world echo), not tests",
        True,
    ),
    "alter_output": (
        "B",
        "instruction names the required output",
        True,
    ),
    "break_boundary": (
        "B",
        "instruction names the required string; case is a pinned token",
        True,
    ),
    "remove_required": (
        "C",
        "dropping the last apply line is a heuristic; remaining gold may still satisfy the verifier",
        False,
    ),
    "observe": (
        "D",
        "spec-ambiguous; unlabeled on purpose",
        False,
    ),
}


def grade_trial(trial: dict) -> dict:
    family = trial.get("family") or ""
    if trial.get("availability") == "unavailable":
        grade, why, justified = "D", trial.get("unavailable_reason") or "unavailable", False
    else:
        grade, why, justified = FAMILY_GRADE.get(
            family,
            ("D", "unlisted family", False),
        )
    return {
        **trial,
        "label_grade": grade,
        "label_justified": justified,
        "label_grade_reason": why,
        "intended_uncertain": grade in {"C", "D"} or trial.get("intended") in {"observe", "none"},
    }


def assay_rates(trials: list[dict], *, min_grade: str = "B") -> dict:
    """Rates using only treatments at or above min_grade. A > B > C > D."""
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    cap = order.get(min_grade, 1)
    kept = []
    for t in trials:
        g = t.get("label_grade") or grade_trial(t)["label_grade"]
        if order.get(g, 3) <= cap and t.get("intended") in {"accept", "reject"}:
            kept.append(t)
    rates = discrimination_rates(kept)
    rates["min_grade"] = min_grade
    rates["n_trials_in_assay"] = len(kept)
    return rates


def information_vs_reference(rows: list[dict]) -> dict:
    """Does a treatment ever disagree with the reference accept bit?"""
    out: dict[str, dict] = {}
    for rec in rows:
        ref = next((t for t in rec.get("trials") or [] if t.get("family") == "reference"), None)
        if ref is None or ref.get("accepted") is None:
            continue
        ref_bit = bool(ref["accepted"])
        for t in rec["trials"]:
            if t.get("availability") == "unavailable" or t.get("accepted") is None:
                continue
            if t.get("family") == "reference":
                continue
            slot = out.setdefault(
                t["family"],
                {"n": 0, "n_disagree_with_reference": 0, "n_same": 0},
            )
            slot["n"] += 1
            if bool(t["accepted"]) == ref_bit:
                slot["n_same"] += 1
            else:
                slot["n_disagree_with_reference"] += 1
    for slot in out.values():
        slot["disagree_frac"] = slot["n_disagree_with_reference"] / slot["n"] if slot["n"] else None
    return out


def analyze_pilot(rows: list[dict]) -> dict:
    graded = []
    ab_rates = []
    all_rates = []
    n_c_as_negative = 0
    for rec in rows:
        trials = [grade_trial(t) for t in rec.get("trials") or []]
        all_r = discrimination_rates(trials)
        ab = assay_rates(trials, min_grade="B")
        graded.append(
            {
                "task_id": rec.get("task_id"),
                "elapsed_sec_total": rec.get("elapsed_sec_total"),
                "rates_all_executed": {
                    k: all_r[k]
                    for k in (
                        "correct_accept",
                        "variant_accept",
                        "incorrect_reject",
                        "false_accept",
                        "false_reject",
                        "n_executed",
                        "interrogable",
                    )
                },
                "rates_ab_only": {
                    k: ab[k]
                    for k in (
                        "correct_accept",
                        "variant_accept",
                        "incorrect_reject",
                        "false_accept",
                        "false_reject",
                        "n_executed",
                        "interrogable",
                        "n_trials_in_assay",
                    )
                },
                "trials": [
                    {
                        "probe_id": t.get("probe_id"),
                        "family": t.get("family"),
                        "intended": t.get("intended"),
                        "label_source": t.get("label_source"),
                        "label_grade": t.get("label_grade"),
                        "label_justified": t.get("label_justified"),
                        "intended_uncertain": t.get("intended_uncertain"),
                        "label_grade_reason": t.get("label_grade_reason"),
                        "reward": t.get("reward"),
                        "accepted": t.get("accepted"),
                        "elapsed_sec": t.get("elapsed_sec"),
                        "availability": t.get("availability"),
                    }
                    for t in trials
                ],
            }
        )
        all_rates.append(all_r)
        ab_rates.append(ab)
        if any(
            t.get("family") == "remove_required" and t.get("reward") == 1.0
            for t in trials
        ):
            n_c_as_negative += 1

    def mean_key(rs: list[dict], key: str) -> float | None:
        return _mean([r[key] for r in rs if r.get(key) is not None])

    return {
        "n_tasks": len(rows),
        "family_grade": {k: {"grade": v[0], "reason": v[1], "justified": v[2]} for k, v in FAMILY_GRADE.items()},
        "mean_rates_all_executed": {
            "correct_accept": mean_key(all_rates, "correct_accept"),
            "variant_accept": mean_key(all_rates, "variant_accept"),
            "incorrect_reject": mean_key(all_rates, "incorrect_reject"),
            "false_accept": mean_key(all_rates, "false_accept"),
            "false_reject": mean_key(all_rates, "false_reject"),
        },
        "mean_rates_ab_only": {
            "correct_accept": mean_key(ab_rates, "correct_accept"),
            "variant_accept": mean_key(ab_rates, "variant_accept"),
            "incorrect_reject": mean_key(ab_rates, "incorrect_reject"),
            "false_accept": mean_key(ab_rates, "false_accept"),
            "false_reject": mean_key(ab_rates, "false_reject"),
        },
        "n_remove_required_false_accept": n_c_as_negative,
        "information_vs_reference": information_vs_reference(
            [{"trials": g["trials"]} for g in graded]
        ),
        "minimum_battery": ["reference", "nop", "revert_gold"],
        "minimum_battery_note": "preserve_comments tracked reference on this pilot; remove_required is C",
        "tasks": graded,
    }
