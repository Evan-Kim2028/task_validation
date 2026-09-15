# Verifier-defect and anti-hack scan over the Harbor-Adapter extract

Question. Can the zero-dollar verifier-defect and anti-hack gates the
literature ranks highest (grounded fail-to-pass checks, shortcut flags) be
run retrospectively on the extract we already have — and would they have
predicted anything the funnel rejected?

Artifact: `data/gold/verifier_defect_scan.json` (full report),
`data/gold/verifier_defect_scan_tasks.jsonl` (per-task flags).
Code: `src/task_validation/evidence/verifier_defect_scan.py`;
tests `tests/test_verifier_defect_scan.py` (11 tests, all pass).
Protocol `verifier_defect_scan.2026-09-15`.

## RESULT

### 1. Reward-channel disagreement: a clean zero

Real schema, verified by streaming all rows (not the field list from the
tasking note). `harbor_adapter_traj.jsonl`: 793,698 rows, 8,468 tasks,
768,956 in-scope. The extract writes `reward = reward_txt_value` whenever
`verifier/reward.txt` parses and falls back to `result.json`
`verifier_result.rewards.reward` only when reward.txt is absent
(`_traj_row` in `ingest/harbor_adapter_traj.py`), so within-file
`reward_txt_value` vs `reward` disagreement is impossible by construction.

| Quantity | n |
| --- | --- |
| reward.txt present and parsed | 760,624 |
| reward.txt absent → reward from result.json | 33,074 |
| reward.txt unparseable (`parse_error`) | 0 |
| non-finite reward.txt (nan/inf) | 0 |
| trials with no reward at all | 0 |
| within-file `reward` ≠ `reward_txt_value` | 0 |

The computable form of the doc-64 defect is the two *written* channels
disagreeing. `harbor_funnel_rewards.jsonl` retains the full `result` dict,
so I joined it to the traj extract on `trial_id`:

| Join cell | n |
| --- | --- |
| funnel trials joined to traj | 108,163 |
| both channels present | 103,458 |
| **disagreeing (\|txt − json\| > 1e-9)** | **0** |
| json-only (reward.txt absent) | 4,705 |
| txt-only | 0 |
| distinct tasks affected | 0 |

Zero disagreements in 103,458 dual-channel trials over all 6,627 funnel
candidates. The two written channels never disagree, at any magnitude —
the magnitude distribution is empty. The defect doc 64 found by hand
(verifier stdout logging 0.966 while reward.txt held 0) lives one level
higher — *logged* score vs *written* reward — and the extract kept only
`test_stdout_bytes`, a length. That mode cannot be rescanned from this
extract at all; see Limits.

### 2. Anti-hack flags mark flailing, not success — pooled

A trial trips a flag when the assistant-text regex count is > 0
(`mentions_answer_file`, `git_history_probe`, `network_fetch`; definitions
in `ingest/harbor_adapter_traj.py`). Pooled over all 793,698 rows
(n_obs = 783,135; the rest have no parsed trajectory), Wilson 95%:

| flag | P(flag) | P(solved \| flag) | P(solved \| no flag) |
| --- | --- | --- | --- |
| mentions_answer_file | 0.0453 (0.0449, 0.0458) | 0.413 (0.408, 0.419), n=35,486 | 0.554 (0.553, 0.556), n=747,649 |
| git_history_probe | 0.0161 (0.0159, 0.0164) | 0.504 (0.495, 0.512), n=12,635 | 0.549 (0.548, 0.550), n=770,500 |
| network_fetch | 0.0667 (0.0662, 0.0673) | 0.484 (0.480, 0.488), n=52,272 | 0.553 (0.552, 0.554), n=730,863 |

Every flag is *anti*-associated with success at the pooled level:
tripping a hack flag predicts a 4–14-point *lower* solve rate. As a
population signal these flags identify hard tasks where agents search and
flail — the opposite of the do-nothing-pass hypothesis.

Per-task, though, elevation exists. Flag a task when the Wilson-95 lower
bound on P(flag|solved) strictly exceeds the Wilson-95 upper bound on
P(flag|unsolved) within the same task, requiring ≥3 flag-observed solved
trials:

| flag | tasks with elevated P(flag\|solved) | tasks where every observed solved trial tripped it |
| --- | --- | --- |
| mentions_answer_file | 175 | 205 |
| git_history_probe | 173 | 208 |
| network_fetch | 252 | 73 |

Concentration (`elevated_tasks`, `all_solved_trips_flag_tasks` in the
JSON): answer-file and git elevation sit in the SWE family
(featurebench-modal, swebench-verified, swebenchpro, swesmith, swtbench);
network elevation sits in fetch-by-design benchmarks (seal0,
replicationbench, deepsynth, simpleqa). Sharpest examples:

