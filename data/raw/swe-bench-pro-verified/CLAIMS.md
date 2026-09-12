# SWE-Bench Pro Verified (OpenCompass)

Eval-only. Never use these IDs as features. Never tune weights on them
(ADR-0011, ADR-0012).

- Hugging Face: `opencompass/SWEBench-Pro-Verified`
- Revision (git sha): `ae466f824cdee69d2c010b6c954b7418c411b6e4`
- Last modified on Hub: 2026-09-10T09:39:53Z
- License: Apache 2.0 (`license: apache-2.0` on the dataset card)
- Paper: arXiv 2609.08149
- Files: `README.md` (102 repaired IDs by category), `swebench_pro_verified.jsonl` (731 rows)
- ID field: `instance_id`, same ScaleAI form as `data/gold/swe_pro_features.jsonl` `task_id`
  (`instance_{org}__{repo}-{sha}[-v{...}]`). Mapping is exact string equality. No hashing.
- Categories in README Part II: misleading prompts (22), overly narrow tests (75),
  overly broad tests (3; heading typo "borad"), other issues (2).
