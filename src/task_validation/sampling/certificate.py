"""Finite-population validity certificate from a frozen sample and verdicts.

Release iff UCB_95%(p) < epsilon. The bound is hypergeometric when n < N
and the observed rate when n == N (census). Unadjudicated units
(invalid is null) make the certificate INCOMPLETE; they are not imputed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from task_validation.sampling.estimators import _hypergeom_sf, srs_estimate

ASSAY_GRADES = frozenset({"A", "B"})
ADJUDICATORS = frozenset({"machine", "human", "both"})
VERIFIER_KINDS = frozenset({"execution", "judge", "none"})
SWE_EXEC_PROTOCOL = "verifier_invalid.fresh_environment.execution"
SWE_EXEC_GRADE = "A"
SWE_EXEC_ADJUDICATOR = "machine"
ALPHA_DEFAULT = 0.05


def _as_ids(manifest: dict) -> tuple[int, int, list[str]]:
    ids = [str(x) for x in manifest["ids"]]
    n = int(manifest["n"])
    n_pop = int(manifest["N"])
    if n != len(ids):
        raise ValueError("manifest n must equal len(ids)")
    if not 0 < n <= n_pop:
        raise ValueError("need 0 < n <= N")
    return n_pop, n, ids


def _evidence_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _observed_adjudicator(rows: list[dict]) -> str | None:
    seen: set[str] = set()
    for row in rows:
        raw = row.get("adjudicator")
        if raw is None:
            continue
        seen.add(str(raw))
    if not seen:
        return None
    if "both" in seen or ({"machine", "human"} <= seen):
        return "both"
    if len(seen) == 1:
        only = next(iter(seen))
        return only if only in ADJUDICATORS else None
    return "both"


def _combine_adjudicator(claimed: str, observed: str | None) -> str:
    if claimed not in ADJUDICATORS:
        raise ValueError("adjudicator must be machine, human, or both")
    if observed is None or observed == claimed:
        return claimed
    if observed == "both" or claimed == "both":
        return "both"
    if {claimed, observed} == {"machine", "human"}:
        return "both"
    return claimed


def _grade_label(grades: set[str]) -> str | None:
    if not grades:
        return None
    ordered = [g for g in ("A", "B") if g in grades]
    return "/".join(ordered) if ordered else None


def _ucb(k: int, n: int, n_pop: int, alpha: float) -> tuple[float, str]:
    if n == n_pop:
        return k / n, "census"
    est = srs_estimate(k, n, n_pop, alpha)
    return est.ucb95, est.method


def p_certify(n: int, n_pop: int, p: float, epsilon: float, alpha: float = ALPHA_DEFAULT) -> float:
    """OC-curve P(UCB < epsilon) if true prevalence equals p."""
    if n <= 0 or n_pop <= 0:
        raise ValueError("n and N must be positive")
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must be in [0, 1]")
    if n == n_pop:
        return 1.0 if p < epsilon else 0.0
    k_pop = int(round(p * n_pop))
    k_pop = min(max(k_pop, 0), n_pop)
    k_star = -1
    for k in range(0, n + 1):
        bound, _method = _ucb(k, n, n_pop, alpha)
        if bound < epsilon:
            k_star = k
        else:
            break
    if k_star < 0:
        return 0.0
    return 1.0 - _hypergeom_sf(k_star + 1, n_pop, k_pop, n)


def build_certificate(
    manifest: dict,
    verdicts: list[dict],
    epsilon: float,
    protocol: str,
    adjudicator: str,
    *,
    alpha: float = ALPHA_DEFAULT,
    verifier_kind: str = "execution",
) -> dict:
    """Assemble a release certificate, or mark it INCOMPLETE.

    verifier_kind is the stratum this certificate covers: execution,
    judge, or none (doc 44). A verdict that declares a different
    verifier_kind is unadjudicated here, so judge-verified units never
    pool into an execution stratum's bound. A judge certificate requires
    judge_model on every counted unit and a human adjudicator.
    """
    if not protocol or not str(protocol).strip():
        raise ValueError("protocol must be named")
    protocol = str(protocol)
    if verifier_kind not in VERIFIER_KINDS:
        raise ValueError("verifier_kind must be execution, judge, or none")
    swap_units = [
        str(row.get("unit_id"))
        for row in verdicts
        if str(row.get("verifier_kind")) == "judge_swap"
    ]
    if swap_units:
        raise ValueError(
            "verifier_kind 'judge_swap' verdicts are judge-swap diagnostics "
            "(doc 51); they never enter a certificate bound and never pool "
            "with execution or shipped-judge strata: " + ", ".join(swap_units)
        )
    if verifier_kind == "judge" and adjudicator == "machine":
        raise ValueError(
            "judge strata are human-adjudicated; a judge-verified stratum "
            "has no machine certificate (doc 44)"
        )
    if not 0 < epsilon <= 1:
        raise ValueError("epsilon must be in (0, 1]")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    n_pop, n, ids = _as_ids(manifest)
    by_id: dict[str, dict] = {}
    for row in verdicts:
        uid = str(row["unit_id"])
        by_id[uid] = row

    unadjudicated: list[str] = []
    reasons: dict[str, str] = {}
    counted: list[dict] = []
    flagged: list[dict] = []
    grades: set[str] = set()
    strata: dict[str, int] = {}
    judge_models: set[str] = set()
    judge_agreement: dict[str, object] = {}

    for uid in ids:
        row = by_id.get(uid)
        if row is None:
            unadjudicated.append(uid)
            reasons[uid] = "missing verdict"
            strata["missing_verdict"] = strata.get("missing_verdict", 0) + 1
            continue
        row_kind = str(row.get("verifier_kind") or verifier_kind)
        strata[row_kind] = strata.get(row_kind, 0) + 1
        invalid = row.get("invalid")
        grade = row.get("grade")
        row_protocol = row.get("label_protocol") or protocol
        if invalid is None:
            unadjudicated.append(uid)
            reasons[uid] = "invalid is null"
            continue
        if grade not in ASSAY_GRADES:
            unadjudicated.append(uid)
            reasons[uid] = f"grade {grade!r} is not A/B"
            continue
        if str(row_protocol) != protocol:
            unadjudicated.append(uid)
            reasons[uid] = "label_protocol does not match certificate protocol"
            continue
        if row_kind != verifier_kind:
            unadjudicated.append(uid)
            reasons[uid] = (
                f"verifier_kind {row_kind!r} does not match certificate "
                f"verifier_kind {verifier_kind!r}; strata never pool"
            )
            continue
        if verifier_kind == "judge" and not str(row.get("judge_model") or "").strip():
            unadjudicated.append(uid)
            reasons[uid] = "judge_model missing on a judge-verified unit"
            continue
        grades.add(str(grade))
        counted.append(row)
        if row.get("judge_model"):
            judge_models.add(str(row["judge_model"]))
        if row.get("judge_agreement") is not None:
            judge_agreement[uid] = row["judge_agreement"]
        if bool(invalid):
            flagged.append(
                {
                    "unit_id": uid,
                    "evidence": _evidence_str(row.get("evidence")),
                    "grade": str(grade),
                    "adjudicator": row.get("adjudicator") or adjudicator,
                    "label_protocol": protocol,
                }
            )

    observed = _observed_adjudicator(counted) or _observed_adjudicator(list(by_id.values()))
    adj = _combine_adjudicator(adjudicator, observed)
    base = {
        "complete": False,
        "decision": "incomplete",
        "N": n_pop,
        "n": n,
        "k_invalid": None,
        "p_hat": None,
        "ucb95": None,
        "method": None,
        "alpha": alpha,
        "epsilon": epsilon,
        "p_certify": None,
        "label_protocol": protocol,
        "grade": _grade_label(grades),
        "adjudicator": adj,
        "verifier_kind": verifier_kind,
        "judge_model": sorted(judge_models) if judge_models else None,
        "judge_agreement": judge_agreement or None,
        "strata": strata,
        "replaces_human_sample": False,
        "design": manifest.get("design"),
        "seed": manifest.get("seed"),
        "flagged": flagged,
        "unadjudicated": unadjudicated,
        "unadjudicated_reasons": reasons,
        "n_unadjudicated": len(unadjudicated),
        "n_adjudicated": len(counted),
    }
    if unadjudicated:
        base["reason"] = (
            "INCOMPLETE: unadjudicated units remain. "
            "Do not impute missing labels as valid."
        )
        return base

    k = sum(1 for row in counted if bool(row.get("invalid")))
    p_hat = k / n
    bound, method = _ucb(k, n, n_pop, alpha)
    decision = "release" if bound < epsilon else "reject"
    base.update(
        {
            "complete": True,
            "decision": decision,
            "k_invalid": k,
            "p_hat": p_hat,
            "ucb95": bound,
            "method": method,
            "p_certify": p_certify(n, n_pop, p_hat, epsilon, alpha),
            "reason": (
                "ucb below epsilon" if decision == "release" else "ucb at or above epsilon"
            ),
        }
    )
    return base


def render_certificate_md(cert: dict) -> str:
    """Markdown rendering of a certificate dict."""
    status = str(cert.get("decision") or "incomplete").upper()
    lines = ["# Validity certificate", ""]
    if not cert.get("complete"):
        lines.append(
            cert.get("reason")
            or (
                "INCOMPLETE: unadjudicated units remain. "
                "Do not impute missing labels as valid."
            )
        )
        lines.append("")
    lines.append(f"- Decision: {status}")
    lines.append(f"- N (population): {cert.get('N')}")
    lines.append(f"- n (sample): {cert.get('n')}")
    lines.append(f"- k invalid: {cert.get('k_invalid')}")
    p_hat = cert.get("p_hat")
    ucb = cert.get("ucb95")
    p_c = cert.get("p_certify")
    lines.append(f"- Point estimate p-hat: {_fmt_rate(p_hat)}")
    lines.append(f"- One-sided 95% UCB: {_fmt_rate(ucb)}")
    lines.append(f"- Method: {cert.get('method')}")
    lines.append(f"- Epsilon: {cert.get('epsilon')}")
    lines.append(f"- P(certify | p-hat): {_fmt_rate(p_c)}")
    lines.append(f"- Label protocol: {cert.get('label_protocol')}")
    lines.append(f"- Grade: {cert.get('grade')}")
    lines.append(f"- Adjudicator: {cert.get('adjudicator')}")
    lines.append(f"- Verifier kind: {cert.get('verifier_kind')}")
    strata = cert.get("strata") or {}
    if strata:
        counts = ", ".join(f"{k}={v}" for k, v in sorted(strata.items()))
        lines.append(f"- Strata: {counts}")
    judge_model = cert.get("judge_model")
    if judge_model:
        lines.append(f"- Judge model: {', '.join(judge_model)}")
    judge_agreement = cert.get("judge_agreement") or {}
    if judge_agreement:
        lines.append("- Judge agreement:")
        for uid in sorted(judge_agreement):
            lines.append(f"  - `{uid}`: {json.dumps(judge_agreement[uid])}")
    lines.append(
        f"- Replaces human sample: {bool(cert.get('replaces_human_sample'))}"
    )
    lines.append(f"- Design: {cert.get('design')}")
    lines.append(f"- Seed: {cert.get('seed')}")
    unadj = cert.get("unadjudicated") or []
    if unadj:
        lines.append(f"- Unadjudicated ({len(unadj)}): {', '.join(unadj)}")
    lines.append("")
    lines.append("## Flagged units")
    flagged = cert.get("flagged") or []
    if not flagged:
        lines.append("")
        lines.append("None.")
    else:
        lines.append("")
        for item in flagged:
            ev = item.get("evidence") or ""
            lines.append(f"- `{item['unit_id']}`: {ev}")
    lines.append("")
    return "\n".join(lines)


def _fmt_rate(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.6f}"


def _pick_treatment(rows: list[dict], treatment: str, rep: int = 0) -> dict | None:
    for row in rows:
        if row.get("treatment") == treatment and int(row.get("rep") or 0) == rep:
            return row
    return None


def swe_exec_to_verdicts(rows: list[dict]) -> list[dict]:
    """Machine verdicts from SWE gold/empty execution rows.

    invalid if the reference fails its own verifier or an empty patch is
    resolved (false accept). P2P-break-on-gold stays in the evidence text.
    Units that did not execute both treatments stay unadjudicated (null).
    """
    by_id: dict[str, list[dict]] = {}
    for row in rows:
        iid = str(row.get("instance_id") or row.get("unit_id") or "")
        if not iid:
            continue
        by_id.setdefault(iid, []).append(row)

    verdicts: list[dict] = []
    for iid in sorted(by_id):
        group = by_id[iid]
        gold = _pick_treatment(group, "gold", 0)
        empty = _pick_treatment(group, "empty", 0)
        gold_exec = bool(gold) and gold.get("status") == "executed" and gold.get("resolved") is not None
        empty_exec = (
            bool(empty) and empty.get("status") == "executed" and empty.get("resolved") is not None
        )
        p2p = list((gold or {}).get("pass_to_pass_failure") or [])
        parts: list[str] = []
        invalid: bool | None
        if not gold_exec or not empty_exec:
            invalid = None
            gold_st = None if gold is None else gold.get("status")
            empty_st = None if empty is None else empty.get("status")
            parts.append(f"unadjudicated gold_status={gold_st} empty_status={empty_st}")
        else:
            gold_fail = gold.get("resolved") is False
            empty_accept = empty.get("resolved") is True
            invalid = bool(gold_fail or empty_accept)
            if gold_fail:
                parts.append("reference fails own verifier")
            if empty_accept:
                parts.append("empty patch resolved (false accept)")
            if not invalid:
                parts.append("gold resolved and empty patch not resolved")
        if p2p:
            parts.append("P2P-break-on-gold: " + ", ".join(p2p))
        verdicts.append(
            {
                "unit_id": iid,
                "invalid": invalid,
                "label_protocol": SWE_EXEC_PROTOCOL,
                "grade": SWE_EXEC_GRADE,
                "evidence": "; ".join(parts),
                "adjudicator": SWE_EXEC_ADJUDICATOR,
            }
        )
    return verdicts


def _census_map(census: dict[str, object] | list[dict]) -> dict[str, bool]:
    if isinstance(census, dict):
        if "ids" in census and "invalid" in census:
            ids = [str(x) for x in census["ids"]]
            flags = list(census["invalid"])
            if len(ids) != len(flags):
                raise ValueError("census ids and invalid must align")
            return {i: bool(v) for i, v in zip(ids, flags)}
        skip = {"design", "N", "n", "seed", "ids", "purpose", "frozen"}
        if all(not isinstance(v, (dict, list)) for k, v in census.items() if k not in skip):
            return {str(k): bool(v) for k, v in census.items() if k not in skip}
        rows = census.get("rows") or census.get("units") or []
        if not isinstance(rows, list):
            raise ValueError("census dict must map unit_id to invalid or hold rows")
        census = rows
    out: dict[str, bool] = {}
    for row in census:
        uid = str(row.get("unit_id") or row.get("instance_id") or row.get("task_id") or "")
        if not uid:
            raise ValueError("census row missing unit_id")
        if row.get("invalid") is None:
            raise ValueError(f"census truth for {uid} is null")
        out[uid] = bool(row["invalid"])
    return out


def coverage_check(
    census: dict[str, object] | list[dict],
    manifest: dict,
    epsilon: float,
    protocol: str,
    adjudicator: str,
    *,
    alpha: float = ALPHA_DEFAULT,
    grade: str = "A",
) -> dict:
    """Whether the sample UCB covers the census invalidity rate."""
    cmap = _census_map(census)
    n_pop, n, ids = _as_ids(manifest)
    if len(cmap) != n_pop:
        raise ValueError("census must contain exactly N units")
    missing = [uid for uid in ids if uid not in cmap]
    if missing:
        raise ValueError("census is missing sample ids")
    census_p = sum(cmap.values()) / n_pop
    verdicts = [
        {
            "unit_id": uid,
            "invalid": cmap[uid],
            "label_protocol": protocol,
            "grade": grade,
            "evidence": "census label",
            "adjudicator": adjudicator,
        }
        for uid in ids
    ]
    cert = build_certificate(
        manifest, verdicts, epsilon, protocol, adjudicator, alpha=alpha
    )
    ucb = cert.get("ucb95")
    covered = bool(cert.get("complete")) and ucb is not None and census_p <= float(ucb) + 1e-12
    return {
        "census_p": census_p,
        "n_census": n_pop,
        "n": n,
        "k_invalid": cert.get("k_invalid"),
        "p_hat": cert.get("p_hat"),
        "ucb95": ucb,
        "method": cert.get("method"),
        "covered": covered,
        "complete": cert.get("complete"),
        "epsilon": epsilon,
        "label_protocol": protocol,
        "adjudicator": adjudicator,
    }


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_census(path: Path) -> dict[str, bool] | list[dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix == ".jsonl" or "\n" in text and text[0] != "[" and text[0] != "{":
        return load_jsonl(path)
    obj = json.loads(text)
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return obj
    raise ValueError("census must be JSONL or JSON list/object")


def _infer_protocol(verdicts: list[dict]) -> str:
    found = {str(v["label_protocol"]) for v in verdicts if v.get("label_protocol")}
    if len(found) == 1:
        return next(iter(found))
    if not found:
        raise ValueError("protocol is required (no label_protocol on verdicts)")
    raise ValueError("verdicts mix label_protocol values; pass --protocol")


def _infer_adjudicator(verdicts: list[dict]) -> str:
    observed = _observed_adjudicator(verdicts)
    if observed in ADJUDICATORS:
        return observed
    raise ValueError("adjudicator is required")


def _infer_verifier_kind(verdicts: list[dict]) -> str:
    found = {str(v["verifier_kind"]) for v in verdicts if v.get("verifier_kind")}
    if len(found) == 1:
        only = next(iter(found))
        if only not in VERIFIER_KINDS:
            raise ValueError(f"unknown verifier_kind {only!r}")
        return only
    if not found:
        return "execution"
    raise ValueError(
        "verdicts mix verifier_kind values; split the strata and certify "
        "each on its own bound (doc 44)"
    )


def _write_json(path: Path | None, obj: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_md(path: Path | None, cert: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_certificate_md(cert), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--verdicts", type=Path, help="JSONL of unit verdicts")
    p.add_argument("--epsilon", type=float, default=0.05)
    p.add_argument("--protocol", default=None)
    p.add_argument("--adjudicator", default=None)
    p.add_argument(
        "--verifier-kind",
        default=None,
        choices=sorted(VERIFIER_KINDS),
        help="verifier stratum this certificate covers (default: infer; execution when undeclared)",
    )
    p.add_argument("--alpha", type=float, default=ALPHA_DEFAULT)
    p.add_argument("--out", type=Path, help="certificate JSON")
    p.add_argument("--md", type=Path, help="rendered markdown")
    p.add_argument(
        "--coverage-check",
        action="store_true",
        help="compare sample UCB to a census truth file",
    )
    p.add_argument("--census", type=Path, help="census truth JSON/JSONL")
    p.add_argument("--grade", default="A", help="grade for census-derived verdicts")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.coverage_check:
        if args.census is None:
            print("--census is required with --coverage-check", file=sys.stderr)
            return 2
        census = load_census(args.census)
        protocol = args.protocol or "census-truth"
        adjudicator = args.adjudicator or "human"
        report = coverage_check(
            census,
            manifest,
            args.epsilon,
            protocol,
            adjudicator,
            alpha=args.alpha,
            grade=args.grade,
        )
        _write_json(args.out, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    if args.verdicts is None:
        print("--verdicts is required unless --coverage-check", file=sys.stderr)
        return 2
    verdicts = load_jsonl(args.verdicts)
    protocol = args.protocol or _infer_protocol(verdicts)
    adjudicator = args.adjudicator or _infer_adjudicator(verdicts)
    cert = build_certificate(
        manifest,
        verdicts,
        args.epsilon,
        protocol,
        adjudicator,
        alpha=args.alpha,
        verifier_kind=args.verifier_kind or _infer_verifier_kind(verdicts),
    )
    _write_json(args.out, cert)
    _write_md(args.md, cert)
    print(
        json.dumps(
            {
                "complete": cert["complete"],
                "decision": cert["decision"],
                "N": cert["N"],
                "n": cert["n"],
                "k_invalid": cert["k_invalid"],
                "p_hat": cert["p_hat"],
                "ucb95": cert["ucb95"],
                "method": cert["method"],
                "epsilon": cert["epsilon"],
                "p_certify": cert["p_certify"],
                "label_protocol": cert["label_protocol"],
                "grade": cert["grade"],
                "adjudicator": cert["adjudicator"],
                "verifier_kind": cert["verifier_kind"],
                "judge_model": cert["judge_model"],
                "strata": cert["strata"],
                "n_flagged": len(cert["flagged"]),
                "n_unadjudicated": cert["n_unadjudicated"],
                "out": None if args.out is None else str(args.out),
                "md": None if args.md is None else str(args.md),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