- `skillsbench/simpo-code-reproduction`: 17/17 solved trials tripped
  network_fetch vs 3/73 unsolved (Wilson LB 0.816 vs UB 0.114).
- `swesmith/oauthlib__oauthlib.1fd52536.combine_file__k77pp897`: 15/15
  solved tripped git_history_probe vs 5/102 unsolved.
- `swebench-multilingual/axum-682`: 106/109 solved tripped
  mentions_answer_file vs 3/9 unsolved.
- `seal0/54`: 25/25 solved tripped network_fetch vs 53/118 unsolved.

Caveat that matters for the second column: tasks where the flag fires on
nearly *all* trials dominate the "every solved trial flagged" list
(compilebench `curl-*` trips network_fetch on ~100% of trials, solved or
not — downloading source is the task). Only the Wilson-separated first
column is evidence the flag tracks *success specifically*. These are
eval-only candidate flags, not proven hacks: `git log`/`git show` is a
legitimate debugging move in SWE tasks, and curl/wget is required work in
fetch benchmarks. The flags are benchmark-structured (network_fetch:
deepsynth 0.610, seal0 0.516, medagentbench 0.452, simpleqa 0.403 —
per-benchmark table in `task2_antihack.per_benchmark`).

### 3. The free flags do not predict what the funnel rejected — NULL

Same model class, folds, and seeds as doc 54 (`eval_label`,
`_fit_logit_fast`, LOBO = leave-one-benchmark-out, LOFO =
leave-one-family-out, 400-replicate bootstrap, seed 20260913). Set A is
the doc-52 execution features and reproduces the prior numbers to the
digit (0.711 / 0.837). New sets: E = reward-channel defect features,
H = the six all/frontier flag rates, H_full adds solved-conditional
shares and lifts, V = per-cell stats from Task 4.

survived_2_to_4 (1,331 stage-1 survivors, 67 kept):

| set | LOBO AUROC (95% CI) | LOFO |
| --- | --- | --- |
| A | 0.711 (0.650, 0.771) | 0.698 |
| E | 0.334 (0.255, 0.411) | 0.354 |
| H | 0.466 (0.375, 0.543) | 0.461 |
| H_full | 0.469 (0.395, 0.548) | 0.498 |
| E+H | 0.423 (0.341, 0.496) | 0.428 |
| A+E+H | 0.618 (0.534, 0.694) | 0.571 |

survived_funnel (6,627 candidates, 81 kept):

| set | LOBO AUROC (95% CI) | LOFO |
| --- | --- | --- |
| A | 0.837 (0.793, 0.871) | 0.830 |
| E | 0.284 (0.211, 0.353) | 0.360 |
| H | 0.575 (0.483, 0.661) | 0.546 |
| H_full | 0.644 (0.564, 0.709) | 0.645 |
| E+H | 0.553 (0.463, 0.630) | 0.511 |
| A+E+H | 0.731 (0.658, 0.786) | 0.683 |

Read: adding the defect and anti-hack flags to execution features *lowers*
held-out AUROC on both labels (0.711→0.618 and 0.837→0.731). The null is
not ambiguous. Mechanism, visible in the univariate table: the only E
features that vary are `def_txt_absent_rate` / `def_json_fallback_rate`,
and reward.txt absence is a two-benchmark bit — research-code-bench and
bixbench never write it (33,074/33,074 absent trials are in those two).
Trained without the held-out benchmark, the logit learns
"absent→survives" from bixbench (5 of 29 stage-1 survivors kept) and then
mis-ranks research-code-bench's 81 stage-1 negatives — benchmark-identity
arbitrage, exactly the failure doc 54 diagnosed for the sparse verifier
features.

### 4. Across-cell variance does not separate kept from rejected

`harbor_funnel_rewards.jsonl` cross-tab (n=108,163 rows, all six cells ≈
18k each, ~16.3 trials/candidate):

| | claude-opus-4-6 | gpt-5.4 | gemini-3.1-pro |
| --- | --- | --- | --- |
| claude-code | 17,751 (.638) | — | — |
| terminus-2 | 17,610 (.629) | 18,209 (.520) | 18,037 (.654) |
| codex | — | 18,438 (.663) | — |
| gemini-cli | — | — | 18,118 (.674) |

(parenthetical = cell solve rate). The design is *not* fully crossed: 6
of 12 agent×model combinations exist. Model effects are separable only
inside terminus-2 — and there the contrast is real (gpt-5.4 under
terminus-2 solves 0.520 vs 0.663 under codex, a harness×model interaction,
not a pure model effect). 5,941 tasks have ≥2 populated cells; 5,844 have
the full terminus-2 model cross.

