# Literature search log

Date: 2026-09-11.

Method: web search + arXiv/HTML fetches + OpenAI blog fetch. Not a PRISMA review. Goal was to verify the locked-thesis citation list and find anything that already does population-level *task-validity* CIs.

## Verified IDs

| Claimed | Result |
| --- | --- |
| ABA 2605.26079 | exists |
| BenchGuard 2604.24955 | exists |
| Harbor-Index site + 2609.04298 | exists, 82 tasks |
| SWE-Universe 2602.02361 | exists |
| InfoSynth 2601.00575 | exists |
| Code2Bench 2508.07180 | exists |
| SWE-Mutation ACL 2026 / 2605.22175 | exists (ID in plan was anthology URL; arXiv is 2605.22175) |
| RHB 2605.02964 | exists |
| FAQ 2601.20251 | exists |
| Noisy but Valid 2601.20913 | exists |
| PRECISE 2606.05308 | exists |
| Berti-Équille 2607.25356 | exists |
| ProgramBench 2605.03546 + programbench.com | exists |
| SWE-smith 2504.21798 | exists |
| Endless Terminals 2601.16443 | exists |
| CLI-Universe 2606.22883 | exists |
| SWE-rebench 2505.20411 | exists |
| R2E-Gym 2504.07164 | exists |
| EvalPlus 2305.01210 | exists |
| SWE-bench+ 2410.06992 | exists |
| TB 2.0 paper 2601.11868 | exists |
| OpenAI Verified 2024 / 2026 drop / Pro 2026 posts | exist, numbers match with scope caveats |

## Unverified

Task Verification Bench, OpenReview `QdDcI0Ftvo`. Cloudflare. No arXiv/HF/GitHub under that name.

## Nearby papers not in the original list

- SPICE 2507.09108 (auto-label SWE issue clarity)
- BenchJack 2605.12673 (reward hacks)
- Measuring what Matters 2511.04703 (construct validity of 445 LLM benches, paper-level)
- SWE-Bench Pro Verified (OpenCompass, arXiv 2609.08149)
- Cer-Eval 2505.03814 (certifiable eval of *models*)
- Defective Task Descriptions 2604.24703 (SpecValidator)

None of these is a design-based CI on agent-task invalidity.

## Gold downloads

SWE-bench annotations: https://cdn.openai.com/introducing-swe-bench-verified/swe-bench-annotation-results.zip (fetched, parsed, 1,699 unique).
