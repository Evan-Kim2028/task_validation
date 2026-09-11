# task_validation

Statistical certification of agent-evaluation benchmark validity under a bounded human-review budget.

This repository is a sister of [`eval_tasks`](https://github.com/Evan-Kim2028/eval_tasks). `eval_tasks` builds Harbor / Terminal-Bench tasks. This repo asks a different question: given a population of tasks, how do you know the residual rate of *materially invalid* tasks is below a stated bound without reviewing every task?

Synthetic task generation is Part 2. This repo does not generate new tasks.

## What is locked

**Estimand.** A task is materially invalid when its evaluation can no longer be read as evidence about the intended capability.

**Method.** Independent execution-grounded signals score risk. Probability sampling estimates residual invalidity. Humans review a budgeted sample. The release claim is a one-sided 95% upper confidence bound, not a point percentage.

**Novelty boundary.** Automated auditors (ABA, BenchGuard), construction funnels (Harbor-Index, Terminal-Bench), and generators (SWE-Universe, SWE-smith) already exist. They do not report a design-based confidence bound on population invalidity. That is the gap. Harbor-Index is the closest operational system. It still audited every survivor.

## Current stop line

The pipeline stops at human review. Sixteen Harbor tasks from `eval_tasks` have packets in [`data/review_queue/packets/`](data/review_queue/packets/). Verdicts are blank. Do not fill them with a model.

How to review: [`documents/08-human-review-protocol.md`](documents/08-human-review-protocol.md) and [`data/review_queue/README.md`](data/review_queue/README.md).

## Quick start

```sh
python3 -m pytest tests
PYTHONPATH=src python3 -m task_validation.cli ingest-swe \
  --csv data/raw/swe-bench-verified/ensembled_annotations_public.csv \
  --out data/gold/swe_verified.jsonl
PYTHONPATH=src python3 -m task_validation.cli simulate-coverage \
  --gold data/gold/swe_verified_compact.jsonl \
  --out data/gold/coverage_n100.json --n 100 --replicates 200
```

Re-download the OpenAI 2024 annotations if the CSV is missing:

```sh
curl -fsSL -o /tmp/swe-ann.zip \
  https://cdn.openai.com/introducing-swe-bench-verified/swe-bench-annotation-results.zip
unzip -o /tmp/swe-ann.zip -d data/raw/swe-bench-verified
```

## What already ran

On the 1,699 SWE-bench Verified ensemble labels (2024 conservative protocol):

| Design | n | Replicates | True invalid rate | Mean UCB | Nominal 95% coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Simple random | 100 | 200 | 0.683 | 0.758 | 0.97 |
| Stratified by repo | 100 | 200 | 0.683 | 0.754 | 0.945 |
| Hybrid (UCB from SRS arm) | 100 | 200 | 0.683 | 0.781 | 0.985 |

That population is *mostly invalid* under the 2024 filter. The simulation checks whether the bound covers. It is not a certificate of SWE-bench Verified residual error. OpenAI's 2026 59.4% figure is 138 hard unsolved tasks, not a probability sample of the 500.

Sample size if a later accepted population shows **zero** invalids in the audit (Clopper-Pearson, one-sided 95%):

| Target UCB | n required with 0 invalids |
| --- | ---: |
| < 5% | 59 |
| < 3% | 99 |
| < 2% | 149 |
| < 1% | 299 |

Going from 1,000 to 100,000 tasks does not multiply this n. New strata and distribution shift do.

## Documents

Start at [`documents/README.md`](documents/README.md).

## Layout

```
documents/     thesis, prior art, plan, ADRs, internal notes
src/           ingest, sampling, review packets
data/gold/     EvalQA-Gold rows and simulation output
data/review_queue/  human packets (unlabeled)
tests/
```

## License

MIT. SWE-bench annotations remain under their upstream terms. We store a derived compact table and a pointer to [OpenAI's zip](https://cdn.openai.com/introducing-swe-bench-verified/swe-bench-annotation-results.zip).
