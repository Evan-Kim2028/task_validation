"""Build the human-review queue. Stop here. Do not invent labels."""

from __future__ import annotations

import json
from pathlib import Path

from task_validation.review.dossier import write_packet
from task_validation.schema import GoldRow
from task_validation.sampling.designs import SampleDraw


def load_jsonl(path: Path) -> list[GoldRow]:
    from task_validation.schema import EvidenceVector

    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            ev = d.pop("evidence", {}) or {}
            d["evidence"] = EvidenceVector(**{k: v for k, v in ev.items() if k in EvidenceVector.__dataclass_fields__})
            # extra keys in evidence.extra
            extra = {k: v for k, v in ev.items() if k not in EvidenceVector.__dataclass_fields__}
            if extra:
                d["evidence"].extra.update(extra.get("extra", extra))
            rows.append(GoldRow(**d))
    return rows


def write_manifest(rows: list[GoldRow], draw: SampleDraw | None, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    packets = []
    for row in rows:
        packet = write_packet(row, out_dir / "packets")
        packets.append(
            {
                "task_id": row.task_id,
                "packet": str(packet.relative_to(out_dir)),
                "label": row.human_validity_label,
                "provenance": row.provenance,
            }
        )
    manifest = {
        "n_packets": len(packets),
        "status": "awaiting_human_review",
        "rule": "Do not fill verdicts automatically. Humans own Q4-Q6 and the binary label.",
        "design": None if draw is None else {"name": draw.design, "n": draw.n, "seed": draw.seed},
        "packets": packets,
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path
