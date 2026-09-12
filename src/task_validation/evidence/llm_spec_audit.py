"""LLM specification-invalidity instrument for SWE-bench 2024 labels.

Eval of an auditor, not training. Human labels, rater votes, and OOF scores
never enter the prompt. One frozen prompt, one pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from task_validation.evidence.diffstats import parse_json_list
from task_validation.evidence.irt import (
    auroc,
    bootstrap_auroc,
    load_jsonl,
    mean,
    retain_by_score,
    zscore,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

SAMPLE_SEED = "swe-llm-audit-v0"
SAMPLE_N = 200
SAMPLE_N_REDUCED = 150
MAX_USD = 10.0
FULL_MAX_USD = 20.0
CONCURRENCY = 4
FULL_CONCURRENCY = 4
# Actual mean completion tokens from the n=200 pass (doc 34). Used to
# project remaining full-population spend; the 4,000-token default would
# refuse a 1,699 run that in practice costs ~$0.008/item.
PRIOR_MEAN_COMPLETION_TOKENS = 444
TEMPERATURE = 0.0
TOKEN_BUDGET = 24000
CHARS_PER_TOKEN = 4
N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 20260912
RETAIN_FRACS = (0.05, 0.10, 0.20)
EXPECTED_COMPLETION_TOKENS = 4000
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"
OPENROUTER_CHAT = "https://openrouter.ai/api/v1/chat/completions"
XAI_CHAT = "https://api.x.ai/v1/chat/completions"
_XAI_LOCK = Lock()
_PREFER_XAI = False
MAJOR_PREFIXES = (
    "openai/",
    "anthropic/",
    "google/",
    "x-ai/",
    "meta-llama/",
    "mistralai/",
    "amazon/",
)
PROMPT_KEYS = (
    "problem_statement",
    "patch",
    "test_patch",
    "FAIL_TO_PASS",
    "repo",
    "base_commit",
    "instance_id",
    "task_id",
)
# Gold-file field names that must not be interpolated into the prompt.
# Rubric axis names (underspecified, false_negative) are asked for, not leaked.
LEAK_MARKERS = (
    "human_validity_label",
    "human_severity",
    "human_label_provenance",
    "p_logistic",
    "p_hgb",
    "filter_out",
    "openai_2024_conservative",
    "majority_invalid",
    "unanimous_invalid",
    "n_material_votes",
    "underspecified_notes",
    "false_negative_notes",
    "other_notes",
)
Y_KEYS = (
    ("conservative", "openai_2024_conservative"),
    ("majority", "majority_invalid"),
    ("unanimous", "unanimous_invalid"),
)

# Frozen before any label comparison. Do not retune the prompt on fail.
COMBINATION_RULE = (
    "retain lowest z(s) + z(1-p_i): low auditor severity and high solve rate"
)
FROZEN_PREDICATES = {
    "F1": (
        "AUROC(s, conservative) >= 0.75 with 1,000-rep bootstrap CI lower bound "
        "> 0.70"
    ),
    "F2": (
        "Cohen's kappa of the model material bit vs majority_invalid >= 0.39 "
        "(human Fleiss kappa on the material bit)"
    ),
    "F3": (
        "retain-20% residual under z(s)+z(1-p_i) <= 0.20 on conservative Y "
        "(versus 0.43 for metadata / OOF logistic alone on the full 1,699)"
    ),
}

SYSTEM_PROMPT = (
    "You audit whether a SWE-bench coding task is specification-valid. "
    "You see a GitHub issue, the FAIL_TO_PASS tests (names and patch), and the "
    "gold patch. Judge only specification fairness: whether a competent engineer "
    "could know what to implement from the issue, and whether those tests fairly "
    "check the issue. Do not judge difficulty. Do not treat the gold patch as "
    "proof that the tests are fair; use it only to see what the tests require. "
    "Reply with one JSON object and no markdown."
)

USER_RUBRIC = """\
Score these fields. Integers unless noted.

underspecified:
  0 = well specified
  1 = minor blanks a senior engineer would fill in
  2 = major blanks; a reasonable engineer could solve differently and fail
  3 = almost impossible to know what is required

false_negative (unfair FAIL_TO_PASS tests):
  0 = tests match the issue
  1 = tests slightly narrower
  2 = tests require unstated behavior or specific names/messages
  3 = tests would reject most valid solutions

other_major_issue: 0 or 1
other_reason: one line; empty string if other_major_issue is 0
confidence: number in [0, 1]
rationale: exactly two sentences
p_invalid: number in [0, 1], your probability that OpenAI's 2024 conservative
  rule would discard this task. That rule discards a task if any of three
  annotators would mark underspecified >= 2 or false_negative >= 2 or
  other_major_issue = 1.

