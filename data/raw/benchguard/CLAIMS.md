# BenchGuard gold (eval-only)

Downloaded 2026-09-12. Never use these IDs as features (ADR-0011).

- GitHub: `XinmingTu/BenchGuard` (`eval/data/gold/`)
- License: Apache-2.0 (`LICENSE` in this directory; also the repo LICENSE)
- Paper: arXiv 2604.24955

| File | Bytes | Date on source | n |
| --- | ---: | --- | ---: |
| `sab_gold.json` | 17746 | 2026-03-10 | 12 SAB tasks / 12 issues |
| `bixbench_gold.json` | 24479 | 2026-03-07 | 17 tasks / 24 expert issues |
| `LICENSE` | 10561 | Apache-2.0 | |

Join: SAB integer task keys (`9`, `12`, ...); Bix `bix-<n>-q<m>`. Author-confirmed on SAB (`human_verified` in file is False: machine-structured from notes). Bix is expert atomic issues. Eval-only. Off the coding-agent SWE/TB join except as a small high-trust scientific-agent set.
