# task_validation

Statistical certification of agent-evaluation benchmark validity under a bounded human-review budget.

This repository is a sister of [`eval_tasks`](https://github.com/Evan-Kim2028/eval_tasks). `eval_tasks` builds Harbor / Terminal-Bench tasks. This repo asks a different question: given a population of tasks, how do you know the residual rate of *materially invalid* tasks is below a stated bound without reviewing every task?

Synthetic task generation is Part 2. This repo does not generate new tasks.

## What is locked

**Estimand.** A task is materially invalid when its evaluation can no longer be read as evidence about the intended capability.

**Method.** Independent execution-grounded signals score risk. Probability sampling estimates residual invalidity. Humans review a budgeted sample. The release claim is a one-sided 95% upper confidence bound, not a point percentage.

**Novelty boundary.** Automated auditors (ABA, BenchGuard), construction funnels (Harbor-Index, Terminal-Bench), and generators (SWE-Universe, SWE-smith) already exist. They do not report a design-based confidence bound on population invalidity. That is the gap. Harbor-Index is the closest operational system. It still audited every survivor.

## Current stop line

Human labeling of the 16 Harbor packets is deferred until those packets include the cheap evidence vector. Do not fill verdicts with a model. See [`documents/11-stop-line.md`](documents/11-stop-line.md).

## Quick start

```sh
uv venv .venv --python python3
uv pip install --python .venv/bin/python -e '.[dev,fit]'
PYTHONPATH=src .venv/bin/python -m pytest tests
PYTHONPATH=src python3 -m task_validation.cli ingest-swe \
  --csv data/raw/swe-bench-verified/ensembled_annotations_public.csv \
  --out data/gold/swe_verified.jsonl
PYTHONPATH=src python3 -m task_validation.cli simulate-coverage \
  --gold data/gold/swe_verified_compact.jsonl \
  --out data/gold/coverage_n100_r200.json --n 100 --replicates 200
```

Re-download the OpenAI 2024 annotations if the CSV is missing:

```sh
curl -fsSL -o /tmp/swe-ann.zip \
  https://cdn.openai.com/introducing-swe-bench-verified/swe-bench-annotation-results.zip
unzip -o /tmp/swe-ann.zip -d data/raw/swe-bench-verified
```

## Empirical bridge (2026-09-11)

Cheap SWE-bench artifact features, **not** the human severity axes, predict the 2024 `filter_out` label at **logistic AUROC 0.76** on held-out repositories (150 tasks). That is the first non-circular H1 number. It is a ranker, not a certificate. Reproduce:

```sh
PYTHONPATH=src .venv/bin/python -m task_validation.cli join-swe \
  --gold data/gold/swe_verified_compact.jsonl \
  --parquet data/raw/swe-bench/test.parquet \
  --out data/gold/swe_verified_features.jsonl
PYTHONPATH=src .venv/bin/python -m task_validation.cli fit-risk \
  --features data/gold/swe_verified_features.jsonl \
  --out data/gold/risk_model_by_repo.json
```

Download the parquet first from Hugging Face `princeton-nlp/SWE-bench` `data/test-00000-of-00001.parquet`. Harbor oracle/nop/cheat from local `eval_tasks/jobs` are attached in `data/gold/eval_tasks_with_evidence.jsonl` (lakehouse: oracle pass, nop fail, cheat rejected, 3 file mutants).

Human review of the 16 packets stays deferred until packets carry this evidence vector.

**Causal consistency:** nine-invariant expansion paused. Static change-causality and provenance **fail** as rankers of 2024 labels (AUROC 0.41 / 0.42 on n=150). Drop those constructions. [`documents/18-causal-consistency.md`](documents/18-causal-consistency.md).

**Decision tree:** gates 1–5. 20-task SWE IDs frozen, Docker not scaled. B1: one rater vs majority agree 0.85, FNR 0.16. Coverage lab: stratified-normal is not the release rule. [`documents/22-decision-tree.md`](documents/22-decision-tree.md).

Grouped 5-fold OOF (honest number) is **AUROC 0.70** (0.67–0.73) on the 2024 conservative label. The accepted tail is the product metric, and it is not yet clean:

| Y | Base invalid | Residual in lowest-risk 5% | Residual in lowest-risk 20% |
| --- | ---: | ---: | ---: |
| conservative (≥1 rater) | 0.68 | 0.34 | 0.43 |
| majority (≥2/3) | 0.45 | 0.15 | 0.22 |
| unanimous (3/3) | 0.23 | 0.06 | 0.09 |

Fleiss κ on the per-rater material bit is **0.39**. Cheap artifacts cannot put a 20% UCB on the conservative tail; execution evidence is required. Details: [`documents/14-risk-coverage-and-labels.md`](documents/14-risk-coverage-and-labels.md). Sequence freeze: [`documents/13-next-directives.md`](documents/13-next-directives.md).

Hello-world cheap runner: oracle 1.0 twice, nop 0.0, wrong-output mutant killed, ~32s/trial.

## What already ran

On the 1,699 SWE-bench Verified ensemble labels (2024 conservative protocol):

| Design | n | Replicates | True invalid rate | Mean UCB | Nominal 95% coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Simple random | 100 | 2000 | 0.683 | 0.756 | 0.958 |
| Stratified by repo | 100 | 2000 | 0.683 | 0.757 | 0.955 |
| Hybrid (UCB from SRS arm) | 100 | 2000 | 0.683 | 0.778 | 0.964 |
| SRS on ~2% invalid population | 100 | 2000 | 0.02 | 0.058 | 1.00 |
| Stratified on ~2% invalid | 100 | 2000 | 0.02 | 0.040 | **0.90** |

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

Start at [`documents/23-handoff.md`](documents/23-handoff.md) (operating story) and [`documents/42-progress-v0.1.md`](documents/42-progress-v0.1.md) (release record). Index: [`documents/README.md`](documents/README.md).

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