Return only JSON with keys:
underspecified, false_negative, other_major_issue, other_reason,
confidence, rationale, p_invalid
"""


def seed_to_int(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest(), "big")


def draw_sample(task_ids: list[str], n: int, seed: str = SAMPLE_SEED) -> list[str]:
    """SRS without replacement from the sorted id list."""

    population = sorted(task_ids)
    if n > len(population):
        raise ValueError(f"n={n} larger than population {len(population)}")
    rng = random.Random(seed_to_int(seed))
    return rng.sample(population, n)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def truncate_to_tokens(text: str, n_tokens: int) -> tuple[str, bool]:
    if n_tokens <= 0:
        return "", bool(text)
    n_chars = n_tokens * CHARS_PER_TOKEN
    if len(text) <= n_chars:
        return text, False
    return text[:n_chars] + "\n...[truncated]...", True


def instance_for_prompt(rec: dict) -> dict:
    """Copy only fields the auditor is allowed to see."""

    out = {}
    for key in PROMPT_KEYS:
        if key in rec and rec[key] is not None:
            out[key] = rec[key]
    if "task_id" not in out and "instance_id" in out:
        out["task_id"] = out["instance_id"]
    if "instance_id" not in out and "task_id" in out:
        out["instance_id"] = out["task_id"]
    return out


def prompt_leaks_labels(text: str) -> list[str]:
    """Detect gold-file field names. Rubric axis names are not leaks."""

    lowered = text.lower()
    return [key for key in LEAK_MARKERS if key.lower() in lowered]


def truncate_packet(rec: dict, budget_tokens: int = TOKEN_BUDGET) -> dict:
    """Issue and test patch take leftover tokens before the gold patch."""

    inst = instance_for_prompt(rec)
    issue = str(inst.get("problem_statement") or "")
    test_patch = str(inst.get("test_patch") or "")
    gold = str(inst.get("patch") or "")
    f2p_names = parse_json_list(inst.get("FAIL_TO_PASS"))
    f2p_text = "\n".join(f2p_names)
    repo = str(inst.get("repo") or "")
    base = str(inst.get("base_commit") or "")
    header = f"Repo: {repo}\nBase commit: {base}\n"
    reserved = estimate_tokens(SYSTEM_PROMPT) + estimate_tokens(USER_RUBRIC) + estimate_tokens(header) + 80
    remaining = max(256, budget_tokens - reserved)
    issue_t, issue_cut = truncate_to_tokens(issue, remaining)
    remaining -= estimate_tokens(issue_t)
    test_t, test_cut = truncate_to_tokens(test_patch, max(0, remaining))
    remaining -= estimate_tokens(test_t)
    f2p_t, f2p_cut = truncate_to_tokens(f2p_text, max(0, remaining))
    remaining -= estimate_tokens(f2p_t)
    gold_t, gold_cut = truncate_to_tokens(gold, max(0, remaining))
    return {
        "task_id": inst.get("task_id") or inst.get("instance_id"),
        "repo": repo,
        "base_commit": base,
        "issue": issue_t,
        "test_patch": test_t,
        "fail_to_pass": f2p_t,
        "gold_patch": gold_t,
        "truncated": {
            "issue": issue_cut,
            "test_patch": test_cut,
            "fail_to_pass": f2p_cut,
            "gold_patch": gold_cut,
        },
    }


def build_prompt(rec: dict, budget_tokens: int = TOKEN_BUDGET) -> dict:
    """Build chat messages. Labels are stripped before interpolation."""

    packet = truncate_packet(rec, budget_tokens=budget_tokens)
    user = (
        f"Repo: {packet['repo']}\n"
        f"Base commit: {packet['base_commit']}\n\n"
        f"## Issue\n{packet['issue']}\n\n"
        f"## FAIL_TO_PASS test names\n{packet['fail_to_pass']}\n\n"
        f"## Test patch\n{packet['test_patch']}\n\n"
        f"## Gold patch\n{packet['gold_patch']}\n\n"
        f"{USER_RUBRIC}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    return {
        "task_id": packet["task_id"],
        "messages": messages,
        "truncated": packet["truncated"],
        "est_prompt_tokens": estimate_tokens(SYSTEM_PROMPT) + estimate_tokens(user),
    }


def _as_int(value, lo: int, hi: int) -> int:
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, str):
        value = value.strip()
    number = float(value)
    return max(lo, min(hi, int(round(number))))


def _as_unit(value) -> float:
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, str):
        value = value.strip().rstrip("%")
    number = float(value)
    if number > 1.0 and number <= 100.0:
        number = number / 100.0
    return max(0.0, min(1.0, float(number)))


def extract_json_object(text: str) -> dict:
    if not text or not str(text).strip():
        raise ValueError("empty model content")
    blob = str(text).strip()
    if blob.startswith("```"):
        lines = blob.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        blob = "\n".join(lines).strip()
    start = blob.find("{")
    end = blob.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in model content")
    parsed = json.loads(blob[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("JSON root is not an object")
    return parsed


def message_text(response: dict) -> str:
    choices = response.get("choices") or []
    if not choices:
        return str(response.get("content") or "")
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    if content:
        return str(content)
    return str(msg.get("reasoning") or "")


def parse_response(raw) -> dict:
    """Parse a chat response dict or a content string into rubric fields."""

    if isinstance(raw, dict) and "choices" in raw:
        text = message_text(raw)
    elif isinstance(raw, dict) and any(
        k in raw for k in ("underspecified", "false_negative", "p_invalid")
    ):
        text = json.dumps(raw)
    else:
        text = raw if isinstance(raw, str) else json.dumps(raw)
    obj = extract_json_object(text)
    other = obj.get("other_major_issue", obj.get("other_major_issues", 0))
    parsed = {
        "underspecified": _as_int(obj.get("underspecified", 0), 0, 3),
        "false_negative": _as_int(obj.get("false_negative", 0), 0, 3),
        "other_major_issue": _as_int(other, 0, 1),
        "other_reason": str(obj.get("other_reason") or "").strip(),
        "confidence": _as_unit(obj.get("confidence", 0.0)),
        "rationale": str(obj.get("rationale") or "").strip(),
        "p_invalid": _as_unit(obj.get("p_invalid", 0.0)),
    }
    if parsed["other_major_issue"] == 0:
        parsed["other_reason"] = parsed["other_reason"] if parsed["other_reason"] else ""
    return parsed


def auditor_score(underspecified: int, false_negative: int, other: int) -> float:
    return float(max(underspecified, false_negative)) + 0.25 * float(other)


def model_material(parsed: dict) -> int:
    return int(
        int(parsed["underspecified"]) >= 2
        or int(parsed["false_negative"]) >= 2
        or int(parsed["other_major_issue"]) >= 1
    )


def score_parsed(parsed: dict) -> dict:
    s = auditor_score(
        parsed["underspecified"],
        parsed["false_negative"],
        parsed["other_major_issue"],
    )
    out = dict(parsed)
    out["s"] = s
    out["model_material"] = model_material(parsed)
    return out


def join_row(
    audit: dict,
    compact: dict | None = None,
    raters: dict | None = None,
    irt_item: dict | None = None,
    oof: dict | None = None,
) -> dict:
    """Attach labels and no-human scores after the auditor has scored."""

    compact = compact or {}
    raters = raters or {}
    irt_item = irt_item or {}
    oof = oof or {}
    sev = compact.get("human_severity") or {}
    row = dict(audit)
    row["human_validity_label"] = compact.get("human_validity_label")
    row["openai_2024_conservative"] = raters.get("openai_2024_conservative")
    row["majority_invalid"] = raters.get("majority_invalid")
    row["unanimous_invalid"] = raters.get("unanimous_invalid")
    row["human_underspecified"] = sev.get("underspecified")
    row["human_false_negative"] = sev.get("false_negative")
    row["human_other_major_issues"] = sev.get("other_major_issues")
    row["n_raters"] = raters.get("n_raters", compact.get("n_raters"))
    row["n_material_votes"] = raters.get("n_material_votes")
    row["votes"] = list(raters.get("votes") or [])
    row["p_i"] = irt_item.get("p_i")
    row["p_logistic"] = oof.get("p_logistic")
    row["repository"] = compact.get("repository")
    return row


def cohens_kappa(a: list[int], b: list[int]) -> float | None:
    n = len(a)
    if n == 0 or n != len(b):
        return None
    p_o = sum(1 for x, y in zip(a, b) if int(x) == int(y)) / n
    p_a = sum(int(x) for x in a) / n
    p_b = sum(int(y) for y in b) / n
    p_e = p_a * p_b + (1.0 - p_a) * (1.0 - p_b)
    if p_e >= 1.0:
        return 1.0 if p_o >= 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


def pairwise_model_human_agreement(model_bits: list[int], vote_rows: list[list[int]]) -> dict:
    hits = 0
    n = 0
    per_slot = []
    max_raters = max((len(v) for v in vote_rows), default=0)
    slot_hits = [0] * max_raters
    slot_n = [0] * max_raters
    for bit, votes in zip(model_bits, vote_rows):
        for i, vote in enumerate(votes):
            n += 1
            agree = int(int(bit) == int(vote))
            hits += agree
            slot_hits[i] += agree
            slot_n[i] += 1
    for i in range(max_raters):
        per_slot.append(slot_hits[i] / slot_n[i] if slot_n[i] else None)
    return {
        "agreement": hits / n if n else None,
        "n_pairs": n,
        "per_rater_slot": per_slot,
    }


def retain_tail(y: list[int], scores: list[float], fracs: tuple[float, ...] = RETAIN_FRACS) -> list[dict]:
    return retain_by_score(y, scores, fracs, higher_kept=False)


def combination_scores(s: list[float], one_minus_p: list[float]) -> list[float]:
    zs = zscore(s)
    zp = zscore(one_minus_p)
    return [zs[i] + zp[i] for i in range(len(s))]


def residual_at(retain_rows: list[dict], frac: float) -> float | None:
    for row in retain_rows:
        if abs(float(row["retain_frac"]) - frac) < 1e-12:
            return row["residual_invalid"]
    return None


def evaluate_predicates(
    auroc_s_conservative: dict,
    kappa_majority: float | None,
    retain20_combo: float | None,
) -> dict:
    """Apply frozen F1/F2/F3. Do not retune the prompt on fail."""

    value = auroc_s_conservative.get("value")
    ci = auroc_s_conservative.get("ci95") or [None, None]
    lo = ci[0]
    f1 = bool(
        value is not None
        and value >= 0.75
        and lo is not None
        and lo > 0.70
    )
    f2 = bool(kappa_majority is not None and kappa_majority >= 0.39)
    f3 = bool(retain20_combo is not None and retain20_combo <= 0.20)
    return {
        "F1": {
            "text": FROZEN_PREDICATES["F1"],
            "pass": f1,
            "auroc": value,
            "ci95_lo": lo,
            "ci95_hi": ci[1],
        },
        "F2": {
            "text": FROZEN_PREDICATES["F2"],
            "pass": f2,
            "kappa": kappa_majority,
            "threshold": 0.39,
        },
        "F3": {
            "text": FROZEN_PREDICATES["F3"],
            "pass": f3,
            "retain20_combo": retain20_combo,
            "threshold": 0.20,
            "metadata_alone_full1699": 0.43,
        },
        "all_pass": bool(f1 and f2 and f3),
        "combination_rule": COMBINATION_RULE,
    }


def analyze_rows(
    rows: list[dict],
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    usable = [
        r
        for r in rows
        if r.get("s") is not None
        and r.get("p_invalid") is not None
        and r.get("p_i") is not None
        and r.get("p_logistic") is not None
        and r.get("openai_2024_conservative") is not None
    ]
    s = [float(r["s"]) for r in usable]
    p_inv = [float(r["p_invalid"]) for r in usable]
    one_minus_p = [1.0 - float(r["p_i"]) for r in usable]
    p_log = [float(r["p_logistic"]) for r in usable]
    combo = combination_scores(s, one_minus_p)
    model_bits = [int(r["model_material"]) for r in usable]
    vote_rows = [list(r.get("votes") or []) for r in usable]
    majority = [int(r["majority_invalid"] or 0) for r in usable]
    agree = pairwise_model_human_agreement(model_bits, vote_rows)
    kappa = cohens_kappa(model_bits, majority)
    agree_maj = (
        sum(1 for a, b in zip(model_bits, majority) if a == b) / len(usable)
        if usable
        else None
    )
    by_y = {}
    for name, field in Y_KEYS:
        y = [int(r[field] or 0) for r in usable]
        by_y[name] = {
            "n": len(y),
            "n_invalid": sum(y),
            "base_rate": mean([float(t) for t in y]),
            "auroc_s": bootstrap_auroc(y, s, n_reps=n_bootstrap, seed=seed),
            "auroc_p_invalid": bootstrap_auroc(
                y, p_inv, n_reps=n_bootstrap, seed=seed + 1
            ),
            "retain": {
                "s": retain_tail(y, s),
                "one_minus_p_i": retain_tail(y, one_minus_p),
                "p_logistic": retain_tail(y, p_log),
                "combination": retain_tail(y, combo),
            },
        }
    y_u = [
        1 if float(r.get("human_underspecified") or 0) >= 2 else 0 for r in usable
    ]
    y_fn = [
        1 if float(r.get("human_false_negative") or 0) >= 2 else 0 for r in usable
    ]
    u_model = [float(r["underspecified"]) for r in usable]
    fn_model = [float(r["false_negative"]) for r in usable]
    axes = {
        "underspecified_ge2": {
            "n": sum(y_u),
            "base_rate": mean([float(t) for t in y_u]),
            "auroc_model_underspecified": bootstrap_auroc(
                y_u, u_model, n_reps=n_bootstrap, seed=seed + 2
            ),
        },
        "false_negative_ge2": {
            "n": sum(y_fn),
            "base_rate": mean([float(t) for t in y_fn]),
            "auroc_model_false_negative": bootstrap_auroc(
                y_fn, fn_model, n_reps=n_bootstrap, seed=seed + 3
            ),
        },
    }
    cons = by_y["conservative"]
    predicates = evaluate_predicates(
        cons["auroc_s"],
        kappa,
        residual_at(cons["retain"]["combination"], 0.20),
    )
    return {
        "n_rows": len(rows),
        "n_scored": len(usable),
        "combination_rule": COMBINATION_RULE,
        "by_y": by_y,
        "axes": axes,
        "agreement": {
            "model_vs_human_pairwise": agree,
            "model_vs_majority_agreement": agree_maj,
            "model_vs_majority_kappa": kappa,
            "model_material_rate": mean([float(x) for x in model_bits]),
            "majority_rate": mean([float(x) for x in majority]),
        },
        "frozen_predicates": predicates,
    }


def format_auroc_row(block: dict) -> str:
    ci = block.get("ci95") or [None, None]
    v = block.get("value")
    if v is None:
        return "NA"
    lo, hi = ci
    if lo is None or hi is None:
        return f"{v:.3f}"
    return f"{v:.3f} ({lo:.3f}, {hi:.3f})"


def print_tables(summary: dict) -> None:
    model = summary.get("model") or {}
    cost = summary.get("cost") or {}
    print(f"model: {model.get('id')}")
    print(
        f"prices per token: prompt={model.get('prompt_price')} "
        f"completion={model.get('completion_price')}"
    )
    print(
        f"n={summary.get('n')} cached={cost.get('n_cached')} "
        f"fetched={cost.get('n_fetched')} spend_usd={cost.get('total_usd')}"
    )
    print(f"wall_clock_s={cost.get('wall_clock_s')} cost_per_item={cost.get('usd_per_item')}")
    print(f"combination: {summary.get('combination_rule')}")
    print()
    print("AUROC (1,000-rep bootstrap 95% CI)")
    print(f"{'Y':<14} {'s':<28} {'p_invalid':<28}")
    for name, block in (summary.get("by_y") or {}).items():
        print(
            f"{name:<14} {format_auroc_row(block['auroc_s']):<28} "
            f"{format_auroc_row(block['auroc_p_invalid']):<28}"
        )
    axes = summary.get("axes") or {}
    print()
    print("Per-axis AUROC")
    u = axes.get("underspecified_ge2") or {}
    fn = axes.get("false_negative_ge2") or {}
    print(
        "underspecified vs human>=2:",
        format_auroc_row(u.get("auroc_model_underspecified") or {}),
    )
    print(
        "false_negative vs human>=2:",
        format_auroc_row(fn.get("auroc_model_false_negative") or {}),
    )
    agr = summary.get("agreement") or {}
    print()
    print(
        f"model vs majority kappa={agr.get('model_vs_majority_kappa')} "
        f"agreement={agr.get('model_vs_majority_agreement')}"
    )
    pair = agr.get("model_vs_human_pairwise") or {}
    print(f"model vs human pairwise agreement={pair.get('agreement')}")
    print()
    print("Retain-tail residual invalidity (conservative Y)")
    cons = (summary.get("by_y") or {}).get("conservative") or {}
    retain = cons.get("retain") or {}
    print(f"{'rule':<22} {'5%':>8} {'10%':>8} {'20%':>8}")
    for key, label in (
        ("s", "s"),
        ("one_minus_p_i", "1-p_i"),
        ("p_logistic", "p_logistic"),
        ("combination", "z(s)+z(1-p_i)"),
    ):
        rows = retain.get(key) or []
        vals = {r["retain_frac"]: r["residual_invalid"] for r in rows}
        print(
            f"{label:<22} {vals.get(0.05, float('nan')):8.3f} "
            f"{vals.get(0.10, float('nan')):8.3f} "
            f"{vals.get(0.20, float('nan')):8.3f}"
        )
    print()
    pred = summary.get("frozen_predicates") or {}
    print("Frozen predicates:", "PASS" if pred.get("all_pass") else "FAIL")
    for key in ("F1", "F2", "F3"):
        block = pred.get(key) or {}
        print(f"  {key} {'PASS' if block.get('pass') else 'FAIL'}: {block.get('text')}")
    print(f"total spend usd: {cost.get('total_usd')}")


def calibration_deciles(
    p_inv: list[float],
    y: list[int],
    n_bins: int = 10,
) -> list[dict]:
    """Equal-count bins of p_invalid vs observed majority-invalid rate."""

    n = len(p_inv)
    if n == 0 or n != len(y) or n_bins < 1:
        return []
    order = sorted(range(n), key=lambda i: (p_inv[i], i))
    rows = []
    for b in range(n_bins):
        lo = (b * n) // n_bins
        hi = ((b + 1) * n) // n_bins
        idx = order[lo:hi]
        if not idx:
            continue
        ps = [p_inv[i] for i in idx]
        ys = [int(y[i]) for i in idx]
        rows.append(
            {
                "decile": b + 1,
                "n": len(idx),
                "p_invalid_min": min(ps),
                "p_invalid_max": max(ps),
                "p_invalid_mean": mean(ps),
                "majority_invalid_rate": mean([float(v) for v in ys]),
                "n_majority_invalid": sum(ys),
            }
        )
    return rows


def auroc_by_repository(
    rows: list[dict],
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    grouped: dict[str, list[dict]] = {}
    for rec in rows:
        grouped.setdefault(str(rec.get("repository") or "unknown"), []).append(rec)
    out = {}
    for repo, grp in sorted(grouped.items()):
        s = [float(r["s"]) for r in grp]
        p_inv = [float(r["p_invalid"]) for r in grp]
        block: dict = {"n": len(grp)}
        for name, field in Y_KEYS:
            y = [int(r.get(field) or 0) for r in grp]
            block[name] = {
                "n_invalid": sum(y),
                "base_rate": mean([float(t) for t in y]),
                "auroc_s": bootstrap_auroc(y, s, n_reps=n_bootstrap, seed=seed),
                "auroc_p_invalid": bootstrap_auroc(
                    y, p_inv, n_reps=n_bootstrap, seed=seed + 1
                ),
            }
        out[repo] = block
    return out


def analyze_full_rows(
    rows: list[dict],
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """Population analysis for the full 1,699 plus by-repo and calibration."""

    base = analyze_rows(rows, n_bootstrap=n_bootstrap, seed=seed)
    usable = [
        r
        for r in rows
        if r.get("s") is not None
        and r.get("p_invalid") is not None
        and r.get("openai_2024_conservative") is not None
        and r.get("majority_invalid") is not None
    ]
    p_inv = [float(r["p_invalid"]) for r in usable]
    majority = [int(r["majority_invalid"] or 0) for r in usable]
    base["calibration_p_invalid_deciles"] = calibration_deciles(p_inv, majority)
    base["by_repository"] = auroc_by_repository(
        usable, n_bootstrap=n_bootstrap, seed=seed + 10
    )
    return base


def print_full_tables(summary: dict) -> None:
    print_tables(summary)
    print()
    print("AUROC by repository (p_invalid vs majority)")
    by_repo = summary.get("by_repository") or {}
    print(f"{'repo':<16} {'n':>5} {'maj_rate':>8} {'auroc_p':<28} {'auroc_s':<28}")
    for repo, block in by_repo.items():
        maj = block.get("majority") or {}
        print(
            f"{repo:<16} {block.get('n', 0):5d} "
            f"{(maj.get('base_rate') if maj.get('base_rate') is not None else float('nan')):8.3f} "
            f"{format_auroc_row(maj.get('auroc_p_invalid') or {}):<28} "
            f"{format_auroc_row(maj.get('auroc_s') or {}):<28}"
        )
    print()
    print("Calibration: p_invalid deciles vs majority-invalid rate")
    print(
        f"{'decile':>6} {'n':>5} {'p_mean':>8} {'p_min':>8} {'p_max':>8} {'maj_rate':>8}"
    )
    for row in summary.get("calibration_p_invalid_deciles") or []:
        print(
            f"{row['decile']:6d} {row['n']:5d} {row['p_invalid_mean']:8.3f} "
            f"{row['p_invalid_min']:8.3f} {row['p_invalid_max']:8.3f} "
            f"{row['majority_invalid_rate']:8.3f}"
        )
    cost = summary.get("cost") or {}
    print()
    print(
        f"full spend usd={cost.get('total_usd')} new={cost.get('new_usd')} "
        f"cached={cost.get('cached_usd')} cap={cost.get('cap_usd')}"
    )


def _mean_or(xs: list[float], fallback: float) -> float:
    return sum(xs) / len(xs) if xs else fallback


def run_full(
    *,
    compact_path: Path,
    raters_path: Path,
    oof_path: Path,
    irt_path: Path,
    parquet_path: Path,
    out_path: Path,
    summary_path: Path,
    cache_root: Path,
    api_key: str | None,
    max_usd: float = FULL_MAX_USD,
    concurrency: int = FULL_CONCURRENCY,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict:
    """Audit the full labeled population. Reuses the n=200 cache. Does not
    rewrite the n=200 gold files.
    """

    compact = load_jsonl(compact_path)
    population = sorted(compact.keys())
    if len(population) != 1699:
        raise SystemExit(f"expected 1699 labeled items, got {len(population)}")

    model_id_guess = "x-ai/grok-4.6"
    cached_recs: dict[str, dict] = {}
    pending: list[str] = []
    cached_prompt: list[int] = []
    cached_completion: list[int] = []
    cached_usd = 0.0
    for tid in population:
        rec = load_cache(cache_path(cache_root, model_id_guess, tid))
        if rec is not None:
            rec["cached"] = True
            cached_recs[tid] = rec
            cached_prompt.append(int(rec.get("prompt_tokens") or 0))
            cached_completion.append(int(rec.get("completion_tokens") or 0))
            cached_usd += float(rec.get("cost_usd") or 0.0)
            if rec.get("model"):
                model_id_guess = rec["model"]
        else:
            pending.append(tid)

    model: dict | None = None
    if api_key:
        catalog = fetch_openrouter_models(api_key)
        model = pick_model(catalog)
    elif pending:
        raise SystemExit("OPENROUTER_API_KEY is not set and uncached ids remain")
    else:
        model = {
            "id": model_id_guess,
            "name": model_id_guess,
            "prompt_price": 0.000002,
            "completion_price": 0.000006,
            "pricing": {"prompt": "0.000002", "completion": "0.000006"},
        }

    mean_pt = _mean_or(cached_prompt, 2792.0)
    mean_ct = _mean_or(cached_completion, float(PRIOR_MEAN_COMPLETION_TOKENS))
    proj_pending_usd = len(pending) * (
        mean_pt * float(model["prompt_price"])
        + mean_ct * float(model["completion_price"])
    )
    projection = {
        "n_population": len(population),
        "n_cached": len(cached_recs),
        "n_pending": len(pending),
        "mean_prompt_tokens_cached": mean_pt,
        "mean_completion_tokens_cached": mean_ct,
        "est_pending_usd": proj_pending_usd,
        "est_total_usd": cached_usd + proj_pending_usd,
        "method": "cached-token-means times pending count",
    }
    print(
        f"model={model['id']} n={len(population)} cached={len(cached_recs)} "
        f"pending={len(pending)} projected_pending_usd={proj_pending_usd:.4f} "
        f"cap={max_usd}",
        file=sys.stderr,
        flush=True,
    )
    if pending and proj_pending_usd > max_usd:
        print(
            f"warning: projected pending ${proj_pending_usd:.2f} exceeds cap "
            f"${max_usd:.2f}; hard stop still applies",
            file=sys.stderr,
            flush=True,
        )

    prompts: dict[str, dict] = {}
    if pending:
        instances = load_swe_instances(pending, parquet_path)
        prompts = {tid: build_prompt(instances[tid]) for tid in pending}

    spent_lock = Lock()
    spent = {"usd": 0.0, "stop": False}
    t0 = time.perf_counter()
    results: dict[str, dict] = dict(cached_recs)

    def work(tid: str) -> dict:
        with spent_lock:
            if spent["stop"]:
                return {
                    "task_id": tid,
                    "s": None,
                    "error": "spend_cap",
                    "cached": False,
                    "cost_usd": 0.0,
                }
        try:
            rec = audit_one(
                tid,
                prompts[tid]["messages"],
                prompts[tid]["truncated"],
                model,
                api_key,
                cache_root,
            )
        except Exception as err:
            rec = {
                "task_id": tid,
                "s": None,
                "p_invalid": None,
                "error": f"uncaught: {err}",
                "cached": False,
                "cost_usd": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        with spent_lock:
            if not rec.get("cached"):
                spent["usd"] += float(rec.get("cost_usd") or 0.0)
                if spent["usd"] >= max_usd:
                    spent["stop"] = True
        return rec

    fetched: list[str] = []
    if pending:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futs = {pool.submit(work, tid): tid for tid in pending}
            done_n = 0
            for fut in as_completed(futs):
                rec = fut.result()
                results[rec["task_id"]] = rec
                fetched.append(rec["task_id"])
                done_n += 1
                if done_n % 10 == 0 or done_n == len(pending):
                    print(
                        f"fetched {done_n}/{len(pending)} spent_usd={spent['usd']:.4f}",
                        file=sys.stderr,
                        flush=True,
                    )

    errors = [
        tid
        for tid in population
        if results.get(tid) is None or results[tid].get("s") is None
    ]
    if errors and api_key and spent["usd"] < max_usd:
        print(f"retrying {len(errors)} errors", file=sys.stderr, flush=True)
        still = []
        for tid in errors:
            if tid not in prompts:
                try:
                    inst = load_swe_instances([tid], parquet_path)
                    prompts[tid] = build_prompt(inst[tid])
                except Exception as err:
                    still.append(tid)
                    results[tid] = {
                        "task_id": tid,
                        "s": None,
                        "error": f"prompt: {err}",
                        "cached": False,
                        "cost_usd": 0.0,
                    }
                    continue
            rec = work(tid)
            results[tid] = rec
            if rec.get("s") is None:
                still.append(tid)
        errors = still

    wall = time.perf_counter() - t0
    raters = load_jsonl(raters_path)
    oof = load_jsonl(oof_path)
    irt = load_irt_p(irt_path)

    joined = []
    n_error = 0
    total_usd = 0.0
    prompt_tokens = 0
    completion_tokens = 0
    new_usd = 0.0
    for tid in population:
        rec = results.get(tid) or {"task_id": tid, "s": None, "error": "missing"}
        if rec.get("s") is None:
            n_error += 1
        cost_i = float(rec.get("cost_usd") or 0.0)
        total_usd += cost_i
        if not rec.get("cached"):
            new_usd += cost_i
        prompt_tokens += int(rec.get("prompt_tokens") or 0)
        completion_tokens += int(rec.get("completion_tokens") or 0)
        audit = {
            "task_id": tid,
            "underspecified": rec.get("underspecified"),
            "false_negative": rec.get("false_negative"),
            "other_major_issue": rec.get("other_major_issue"),
            "other_reason": rec.get("other_reason"),
            "confidence": rec.get("confidence"),
            "rationale": rec.get("rationale"),
            "p_invalid": rec.get("p_invalid"),
            "s": rec.get("s"),
            "model_material": rec.get("model_material"),
            "prompt_tokens": rec.get("prompt_tokens"),
            "completion_tokens": rec.get("completion_tokens"),
            "total_tokens": rec.get("total_tokens"),
            "cost_usd": rec.get("cost_usd"),
            "truncated": rec.get("truncated"),
            "cached": rec.get("cached"),
            "error": rec.get("error"),
            "model": rec.get("model") or model["id"],
        }
        joined.append(
            join_row(
                audit,
                compact.get(tid) or {},
                raters.get(tid) or {},
                irt.get(tid) or {},
                oof.get(tid) or {},
            )
        )

    n_item = max(len(population), 1)
    cost_block = {
        "total_usd": total_usd,
        "new_usd": new_usd,
        "cached_usd": cached_usd,
        "usd_per_item": total_usd / n_item,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "n_cached": len(cached_recs),
        "n_fetched": sum(1 for tid in fetched if not cached_recs.get(tid)),
        "n_error": n_error,
        "wall_clock_s": wall,
        "projected_pending_usd": projection["est_pending_usd"],
        "cap_usd": max_usd,
        "concurrency": concurrency,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in joined:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    analysis = analyze_full_rows(joined, n_bootstrap=n_bootstrap, seed=BOOTSTRAP_SEED)
    summary = {
        "schema": "swe_llm_audit_full.summary.v1",
        "model": model,
        "population": {
            "design": "census of the 1,699 labeled SWE-bench 2024 items",
            "N": len(population),
            "ids_sorted": True,
        },
        "prompt": {
            "system": SYSTEM_PROMPT,
            "token_budget": TOKEN_BUDGET,
            "temperature": TEMPERATURE,
            "labels_in_prompt": False,
            "reasoning": {"effort": "low"},
            "fields": [
                "issue",
                "test_patch",
                "FAIL_TO_PASS names",
                "gold patch",
                "repo",
                "base_commit",
            ],
        },
        "combination_rule": COMBINATION_RULE,
        "projection": projection,
        "cost": cost_block,
        "n": len(population),
        "n_scored": analysis["n_scored"],
        "by_y": analysis["by_y"],
        "axes": analysis["axes"],
        "agreement": analysis["agreement"],
        "frozen_predicates": analysis["frozen_predicates"],
        "by_repository": analysis["by_repository"],
        "calibration_p_invalid_deciles": analysis["calibration_p_invalid_deciles"],
        "artifacts": {
            "jsonl": str(out_path),
            "summary": str(summary_path),
            "cache_root": str(cache_root / model["id"]),
        },
        "constraints": {
            "stdlib_runtime": True,
            "labels_never_in_prompt": True,
            "one_pass_no_retune": True,
            "reused_n200_cache": True,
            "did_not_rewrite_n200_gold": True,
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print_full_tables(summary)
    if n_error:
        print(f"ERROR: {n_error} unscored items", file=sys.stderr, flush=True)
    return summary


def model_card(raw: dict) -> dict:
    pricing = raw.get("pricing") or {}
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "context_length": raw.get("context_length"),
        "prompt_price": float(pricing.get("prompt") or 0.0),
        "completion_price": float(pricing.get("completion") or 0.0),
        "pricing": pricing,
        "reasoning": raw.get("reasoning"),
        "supported_parameters": raw.get("supported_parameters"),
    }


def pick_model(catalog: list[dict]) -> dict:
    """Prefer grok 4.6, else grok-4-fast / grok-4.1-fast, else cheapest 128k major."""

    by_id = {m.get("id"): m for m in catalog if m.get("id")}
    if "x-ai/grok-4.6" in by_id:
        return model_card(by_id["x-ai/grok-4.6"])
    family = [
        m
        for m in catalog
        if str(m.get("id") or "").startswith("x-ai/grok-4.6")
        and ":batch" not in str(m.get("id"))
    ]
    if family:
        return model_card(family[0])
    for fid in ("x-ai/grok-4-fast", "x-ai/grok-4.1-fast"):
        if fid in by_id:
            return model_card(by_id[fid])
    for m in catalog:
        mid = str(m.get("id") or "")
        if "grok-4-fast" in mid or "grok-4.1-fast" in mid:
            return model_card(m)

    def price_key(m: dict) -> tuple[float, float]:
        pricing = m.get("pricing") or {}
        try:
            return (float(pricing.get("prompt") or 1e9), float(pricing.get("completion") or 1e9))
        except (TypeError, ValueError):
            return (1e9, 1e9)

    cands = []
    for m in catalog:
        mid = str(m.get("id") or "")
        if ":free" in mid or ":batch" in mid:
            continue
        if not any(mid.startswith(p) for p in MAJOR_PREFIXES):
            continue
        ctx = m.get("context_length") or 0
        if ctx < 128000:
            continue
        cands.append(m)
    if not cands:
        raise RuntimeError("no eligible OpenRouter model")
    cands.sort(key=price_key)
    return model_card(cands[0])


def fetch_openrouter_models(api_key: str) -> list[dict]:
    req = urllib.request.Request(
        OPENROUTER_MODELS,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return list(payload.get("data") or [])


def usage_tokens(response: dict) -> tuple[int, int, int]:
    usage = response.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    details = usage.get("completion_tokens_details") or {}
    reasoning = int(details.get("reasoning_tokens") or 0)
    if completion == 0 and reasoning:
        completion = reasoning
    total = int(usage.get("total_tokens") or (prompt + completion))
    return prompt, completion, total


def cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    prompt_price: float,
    completion_price: float,
) -> float:
    return prompt_tokens * prompt_price + completion_tokens * completion_price


def project_cost(
    est_prompt_tokens: list[int],
    prompt_price: float,
    completion_price: float,
    completion_tokens: int = EXPECTED_COMPLETION_TOKENS,
) -> dict:
    n = len(est_prompt_tokens)
    prompt_cost = sum(est_prompt_tokens) * prompt_price
    completion_cost = n * completion_tokens * completion_price
    return {
        "n": n,
        "est_prompt_tokens": int(sum(est_prompt_tokens)),
        "est_completion_tokens": n * completion_tokens,
        "est_usd": prompt_cost + completion_cost,
        "completion_tokens_assumed": completion_tokens,
    }


def cache_path(cache_root: Path, model_id: str, task_id: str) -> Path:
    return cache_root / model_id / f"{task_id}.json"


def load_cache(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if rec.get("parsed") and rec.get("s") is not None:
        return rec
    return None


def write_json_atomic(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def xai_api_token() -> str | None:
    """Grok.com / xAI session token. Used only if OpenRouter returns 402."""

    path = Path.home() / ".grok" / "auth.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for rec in data.values():
        if isinstance(rec, dict) and rec.get("key"):
            return str(rec["key"])
    return None


def xai_chat(
    payload: dict,
    token: str,
    timeout: int = 240,
) -> tuple[int, dict]:
    """Same grok-4.6 chat as OpenRouter, via api.x.ai."""

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        XAI_CHAT,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.getcode() or 200), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", "replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"error": raw}
        return int(err.code), data
    except urllib.error.URLError as err:
        return 0, {"error": str(err.reason if getattr(err, "reason", None) else err)}
    except TimeoutError as err:
        return 0, {"error": f"timeout: {err}"}


def _xai_payload(messages: list[dict], max_tokens: int = 2048) -> dict:
    return {
        "model": "grok-4.6",
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
        "reasoning_effort": "low",
    }


def openrouter_chat(
    payload: dict,
    api_key: str,
    timeout: int = 240,
) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_CHAT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/task-validation",
            "X-Title": "task-validation llm-spec-audit",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.getcode() or 200), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", "replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"error": raw}
        return int(err.code), data
    except urllib.error.URLError as err:
        return 0, {"error": str(err.reason if getattr(err, "reason", None) else err)}
    except TimeoutError as err:
        return 0, {"error": f"timeout: {err}"}


def should_retry(status: int) -> bool:
    # 402 from OpenRouter is often "in-flight credits", not an empty wallet.
    if status in (0, 402, 408, 409, 425, 429):
        return True
    return 500 <= status <= 599


def _success_record(
    *,
    task_id: str,
    model: dict,
    messages: list[dict],
    truncated: dict,
    response: dict,
    parsed: dict,
    http_status: int,
    api: str,
    request_meta: dict,
) -> dict:
    prompt_tok, comp_tok, total_tok = usage_tokens(response)
    details = (response.get("usage") or {}).get("completion_tokens_details") or {}
    reasoning = int(details.get("reasoning_tokens") or 0)
    if reasoning and comp_tok < reasoning:
        comp_tok = comp_tok + reasoning
        total_tok = prompt_tok + comp_tok
    ticks = (response.get("usage") or {}).get("cost_in_usd_ticks")
    return {
        "task_id": task_id,
        "model": model["id"],
        "api": api,
        "request": request_meta,
        "response": response,
        "http_status": http_status,
        "parsed": {k: parsed[k] for k in (
            "underspecified",
            "false_negative",
            "other_major_issue",
            "other_reason",
            "confidence",
            "rationale",
            "p_invalid",
        )},
        "s": parsed["s"],
        "p_invalid": parsed["p_invalid"],
        "model_material": parsed["model_material"],
        "underspecified": parsed["underspecified"],
        "false_negative": parsed["false_negative"],
        "other_major_issue": parsed["other_major_issue"],
        "other_reason": parsed["other_reason"],
        "confidence": parsed["confidence"],
        "rationale": parsed["rationale"],
        "prompt_tokens": prompt_tok,
        "completion_tokens": comp_tok,
        "total_tokens": total_tok,
        "cost_usd": cost_usd(
            prompt_tok,
            comp_tok,
            model["prompt_price"],
            model["completion_price"],
        ),
        "cost_in_usd_ticks": ticks,
        "truncated": truncated,
        "cached": False,
        "error": None,
        "est_prompt_tokens": estimate_tokens("\n".join(m["content"] for m in messages)),
    }


def _audit_via_xai(
    task_id: str,
    messages: list[dict],
    truncated: dict,
    model: dict,
    cache_path_out: Path,
    *,
    max_retries: int,
) -> dict | None:
    token = xai_api_token()
    if not token:
        return None
    payload = _xai_payload(messages)
    last_error = None
    response: dict = {}
    status = 0
    for attempt in range(max_retries):
        status, response = xai_chat(payload, token)
        if status == 200:
            try:
                parsed = score_parsed(parse_response(response))
                rec = _success_record(
                    task_id=task_id,
                    model=model,
                    messages=messages,
                    truncated=truncated,
                    response=response,
                    parsed=parsed,
                    http_status=status,
                    api="xai",
                    request_meta={
                        "temperature": TEMPERATURE,
                        "max_tokens": payload.get("max_tokens"),
                        "reasoning_effort": "low",
                        "backend": "api.x.ai",
                    },
                )
                write_json_atomic(cache_path_out, rec)
                return rec
            except (ValueError, TypeError, json.JSONDecodeError) as err:
                last_error = f"xai parse: {err}"
                time.sleep(min(2 ** attempt, 8))
                continue
        if not should_retry(status):
            last_error = f"xai http {status}: {response}"
            break
        delay = min(2 ** attempt, 60)
        last_error = f"xai http {status}"
        time.sleep(delay)
    return None


def audit_one(
    task_id: str,
    messages: list[dict],
    truncated: dict,
    model: dict,
    api_key: str,
    cache_root: Path,
    *,
    max_retries: int = 6,
) -> dict:
    global _PREFER_XAI
    path = cache_path(cache_root, model["id"], task_id)
    cached = load_cache(path)
    if cached is not None:
        cached["cached"] = True
        return cached
    payload = {
        "model": model["id"],
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": 4096,
        "reasoning": {"effort": "low"},
        "response_format": {"type": "json_object"},
    }
    status = 0
    response: dict = {}
    last_error = None
    dropped_json_mode = False
    with _XAI_LOCK:
        skip_openrouter = _PREFER_XAI
    if api_key and not skip_openrouter:
        for attempt in range(max_retries):
            status, response = openrouter_chat(payload, api_key)
            if status == 400 and not dropped_json_mode:
                payload = dict(payload)
                payload.pop("response_format", None)
                dropped_json_mode = True
                continue
            if status == 200:
                try:
                    parsed = score_parsed(parse_response(response))
                    rec = _success_record(
                        task_id=task_id,
                        model=model,
                        messages=messages,
                        truncated=truncated,
                        response=response,
                        parsed=parsed,
                        http_status=status,
                        api="openrouter",
                        request_meta={
                            "temperature": TEMPERATURE,
                            "max_tokens": payload.get("max_tokens"),
                            "reasoning": payload.get("reasoning"),
                        },
                    )
                    write_json_atomic(path, rec)
                    return rec
                except (ValueError, TypeError, json.JSONDecodeError) as err:
                    last_error = f"parse: {err}"
                    if attempt + 1 >= max_retries:
                        break
                    time.sleep(min(2 ** attempt, 8))
                    continue
            if status == 402:
                with _XAI_LOCK:
                    _PREFER_XAI = True
                last_error = f"http {status}: {response}"
                break
            if not should_retry(status):
                last_error = f"http {status}: {response}"
                break
            delay = min(2 ** attempt, 60)
            retry_after = None
            err_obj = response.get("error") if isinstance(response, dict) else None
            if isinstance(err_obj, dict):
                retry_after = err_obj.get("retry_after")
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except (TypeError, ValueError):
                    pass
            last_error = f"http {status}"
            time.sleep(delay)
    xai_rec = _audit_via_xai(
        task_id, messages, truncated, model, path, max_retries=max_retries
    )
    if xai_rec is not None:
        return xai_rec
    rec = {
        "task_id": task_id,
        "model": model["id"],
        "response": response,
        "http_status": status,
        "parsed": None,
        "s": None,
        "p_invalid": None,
        "error": last_error or f"http {status}",
        "truncated": truncated,
        "cached": False,
        "cost_usd": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    write_json_atomic(path, rec)
    return rec


def load_compact_ids(path: Path) -> list[str]:
    ids = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            ids.append(json.loads(line)["task_id"])
    return ids


def load_swe_instances(ids: list[str], parquet_path: Path) -> dict[str, dict]:
    wanted = set(ids)
    if parquet_path.is_file():
        import pandas as pd

        df = pd.read_parquet(parquet_path)
        out = {}
        for _, art in df.iterrows():
            tid = art["instance_id"]
            if tid not in wanted:
                continue
            out[tid] = {
                "task_id": tid,
                "instance_id": tid,
                "problem_statement": art.get("problem_statement") or "",
                "patch": art.get("patch") or "",
                "test_patch": art.get("test_patch") or "",
                "FAIL_TO_PASS": art.get("FAIL_TO_PASS"),
                "PASS_TO_PASS": art.get("PASS_TO_PASS"),
                "repo": art.get("repo") or "",
                "base_commit": art.get("base_commit") or "",
            }
        missing = sorted(wanted - set(out))
        if missing:
            raise RuntimeError(f"parquet missing {len(missing)} ids, e.g. {missing[:3]}")
        return out
    from datasets import load_dataset

    ds = load_dataset("SWE-bench/SWE-bench", split="test")
    out = {}
    for art in ds:
        tid = art["instance_id"]
        if tid not in wanted:
            continue
        out[tid] = {
            "task_id": tid,
            "instance_id": tid,
            "problem_statement": art.get("problem_statement") or "",
            "patch": art.get("patch") or "",
            "test_patch": art.get("test_patch") or "",
            "FAIL_TO_PASS": art.get("FAIL_TO_PASS"),
            "PASS_TO_PASS": art.get("PASS_TO_PASS"),
            "repo": art.get("repo") or "",
            "base_commit": art.get("base_commit") or "",
        }
    missing = sorted(wanted - set(out))
    if missing:
        raise RuntimeError(f"HF dataset missing {len(missing)} ids, e.g. {missing[:3]}")
    return out


def load_irt_p(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data["items"] if isinstance(data, dict) else data
    return {it["task_id"]: it for it in items}


def write_sample_file(
    path: Path,
    ids: list[str],
    *,
    n_requested: int,
    reduced: bool,
    seed: str,
    n_population: int,
) -> dict:
    rec = {
        "design": "SRS without replacement",
        "N": n_population,
        "n": len(ids),
        "n_requested": n_requested,
        "seed": seed,
        "seed_int": str(seed_to_int(seed)),
        "seed_note": "sha256(seed utf-8) interpreted as a big-endian int",
        "reduced_to_150_for_cost_cap": reduced,
        "ids": sorted(ids),
        "draw_order": list(ids),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def run(
    *,
    compact_path: Path,
    raters_path: Path,
    oof_path: Path,
    irt_path: Path,
    parquet_path: Path,
    sample_path: Path,
    out_path: Path,
    summary_path: Path,
    cache_root: Path,
    api_key: str | None,
    n: int = SAMPLE_N,
    seed: str = SAMPLE_SEED,
    max_usd: float = MAX_USD,
    concurrency: int = CONCURRENCY,
    estimate_only: bool = False,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict:
    compact = load_jsonl(compact_path)
    population = sorted(compact.keys())
    if len(population) != 1699:
        raise SystemExit(f"expected 1699 labeled items, got {len(population)}")
    draw = draw_sample(population, n, seed)
    reduced = False
    sample_meta = write_sample_file(
        sample_path,
        draw,
        n_requested=n,
        reduced=False,
        seed=seed,
        n_population=len(population),
    )
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    catalog = fetch_openrouter_models(api_key)
    model = pick_model(catalog)
    instances = load_swe_instances(draw, parquet_path)
    prompts = {tid: build_prompt(instances[tid]) for tid in draw}
    projection = project_cost(
        [prompts[tid]["est_prompt_tokens"] for tid in draw],
        model["prompt_price"],
        model["completion_price"],
    )
    if projection["est_usd"] > max_usd and n > SAMPLE_N_REDUCED:
        n = SAMPLE_N_REDUCED
        draw = draw[:n]
        reduced = True
        sample_meta = write_sample_file(
            sample_path,
            draw,
            n_requested=SAMPLE_N,
            reduced=True,
            seed=seed,
            n_population=len(population),
        )
        prompts = {tid: prompts[tid] for tid in draw}
        projection = project_cost(
            [prompts[tid]["est_prompt_tokens"] for tid in draw],
            model["prompt_price"],
            model["completion_price"],
        )
    if projection["est_usd"] > max_usd:
        raise SystemExit(
            f"projected cost ${projection['est_usd']:.2f} exceeds cap ${max_usd:.2f}"
        )
    print(
        f"model={model['id']} prompt_price={model['prompt_price']} "
        f"completion_price={model['completion_price']} n={len(draw)} "
        f"projected_usd={projection['est_usd']:.4f} reduced={reduced}",
        file=sys.stderr,
        flush=True,
    )
    if estimate_only:
        summary = {
            "schema": "swe_llm_audit.summary.v1",
            "model": model,
            "sample": sample_meta,
            "cost": {"projected_usd": projection["est_usd"], "total_usd": 0.0},
            "projection": projection,
            "frozen_predicates": FROZEN_PREDICATES,
            "combination_rule": COMBINATION_RULE,
            "estimate_only": True,
        }
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print_tables(
            {
                **summary,
                "n": len(draw),
                "by_y": {},
                "axes": {},
                "agreement": {},
                "frozen_predicates": {"all_pass": False},
            }
        )
        return summary

    raters = load_jsonl(raters_path)
    oof = load_jsonl(oof_path)
    irt = load_irt_p(irt_path)
    spent_lock = Lock()
    spent = {"usd": 0.0, "stop": False}
    t0 = time.perf_counter()
    results: dict[str, dict] = {}

    def work(tid: str) -> dict:
        with spent_lock:
            if spent["stop"]:
                return {"task_id": tid, "s": None, "error": "spend_cap", "cached": False, "cost_usd": 0.0}
        try:
            rec = audit_one(
                tid,
                prompts[tid]["messages"],
                prompts[tid]["truncated"],
                model,
                api_key,
                cache_root,
            )
        except Exception as err:
            rec = {
                "task_id": tid,
                "s": None,
                "p_invalid": None,
                "error": f"uncaught: {err}",
                "cached": False,
                "cost_usd": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        with spent_lock:
            if not rec.get("cached"):
                spent["usd"] += float(rec.get("cost_usd") or 0.0)
                if spent["usd"] >= max_usd:
                    spent["stop"] = True
        return rec

    pending = []
    n_cached = 0
    for tid in draw:
        cached = load_cache(cache_path(cache_root, model["id"], tid))
        if cached is not None:
            cached["cached"] = True
            results[tid] = cached
            n_cached += 1
        else:
            pending.append(tid)

    fetched = []
    if pending:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futs = {pool.submit(work, tid): tid for tid in pending}
            done_n = 0
            for fut in as_completed(futs):
                rec = fut.result()
                results[rec["task_id"]] = rec
                fetched.append(rec["task_id"])
                done_n += 1
                if done_n % 10 == 0 or done_n == len(pending):
                    print(
                        f"fetched {done_n}/{len(pending)} spent_usd={spent['usd']:.4f}",
                        file=sys.stderr,
                        flush=True,
                    )
    wall = time.perf_counter() - t0

    joined = []
    n_error = 0
    total_usd = 0.0
    prompt_tokens = 0
    completion_tokens = 0
    for tid in draw:
        rec = results.get(tid) or {"task_id": tid, "s": None, "error": "missing"}
        if rec.get("s") is None:
            n_error += 1
        total_usd += float(rec.get("cost_usd") or 0.0)
        prompt_tokens += int(rec.get("prompt_tokens") or 0)
        completion_tokens += int(rec.get("completion_tokens") or 0)
        audit = {
            "task_id": tid,
            "underspecified": rec.get("underspecified"),
            "false_negative": rec.get("false_negative"),
            "other_major_issue": rec.get("other_major_issue"),
            "other_reason": rec.get("other_reason"),
            "confidence": rec.get("confidence"),
            "rationale": rec.get("rationale"),
            "p_invalid": rec.get("p_invalid"),
            "s": rec.get("s"),
            "model_material": rec.get("model_material"),
            "prompt_tokens": rec.get("prompt_tokens"),
            "completion_tokens": rec.get("completion_tokens"),
            "total_tokens": rec.get("total_tokens"),
            "cost_usd": rec.get("cost_usd"),
            "truncated": rec.get("truncated"),
            "cached": rec.get("cached"),
            "error": rec.get("error"),
            "model": rec.get("model") or model["id"],
        }
        joined.append(
            join_row(
                audit,
                compact.get(tid) or {},
                raters.get(tid) or {},
                irt.get(tid) or {},
                oof.get(tid) or {},
            )
        )

    analysis = analyze_rows(joined, n_bootstrap=n_bootstrap, seed=BOOTSTRAP_SEED)
    n_item = max(len(draw), 1)
    cost_block = {
        "total_usd": total_usd,
        "usd_per_item": total_usd / n_item,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "n_cached": n_cached,
        "n_fetched": len(fetched),
        "n_error": n_error,
        "wall_clock_s": wall,
        "projected_usd": projection["est_usd"],
        "cap_usd": max_usd,
        "concurrency": concurrency,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in joined:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "schema": "swe_llm_audit.summary.v1",
        "model": model,
        "sample": sample_meta,
        "prompt": {
            "system": SYSTEM_PROMPT,
            "token_budget": TOKEN_BUDGET,
            "temperature": TEMPERATURE,
            "labels_in_prompt": False,
            "fields": [
                "issue",
                "test_patch",
                "FAIL_TO_PASS names",
                "gold patch",
                "repo",
                "base_commit",
            ],
        },
        "combination_rule": COMBINATION_RULE,
        "frozen_predicate_text": FROZEN_PREDICATES,
        "projection": projection,
        "cost": cost_block,
        "n": len(draw),
        "n_scored": analysis["n_scored"],
        "by_y": analysis["by_y"],
        "axes": analysis["axes"],
        "agreement": analysis["agreement"],
        "frozen_predicates": analysis["frozen_predicates"],
        "artifacts": {
            "sample": str(sample_path),
            "jsonl": str(out_path),
            "summary": str(summary_path),
            "cache_root": str(cache_root / model["id"]),
        },
        "constraints": {
            "stdlib_runtime": True,
            "labels_never_in_prompt": True,
            "one_pass_no_retune": True,
            "severity_not_used_as_features": True,
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print_tables(summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LLM spec-invalidity audit of SWE-bench 2024")
    p.add_argument(
        "--compact",
        type=Path,
        default=REPO_ROOT / "data/gold/swe_verified_compact.jsonl",
    )
    p.add_argument(
        "--raters",
        type=Path,
        default=REPO_ROOT / "data/gold/swe_rater_targets.jsonl",
    )
    p.add_argument(
        "--oof",
        type=Path,
        default=REPO_ROOT / "data/gold/oof_openai_2024_conservative.oof.jsonl",
    )
    p.add_argument("--irt", type=Path, default=REPO_ROOT / "data/gold/swe_irt.json")
    p.add_argument(
        "--parquet",
        type=Path,
        default=REPO_ROOT / "data/raw/swe-bench/test.parquet",
    )
    p.add_argument(
        "--sample-out",
        type=Path,
        default=REPO_ROOT / "data/gold/swe_llm_audit_sample.json",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data/gold/swe_llm_audit.jsonl",
    )
    p.add_argument(
        "--summary",
        type=Path,
        default=REPO_ROOT / "data/gold/swe_llm_audit.summary.json",
    )
    p.add_argument(
        "--cache-root",
        type=Path,
        default=REPO_ROOT / "data/raw/llm-audit",
    )
    p.add_argument("--n", type=int, default=SAMPLE_N)
    p.add_argument("--seed", type=str, default=SAMPLE_SEED)
    p.add_argument("--max-usd", type=float, default=MAX_USD)
    p.add_argument("--concurrency", type=int, default=CONCURRENCY)
    p.add_argument("--estimate-only", action="store_true")
    p.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    p.add_argument(
        "--full",
        action="store_true",
        help="census of all 1,699; writes swe_llm_audit_full.* and reuses cache",
    )
    p.add_argument("--full-max-usd", type=float, default=FULL_MAX_USD)
    args = p.parse_args(argv)
    import os

    if args.full:
        default_out = REPO_ROOT / "data/gold/swe_llm_audit.jsonl"
        default_summary = REPO_ROOT / "data/gold/swe_llm_audit.summary.json"
        out_path = (
            REPO_ROOT / "data/gold/swe_llm_audit_full.jsonl"
            if args.out == default_out
            else args.out
        )
        summary_path = (
            REPO_ROOT / "data/gold/swe_llm_audit_full.summary.json"
            if args.summary == default_summary
            else args.summary
        )
        run_full(
            compact_path=args.compact,
            raters_path=args.raters,
            oof_path=args.oof,
            irt_path=args.irt,
            parquet_path=args.parquet,
            out_path=out_path,
            summary_path=summary_path,
            cache_root=args.cache_root,
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            max_usd=args.full_max_usd,
            concurrency=args.concurrency,
            n_bootstrap=args.n_bootstrap,
        )
        return 0

    run(
        compact_path=args.compact,
        raters_path=args.raters,
        oof_path=args.oof,
        irt_path=args.irt,
        parquet_path=args.parquet,
        sample_path=args.sample_out,
        out_path=args.out,
        summary_path=args.summary,
        cache_root=args.cache_root,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        n=args.n,
        seed=args.seed,
        max_usd=args.max_usd,
        concurrency=args.concurrency,
        estimate_only=args.estimate_only,
        n_bootstrap=args.n_bootstrap,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
