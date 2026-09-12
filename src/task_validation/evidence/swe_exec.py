"""Parse SWE-bench harness reports for the frozen 2x2 execution probe.

No Docker, no LLM. Rebuilds data/gold/swe_2x2_exec.jsonl and the summary
from logs/run_evaluation/<run_id>/<model>/<instance>/report.json.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

RUNTIME_RE = re.compile(r"Test runtime:\s*([0-9_]+(?:\.[0-9]+)?)\s*seconds")
TIMEOUT_MARKERS = (
    "Timeout error:",
    "Test timed out after",
    ">>>>> Tests Timed Out",
    "tests_timed_out",
)
INFRA_MARKERS = (
    "Image not found",
    "image not found",
    "not found for",
    "Error creating container",
    "Cannot connect to the Docker daemon",
    "Error response from daemon",
    "BUILD FAILED",
    "no published image exists",
)

TREATMENT_RUNS = (
    ("gold", "tv-gold", 0),
    ("empty", "tv-empty", 0),
    ("gold", "tv-gold-rep", 1),
)

STATUSES = ("executed", "infra", "timeout")


def load_jsonl(path: Path, key: str = "task_id") -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out[rec[key]] = rec
    return out


def load_sample(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cell_index(sample: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for cell_name, items in (sample.get("cells") or {}).items():
        for item in items:
            rec = dict(item)
            rec["cell"] = rec.get("cell") or cell_name
            out[rec["task_id"]] = rec
    return out


def unwrap_report(report: dict, instance_id: str) -> dict:
    if instance_id in report and isinstance(report[instance_id], dict):
        return report[instance_id]
    return report


def tests_status_lists(body: dict) -> dict[str, list[str]]:
    ts = body.get("tests_status") or {}
    f2p = ts.get("FAIL_TO_PASS") or {}
    p2p = ts.get("PASS_TO_PASS") or {}
    return {
        "fail_to_pass_success": list(f2p.get("success") or []),
        "fail_to_pass_failure": list(f2p.get("failure") or []),
        "pass_to_pass_success": list(p2p.get("success") or []),
        "pass_to_pass_failure": list(p2p.get("failure") or []),
    }


def parse_instance_report(report: dict, instance_id: str) -> dict:
    """Parse a harness report.json object (wrapped or unwrapped)."""
    body = unwrap_report(report, instance_id)
    lists = tests_status_lists(body)
    resolved = body.get("resolved")
    return {
        "instance_id": instance_id,
        "resolved": bool(resolved) if resolved is not None else None,
        "infra_failure": bool(body.get("infra_failure")),
        "infra_failure_reason": body.get("infra_failure_reason"),
        "patch_successfully_applied": body.get("patch_successfully_applied"),
        "patch_exists": body.get("patch_exists"),
        "patch_is_None": body.get("patch_is_None"),
        **lists,
    }


def parse_elapsed(log_text: str) -> float | None:
    match = RUNTIME_RE.search(log_text or "")
    if not match:
        return None
    return float(match.group(1).replace("_", ""))


def error_tail(text: str, n: int = 1500) -> str | None:
    if not text:
        return None
    clipped = text[-n:]
    return clipped if clipped.strip() else None


def classify_status(
    parsed: dict | None,
    *,
    log_text: str = "",
    test_output: str = "",
) -> str:
    blob = f"{log_text or ''}\n{test_output or ''}"
    lower = blob.lower()
    if any(m.lower() in lower for m in TIMEOUT_MARKERS):
        return "timeout"
    if parsed and parsed.get("infra_failure"):
        return "infra"
    # A report with tests_status means the container ran the tests. The harness
    # logs "Image not found" before pulling, so markers only count without one.
    if parsed and parsed.get("tests_status_present"):
        return "executed"
    if any(m.lower() in lower for m in INFRA_MARKERS):
        return "infra"
    if parsed and (
        parsed.get("fail_to_pass_success")
        or parsed.get("fail_to_pass_failure")
        or parsed.get("pass_to_pass_success")
        or parsed.get("pass_to_pass_failure")
        or parsed.get("resolved") is not None
    ):
        return "executed"
    if parsed and parsed.get("patch_successfully_applied"):
        return "executed"
    return "infra"


def _mark_tests_present(parsed: dict, body: dict) -> dict:
    parsed = dict(parsed)
    parsed["tests_status_present"] = bool(body.get("tests_status"))
    return parsed


def pass_frac(success: list, failure: list) -> float | None:
    n = len(success) + len(failure)
    if n == 0:
        return None
    return len(success) / n


def fail_frac(success: list, failure: list) -> float | None:
    n = len(success) + len(failure)
    if n == 0:
        return None
    return len(failure) / n


def phi_coefficient(n00: int, n01: int, n10: int, n11: int) -> float | None:
    """Phi for a 2x2 table [[n00, n01], [n10, n11]]."""
    n = n00 + n01 + n10 + n11
    if n == 0:
        return None
    den = math.sqrt((n00 + n01) * (n10 + n11) * (n00 + n10) * (n01 + n11))
    if den == 0:
        return None
    return (n00 * n11 - n01 * n10) / den


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_report_file(path: Path) -> dict | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_instance_dir(inst_dir: Path, instance_id: str) -> dict:
    report = load_report_file(inst_dir / "report.json")
    log_text = read_text(inst_dir / "run_instance.log")
    test_output = read_text(inst_dir / "test_output.txt")
    parsed = parse_instance_report(report, instance_id) if report else None
    if parsed and report:
        parsed = _mark_tests_present(parsed, unwrap_report(report, instance_id))
    status = classify_status(parsed, log_text=log_text, test_output=test_output)
    elapsed = parse_elapsed(log_text)
    tail_src = log_text or test_output
    row = {
        "instance_id": instance_id,
        "status": status,
        "elapsed_sec": elapsed,
        "error_tail": error_tail(tail_src) if status != "executed" else None,
        "resolved": None if parsed is None else parsed.get("resolved"),
        "fail_to_pass_success": [] if parsed is None else parsed["fail_to_pass_success"],
        "fail_to_pass_failure": [] if parsed is None else parsed["fail_to_pass_failure"],
        "pass_to_pass_success": [] if parsed is None else parsed["pass_to_pass_success"],
        "pass_to_pass_failure": [] if parsed is None else parsed["pass_to_pass_failure"],
        "infra_failure": bool(parsed and parsed.get("infra_failure")),
        "patch_successfully_applied": None
        if parsed is None
        else parsed.get("patch_successfully_applied"),
        "log_dir": str(inst_dir),
    }
    if status != "executed" and row["error_tail"] is None:
        row["error_tail"] = error_tail(tail_src) or "no report.json"
    return row


def iter_run_instance_dirs(logs_dir: Path, run_id: str) -> list[tuple[str, str, Path]]:
    """Return (model, instance_id, dir) for a harness run_id."""
    root = logs_dir / run_id
    if not root.is_dir():
        return []
    found: list[tuple[str, str, Path]] = []
    for model_dir in sorted(root.iterdir()):
        if not model_dir.is_dir():
            continue
        if model_dir.name in {"run.json"}:
            continue
        for inst_dir in sorted(model_dir.iterdir()):
            if inst_dir.is_dir():
                found.append((model_dir.name, inst_dir.name, inst_dir))
    return found


def join_labels(
    instance_id: str,
    *,
    cells: dict[str, dict],
    compact: dict[str, dict],
    oof: dict[str, dict],
    raters: dict[str, dict],
) -> dict:
    cell = cells.get(instance_id) or {}
    gold = compact.get(instance_id) or {}
    oof_row = oof.get(instance_id) or {}
    rater = raters.get(instance_id) or {}
    severity = gold.get("human_severity") or {}
    return {
        "cell": cell.get("cell"),
        "p_logistic": oof_row.get("p_logistic", cell.get("p_logistic")),
        "human_validity_label": gold.get("human_validity_label"),
        "human_label_provenance": gold.get("human_label_provenance"),
        "n_raters": rater.get("n_raters", gold.get("n_raters")),
        "n_material_votes": rater.get("n_material_votes"),
        "openai_2024_conservative": rater.get("openai_2024_conservative"),
        "majority_invalid": rater.get("majority_invalid"),
        "unanimous_invalid": rater.get("unanimous_invalid"),
        "votes": rater.get("votes"),
        "underspecified": severity.get("underspecified"),
        "false_negative": severity.get("false_negative"),
        "other_major_issues": severity.get("other_major_issues"),
        "filter_out": severity.get("filter_out"),
        "difficulty": gold.get("difficulty"),
        "repository": gold.get("repository") or cell.get("repository") or oof_row.get("repository"),
    }


def collect_rows(
    logs_dir: Path,
    *,
    run_ids: list[str],
    cells: dict[str, dict],
    compact: dict[str, dict],
    oof: dict[str, dict],
    raters: dict[str, dict],
    treatment_runs: tuple[tuple[str, str, int], ...] = TREATMENT_RUNS,
) -> list[dict]:
    wanted = set(run_ids)
    rows: list[dict] = []
    for treatment, run_id, rep in treatment_runs:
        seen: set[str] = set()
        for model, iid, inst_dir in iter_run_instance_dirs(logs_dir, run_id):
            if iid not in wanted:
                continue
            parsed = parse_instance_dir(inst_dir, iid)
            labels = join_labels(
                iid, cells=cells, compact=compact, oof=oof, raters=raters
            )
            rows.append(
                {
                    **parsed,
                    **labels,
                    "treatment": treatment,
                    "rep": rep,
                    "run_id": run_id,
                    "model_name_or_path": model,
                }
            )
            seen.add(iid)
        # Gold-rep is only the 5 fastest; do not invent infra rows for the rest.
        if rep != 0:
            continue
        for iid in run_ids:
            if iid in seen:
                continue
            labels = join_labels(
                iid, cells=cells, compact=compact, oof=oof, raters=raters
            )
            rows.append(
                {
                    "instance_id": iid,
                    "status": "infra",
                    "elapsed_sec": None,
                    "error_tail": f"no harness logs for run_id={run_id}",
                    "resolved": None,
                    "fail_to_pass_success": [],
                    "fail_to_pass_failure": [],
                    "pass_to_pass_success": [],
                    "pass_to_pass_failure": [],
                    "infra_failure": True,
                    "patch_successfully_applied": None,
                    "log_dir": None,
                    **labels,
                    "treatment": treatment,
                    "rep": rep,
                    "run_id": run_id,
                    "model_name_or_path": None,
                }
            )
    rows.sort(key=lambda r: (r["instance_id"], r["treatment"], r["rep"]))
    return rows


def _by_key(rows: list[dict]) -> dict[tuple, dict]:
    return {(r["instance_id"], r["treatment"], r["rep"]): r for r in rows}


def _crosstab(pairs: list[tuple[bool, int]]) -> dict:
    """pairs of (signal, y_invalid)."""
    n_sig_inv = n_sig_val = n_nos_inv = n_nos_val = 0
    for signal, y in pairs:
        if signal and y:
            n_sig_inv += 1
        elif signal and not y:
            n_sig_val += 1
        elif (not signal) and y:
            n_nos_inv += 1
        else:
            n_nos_val += 1
    return {
        "signal_and_invalid": n_sig_inv,
        "signal_and_valid": n_sig_val,
        "no_signal_and_invalid": n_nos_inv,
        "no_signal_and_valid": n_nos_val,
        "n": n_sig_inv + n_sig_val + n_nos_inv + n_nos_val,
        "phi": phi_coefficient(n_nos_val, n_nos_inv, n_sig_val, n_sig_inv),
    }


def summarize(rows: list[dict], run_ids: list[str]) -> dict:
    keyed = _by_key(rows)
    per_instance: dict[str, dict] = {}
    n_gold_pass = 0
    n_empty_fail = 0
    n_reference_fails_own_verifier = 0
    n_flaky = 0
    n_infra = 0
    n_timeout = 0
    gold_fail_tests: dict[str, list[str]] = {}
    cons_pairs: list[tuple[bool, int]] = []
    maj_pairs: list[tuple[bool, int]] = []
    p2p_cons_pairs: list[tuple[bool, int]] = []
    elapsed_gold: list[float] = []
    n_det_compared = 0
    n_det_agree = 0

    infra_ids: set[str] = set()
    for iid in run_ids:
        gold = keyed.get((iid, "gold", 0))
        empty = keyed.get((iid, "empty", 0))
        gold_rep = keyed.get((iid, "gold", 1))
        gold = gold or {}
        empty = empty or {}

        gold_status = gold.get("status")
        empty_status = empty.get("status")
        if gold_status == "infra" or empty_status == "infra":
            n_infra += 1
            infra_ids.add(iid)
        if gold_status == "timeout" or empty_status == "timeout":
            n_timeout += 1

        gold_resolved = gold.get("resolved")
        empty_resolved = empty.get("resolved")
        gold_exec = gold_status == "executed"
        empty_exec = empty_status == "executed"

        if gold_exec and gold.get("elapsed_sec") is not None:
            elapsed_gold.append(float(gold["elapsed_sec"]))

        if gold_exec and gold_resolved:
            n_gold_pass += 1
        if empty_exec and empty_resolved is False:
            n_empty_fail += 1
        if gold_exec and gold_resolved is False:
            n_reference_fails_own_verifier += 1
            fails = list(gold.get("fail_to_pass_failure") or []) + list(
                gold.get("pass_to_pass_failure") or []
            )
            gold_fail_tests[iid] = fails

        det = None
        if gold_rep and gold_rep.get("status") == "executed" and gold_exec:
            n_det_compared += 1
            det = bool(gold_resolved) == bool(gold_rep.get("resolved"))
            if det:
                n_det_agree += 1
            else:
                n_flaky += 1

        gold_f2p_pass = pass_frac(
            gold.get("fail_to_pass_success") or [],
            gold.get("fail_to_pass_failure") or [],
        )
        empty_f2p_fail = fail_frac(
            empty.get("fail_to_pass_success") or [],
            empty.get("fail_to_pass_failure") or [],
        )
        p2p_break = None
        if gold_exec:
            p2p_break = bool(gold.get("pass_to_pass_failure"))

        signal = bool(gold_exec and empty_exec and gold_resolved and empty_resolved is False)
        y_cons = gold.get("openai_2024_conservative")
        y_maj = gold.get("majority_invalid")
        if gold_exec and empty_exec and y_cons is not None:
            cons_pairs.append((signal, int(y_cons)))
        if gold_exec and empty_exec and y_maj is not None:
            maj_pairs.append((signal, int(y_maj)))
        if gold_exec and y_cons is not None and p2p_break is not None:
            p2p_cons_pairs.append((bool(p2p_break), int(y_cons)))

        per_instance[iid] = {
            "cell": gold.get("cell") or empty.get("cell"),
            "p_logistic": gold.get("p_logistic"),
            "human_validity_label": gold.get("human_validity_label"),
            "openai_2024_conservative": y_cons,
            "majority_invalid": y_maj,
            "gold_resolved": gold_resolved,
            "empty_resolved": empty_resolved,
            "gold_status": gold_status,
            "empty_status": empty_status,
            "gold_f2p_pass_frac": gold_f2p_pass,
            "empty_f2p_fail_frac": empty_f2p_fail,
            "p2p_break_on_gold": p2p_break,
            "determinism": det,
            "gold_elapsed_sec": gold.get("elapsed_sec"),
            "empty_elapsed_sec": empty.get("elapsed_sec"),
            "gold_rep_resolved": None if not gold_rep else gold_rep.get("resolved"),
            "signal_gold_pass_empty_fail": signal if (gold_exec and empty_exec) else None,
            "gold_f2p_failure": list(gold.get("fail_to_pass_failure") or []),
            "gold_p2p_failure": list(gold.get("pass_to_pass_failure") or []),
        }

    vs_cons = _crosstab(cons_pairs)
    vs_maj = _crosstab(maj_pairs)
    vs_p2p = _crosstab(p2p_cons_pairs)
    n_signal = sum(1 for s, _ in cons_pairs if s)
    note = (
        "SWE-bench already requires fail-before / pass-after, so gold-pass and "
        "empty-fail is the construction of the benchmark. A null association "
        "with the 2024 specification-fairness label is the expected result, "
        "not a retune signal."
    )
    return {
        "n_instances": len(run_ids),
        "n_gold_pass": n_gold_pass,
        "n_empty_fail": n_empty_fail,
        "n_reference_fails_own_verifier": n_reference_fails_own_verifier,
        "reference_fail_tests": gold_fail_tests,
        "n_flaky": n_flaky,
        "n_determinism_compared": n_det_compared,
        "n_determinism_agree": n_det_agree,
        "n_infra": n_infra,
        "n_timeout": n_timeout,
        "infra_ids": sorted(infra_ids),
        "n_signal_gold_pass_empty_fail": n_signal,
        "gold_elapsed_sec_mean": (
            sum(elapsed_gold) / len(elapsed_gold) if elapsed_gold else None
        ),
        "gold_elapsed_sec_total": sum(elapsed_gold) if elapsed_gold else 0.0,
        "crosstab_signal_vs_conservative": vs_cons,
        "crosstab_signal_vs_majority": vs_maj,
        "crosstab_p2p_break_vs_conservative": vs_p2p,
        "correlates_with_2024_label": _correlates(vs_cons),
        "expected_null": True,
        "note": note,
        "instances": per_instance,
    }


def _correlates(tab: dict, abs_phi_min: float = 0.3) -> bool | None:
    phi = tab.get("phi")
    if phi is None or tab.get("n", 0) == 0:
        return None
    return abs(phi) >= abs_phi_min


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    skip = {"raw"}
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            dumped = {k: v for k, v in row.items() if k not in skip}
            fh.write(json.dumps(dumped, ensure_ascii=False) + "\n")


def rebuild(
    *,
    logs_dir: Path,
    sample_path: Path,
    compact_path: Path,
    oof_path: Path,
    raters_path: Path,
    out_jsonl: Path,
    out_summary: Path,
    gold_run: str = "tv-gold",
    empty_run: str = "tv-empty",
    gold_rep_run: str = "tv-gold-rep",
) -> dict:
    sample = load_sample(sample_path)
    run_ids = list(sample["run_ids"])
    cells = cell_index(sample)
    compact = load_jsonl(compact_path)
    oof = load_jsonl(oof_path)
    raters = load_jsonl(raters_path)
    treatment_runs = (
        ("gold", gold_run, 0),
        ("empty", empty_run, 0),
        ("gold", gold_rep_run, 1),
    )
    rows = collect_rows(
        logs_dir,
        run_ids=run_ids,
        cells=cells,
        compact=compact,
        oof=oof,
        raters=raters,
        treatment_runs=treatment_runs,
    )
    summary = summarize(rows, run_ids)
    summary["gold_run"] = gold_run
    summary["empty_run"] = empty_run
    summary["gold_rep_run"] = gold_rep_run
    write_jsonl(rows, out_jsonl)
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--logs-dir", type=Path, default=Path("logs/run_evaluation"))
    p.add_argument("--sample", type=Path, default=Path("data/gold/swe_2x2_sample.json"))
    p.add_argument(
        "--compact", type=Path, default=Path("data/gold/swe_verified_compact.jsonl")
    )
    p.add_argument(
        "--oof",
        type=Path,
        default=Path("data/gold/oof_openai_2024_conservative.oof.jsonl"),
    )
    p.add_argument(
        "--raters", type=Path, default=Path("data/gold/swe_rater_targets.jsonl")
    )
    p.add_argument("--out-jsonl", type=Path, default=Path("data/gold/swe_2x2_exec.jsonl"))
    p.add_argument(
        "--out-summary", type=Path, default=Path("data/gold/swe_2x2_exec.summary.json")
    )
    p.add_argument("--gold-run", default="tv-gold")
    p.add_argument("--empty-run", default="tv-empty")
    p.add_argument("--gold-rep-run", default="tv-gold-rep")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = rebuild(
        logs_dir=args.logs_dir,
        sample_path=args.sample,
        compact_path=args.compact,
        oof_path=args.oof,
        raters_path=args.raters,
        out_jsonl=args.out_jsonl,
        out_summary=args.out_summary,
        gold_run=args.gold_run,
        empty_run=args.empty_run,
        gold_rep_run=args.gold_rep_run,
    )
    print(
        json.dumps(
            {
                "n_instances": summary["n_instances"],
                "n_gold_pass": summary["n_gold_pass"],
                "n_empty_fail": summary["n_empty_fail"],
                "n_reference_fails_own_verifier": summary["n_reference_fails_own_verifier"],
                "n_flaky": summary["n_flaky"],
                "n_infra": summary["n_infra"],
                "correlates_with_2024_label": summary["correlates_with_2024_label"],
                "out_jsonl": str(args.out_jsonl),
                "out_summary": str(args.out_summary),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
