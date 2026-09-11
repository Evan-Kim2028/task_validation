"""Human-review dossier. The reviewer reads evidence. They do not re-run Harbor."""

from __future__ import annotations

from pathlib import Path

from task_validation.schema import GoldRow

CHECKLIST = [
    (
        "Q1",
        "Oracle / reference",
        "Did a clean-container oracle (or documented equivalent) pass, and is the log attached or cited?",
    ),
    (
        "Q2",
        "Nop / mutation",
        "Did a no-op fail, and would a plausible wrong patch fail at least one check?",
    ),
    (
        "Q3",
        "Cheat / exploit",
        "Did an adversarial or cheat trial end at reward 0, or is the gap explicitly recorded?",
    ),
    (
        "Q4",
        "Instruction-test alignment",
        "Can every hidden check be derived from the instruction, the environment, or docs the agent can read?",
    ),
    (
        "Q5",
        "Single interpretation",
        "Would two competent engineers agree on what 'done' means from the instruction alone?",
    ),
    (
        "Q6",
        "Material invalidity",
        "If evaluation can no longer be read as evidence about the intended capability, mark invalid.",
    ),
]


def render_dossier(row: GoldRow) -> str:
    ev = row.evidence
    static = ev.static_checks or {}
    lines = [
        f"# Review packet: `{row.task_id}`",
        "",
        "Fill the checklist. Do not repair the task in this packet. Mark valid, invalid, or ambiguous.",
        "",
        "## Identity",
        "",
        f"- Benchmark: `{row.benchmark}` `{row.benchmark_version}`",
        f"- Provenance: `{row.provenance}`",
        f"- Domain: {row.domain or 'unspecified'}",
        f"- Difficulty / expert hours: {row.difficulty or 'unspecified'}",
        f"- Current label: `{row.human_validity_label}`",
        "",
        "## Artifacts",
        "",
    ]
    for k, v in (row.artifacts or {}).items():
        if k == "instruction_preview":
            continue
        lines.append(f"- `{k}`: {v}")
    preview = (row.artifacts or {}).get("instruction_preview")
    if preview:
        lines.extend(
            [
                "",
                "## Instruction preview",
                "",
                "```",
                str(preview).rstrip(),
                "```",
                "",
                "Full instruction lives in the sister repo. Do not paste the solution into this packet.",
            ]
        )
    lines.extend(
        [
            "",
            "## Machine evidence (may be incomplete)",
            "",
            f"- oracle_pass: `{ev.oracle_pass}`",
            f"- nop_fail: `{ev.nop_fail}`",
            f"- environment_builds: `{ev.environment_builds}`",
            f"- evaluation_deterministic: `{ev.evaluation_deterministic}`",
            f"- mutation_kill_rate: `{ev.mutation_kill_rate}`",
            f"- exploit_probe_rejected: `{ev.exploit_probe_rejected}`",
            "",
            "### Static",
            "",
        ]
    )
    for k, v in static.items():
        lines.append(f"- `{k}`: `{v}`")
    lines.extend(["", "## Checklist", ""])
    for code, title, prompt in CHECKLIST:
        lines.extend(
            [
                f"### {code}. {title}",
                "",
                prompt,
                "",
                "- [ ] yes",
                "- [ ] no",
                "- [ ] cannot tell from this packet",
                "",
                "Notes:",
                "",
                "",
            ]
        )
    lines.extend(
        [
            "## Verdict",
            "",
            "Primary outcome (exactly one):",
            "",
            "- [ ] valid",
            "- [ ] invalid",
            "- [ ] ambiguous",
            "",
            "If invalid, name the failure (impossible, spec/verifier disagreement, hidden unstated tests, wrong reference, nondeterminism, cheap game, leak):",
            "",
            "",
            "Reviewer:",
            "",
            "Minutes spent:",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def write_packet(row: GoldRow, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = row.task_id.replace("/", "__")
    path = out_dir / f"{safe}.md"
    path.write_text(render_dossier(row), encoding="utf-8")
    return path
