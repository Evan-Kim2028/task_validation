"""Fill VEV primitives from a Harbor cheap-run report."""

from __future__ import annotations

from task_validation.evidence.vev import ValidityEvidenceVector


def fill_execution(vev: ValidityEvidenceVector, report: dict) -> ValidityEvidenceVector:
    oracles = report.get("oracle") or []
    rewards = [o.get("reward") for o in oracles if o.get("reward") is not None]
    if rewards:
        vev.set(
            "positive_control",
            status="pass" if all(r == 1.0 for r in rewards) else "fail",
            value=1.0 if all(r == 1.0 for r in rewards) else 0.0,
            n=sum(1 for r in rewards if r == 1.0),
            d=len(rewards),
            detail={"rewards": rewards},
        )
    nop = (report.get("nop") or {}).get("reward")
    if nop is not None:
        vev.set(
            "negative_control",
            status="pass" if nop == 0.0 else "fail",
            value=1.0 if nop == 0.0 else 0.0,
            n=1 if nop == 0.0 else 0,
            d=1,
            detail={"nop_reward": nop},
        )
    det = report.get("deterministic")
    if det is not None:
        vev.set(
            "determinism",
            status="pass" if det else "fail",
            value=1.0 if det else 0.0,
            n=len(rewards),
            d=len(rewards),
        )
    kr = report.get("mutation_kill_rate")
    if kr is not None:
        vev.set(
            "mutation_sensitivity",
            status="pass" if kr >= 1.0 else "fail" if kr < 0.5 else "inconclusive",
            value=float(kr),
            n=report.get("n_mutants_killed"),
            d=report.get("n_mutants_tested"),
            detail={"wrong_impl_accepted_rate": report.get("wrong_impl_accepted_rate")},
        )
    inv = report.get("invariance")
    if inv:
        n = inv.get("n_alts") or 0
        rejected = inv.get("n_rejected") or 0
        frac = rejected / n if n else None
        vev.set(
            "implementation_invariance",
            status="fail" if frac and frac > 0 else "pass" if n else "not_run",
            value=frac,
            n=rejected,
            d=n,
            detail=inv,
        )
    static = report.get("static") or {}
    leaks = []
    if static.get("env_copies_solution"):
        leaks.append("env_copies_solution")
    if static.get("env_copies_tests"):
        leaks.append("env_copies_tests")
    if leaks:
        vev.set(
            "environment_integrity",
            status="fail",
            value=1.0,
            n=len(leaks),
            d=max(len(static), 1),
            detail={"leaks": leaks},
        )
    elif static:
        vev.set(
            "environment_integrity",
            status="pass",
            value=0.0,
            n=0,
            d=1,
            detail={"separate_verifier": static.get("separate_verifier")},
        )
    return vev
