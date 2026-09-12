# Z.ai Terminal-Bench 2.0 Verified changelog (eval-only)

Downloaded 2026-09-12. Never use these IDs as features (ADR-0011).

- Hugging Face: `zai-org/terminal-bench-2-verified`
- Files: `changes_instructions.md` (22229 bytes), `README.md` (15873 bytes)
- License: Apache-2.0 (`license: apache-2.0` on the dataset card). No LICENSE file on the dataset root.
- Join: TB task directory name.

Keep the named instruction/test fixes only:

- Original 11 instruction/test mismatches (README Part II / changes_instructions Category A/B/C)
- 2026-08-18 round: dna-insert, make-doom-for-mips, filter-js-from-html, install-windows-3.11 (tests); pytorch-model-cli, raman-fitting (instructions)
- Five synced from TB 2.1: mteb-leaderboard, query-optimize, torch-tensor-parallelism, polyglot-rust-c, caffe-cifar-10

Drop the 89 Dockerfile-only procps/python rows. Those are harness/env, not validity labels.
