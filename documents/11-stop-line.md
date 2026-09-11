# Stop line

Human labeling of the 16 Harbor packets is **still deferred**. Cheap artifacts rank (OOF AUROC ~0.70) but do not clean the 2024 conservative tail to a certifiable residual. Next engineering step is the Harbor execution runner on lakehouse, not six humans.

See [13-next-directives.md](13-next-directives.md), [14-risk-coverage-and-labels.md](14-risk-coverage-and-labels.md), and [15-openai-reconstruction.md](15-openai-reconstruction.md). Decision gate: do not sample a population until the evidence layer can clean a tail.

## Ready for a human

| Item | Path |
| --- | --- |
| Protocol | [08-human-review-protocol.md](08-human-review-protocol.md) |
| Queue index | [../data/review_queue/README.md](../data/review_queue/README.md) |
| 16 Harbor packets | `data/review_queue/packets/` |
| Manifest | `data/review_queue/manifest.json` |
| Sealed 10-item SWE-bench calibration | `data/review_queue/calibration_sealed.json` (open after those reviews) |

## Already executed (no human needed)

- SWE-bench 1,699-row ingest
- Coverage simulations n=50 and n=100
- Sample-size table for UCB targets
- Unit tests for estimators, designs, ingest, dossiers

## Do not do next without a human

- Fill `valid` / `invalid` on packets
- Train a risk model on circular SWE-bench severities
- Announce a residual-error bound on any accepted benchmark
- Generate synthetic tasks

## First human slice (about two hours)

Review in this order, 8–10 minutes each:

1. `tasks/lakehouse-publish-recovery`
2. `experimental/logged-bandit-ope`
3. `experimental/gold-retry-publisher`
4. `tasks/durable-prefix-ack`
5. `tasks/week-hours` (easy control)
6. `experimental/bootstrap-merge-resume` (easy control)

Return the six filled packets. Then we score agreement, packet defects (missing logs), and whether Q4/Q5 are actually answerable in five minutes.