Univariate LOBO on survived_2_to_4: across-cell variance 0.474
(0.399, 0.549), spread 0.497 (0.415, 0.572), pooled rate 0.431
(0.351, 0.510), n_cells 0.506, terminus-model variance 0.408 — every one
inside or straddling chance. The V set scores 0.518 LOBO; A+V degrades A
to 0.594. On survived_funnel, `cell_pooled_rate` alone earns 0.771 —
mechanically, since stage 1 *is* a solve-rate cutoff — while cell
variance earns 0.510. Across-cell discrimination is a real number nobody
featurized before, and it carries no funnel-rejection signal.

### 5. Cost

Wall-clock and peak RSS per stage (`costs` in the JSON; ru_maxrss is a
running peak, reported at stage end):

| stage | wall sec | peak RSS at end (MB) |
| --- | --- | --- |
| stream funnel rewards (337 MB) | 2.3 | 74 |
| stream traj (757 MB, all tasks 1–2 aggregates) | 10.2 | 101 |
| task reports (Tasks 1–2, 4) | 0.2 | 141–156 |
| join + LOBO/LOFO evals (Tasks 3–4) | 142.6 | 247 |
| **total** | **155.3** | **247** |

155 seconds, 247 MB peak, zero API calls, zero trials, zero dollars. The
expensive line is the logistic eval grid (16 LOBO+LOFO fits × ~50 folds +
26 univariate fits × bootstrap), not the data scan — and it is still
cheaper than one frontier trial.

## Method

Single streaming pass per file, line-by-line `json.loads`; no file is
loaded whole. `scan_funnel_rewards` keeps `trial_id → result.json reward`
plus per-(task, cell) counts. `scan_traj` folds each row into global,
per-benchmark, and per-task accumulators (`acc_traj_row`), tracking the
reward-channel bookkeeping and the three flag four-cells
(flagged/unflagged × solved/unsolved) for all trials and the six frontier
cells separately. Intervals are Wilson-95 (`wilson`); per-task elevation
compares the Wilson lower bound on P(flag|solved) to the Wilson upper
bound on P(flag|unsolved) within the same task, min 3 flag-observed
solved trials (`MIN_SOLVED_FOR_ELEVATION`). Task 3/4 evals reuse
`harbor_funnel.eval_label` unchanged: median imputation, missingness
indicators, standardized design matrix, class-weighted L2 logit, grouped
OOF by benchmark (`lobo`) and by `benchmark_family` (`lofo`), pooled
contrast, bootstrap CIs. Labels are grade-A/B external and enter nothing
but the AUROC — eval-only per doc 43. All inputs opened read-only; the
raw parquet dump is gone, so nothing was re-extracted.

## Limits

- **The doc-64 defect mode is not rescan-able from this extract.** The
  logged-vs-written disagreement lived in verifier stdout; the extract
  retained `test_stdout_bytes`, not the text. The zero in Task 1 covers
  written-channel consistency (reward.txt vs result.json) on the 108,163
  fetched funnel trials only. It does not show the sldbench mode is rare;
  it shows the mode is invisible to these fields. To make the real gate
  runnable, the extractor must retain verifier stdout (or at least the
  score-bearing lines) — one-line change in `_WANTED`, full re-extract.
- **Join coverage.** The two-channel check exists only where the funnel
  file has the trial (the ~18 fetched frontier trials per candidate). The
  other ~685k in-scope traj rows have only the collapsed `reward`.
- **Flag validity.** The regexes fire on legitimate behavior (git log in
  SWE tasks, curl in fetch-by-design benchmarks). Elevation marks a task
  for review; it does not convict. The counts are assistant-text only —
  tool observations are never scanned, so a flag means the agent wrote or
  invoked it.
- **Repo infra defect found en route:** `_binom_sf` in
  `sampling/estimators.py` underflows `q**n` to 0.0 for n ≳ ~1.5e3 at
  small p, so `clopper_pearson_upper/lower` and
  `footprint.binomial_ci` silently return inverted/collapsed bounds on
  these cell sizes (verified: `binomial_ci(35486, 783135)` → lo 0.999,
  hi 0.001). This scan uses Wilson everywhere; any earlier artifact that
  put large-n binomial CIs through `binomial_ci` should be rechecked.
- **Fold-artifact caution.** Two E features (`def_disagree_rate`,
  `def_n_disagree`) are constant across all tasks — zero disagreements
  exist — and txt-absence is a two-benchmark bit. Sub-0.5 AUROCs on
  sparse/constant features are fold-base-rate artifacts more than signal
  (doc 54's warning applies); the A+E+H < A comparison is the load-bearing
  number, not E alone.
- **survived_funnel is partly mechanical** — stage 1 is itself a
  frontier solve-rate cutoff, so pooled-rate features earn "signal" on
  that label by construction. survived_2_to_4 is the honest label.
- **One published task unjoinable** (dacode ml-competition-017 was never
  sampled into the manifest): evals run on 81 of 82 published.
