# Selection replay: does a selection rule beat random at the same k

Code: `src/task_validation/evidence/selection_replay.py`. Artifact: `data/gold/selection_replay_tb4.json`. Input: `/home/evan/Documents/eval_tasks/analysis/tb4/raw/*.trials.json`, 4,290 scored trial rows = 13 submissions x 66 TB4 tasks x 5 trials. Rewards are binary with 9 nulls (scored as failure, matching doc 63). No new rollouts, no API calls; everything below is computed from rows already on disk.

## Result

**No selection rule demonstrably beats random selection of the same size on TB4 — but every adaptive rule's point estimate is above random, and the experiment is underpowered to confirm an advantage smaller than about 0.18 tau.** The honest reading is "positive trend, unresolved", not "null" and not "proven".

The full-set ranking of the 13 submissions by mean reward over all 66 tasks (`data/gold/selection_replay_tb4.json`, `selection.full_ranking`):

| Rank | Submission (model / harness) | Mean reward |
| ---: | --- | ---: |
| 1 | claude-fable-5-1 / claude-code | 0.579 |
| 2 | claude-opus-5 / claude-code | 0.524 |
| 3 | claude-fable-5 / claude-code | 0.445 |
| 4 | glm-5.3 / claude-code | 0.418 |
| 5 | gpt-5.6-sol / codex | 0.373 |
| 6 | claude-opus-4-8 / claude-code | 0.236 |
| 7 | gpt-5.6-terra / codex | 0.215 |
| 8 | grok-4.6 / grok-build | 0.203 |
| 9 | gemini-3.8-flash / mini-swe-agent | 0.191 |
| 10 | gpt-5.6-luna / codex | 0.173 |
| 11.5 | claude-sonnet-5 / claude-code | 0.124 |
| 11.5 | grok-4.5 / grok-build | 0.124 |
| 13 | gemini-3.7-flash / mini-swe-agent | 0.112 |

Random selection of k tasks already recovers this ranking at Kendall tau 0.74 (k=8) rising to 0.89 (k=32). An in-sample greedy oracle — the ceiling any rule could reach on this matrix — tops out at tau 0.987 (k=8) and 0.994 (k>=16), so the maximum attainable improvement over random at k=8 is +0.25 tau; the best observed rule reaches +0.13.

Kendall tau of the k-subset ranking against the full-66 ranking. For sampling rules: mean over 400 seeds with the seed 95% interval, then the paired trial-bootstrap interval on tau_rule minus E[tau_random]. For deterministic rules (irt_2pl, pbis): point estimate, then the same paired bootstrap. All numbers from `selection.rules` in the artifact.

| Rule | k=8 | k=16 | k=24 | k=32 |
| --- | --- | --- | --- | --- |
| random | 0.739 (0.52, 0.90) | 0.817 (0.65, 0.94) | 0.862 (0.71, 0.96) | 0.892 (0.78, 0.98) |
| band [0.10, 0.70] (50 tasks) | 0.763 (0.54, 0.91) | 0.839 (0.72, 0.94) | 0.889 (0.78, 0.97) | 0.914 (0.83, 0.99) |
| band [0.25, 0.75] (30 tasks) | 0.785 (0.61, 0.92) | 0.870 (0.77, 0.96) | 0.918 (0.86, 0.97) | 0.935* (30 items) |
| band [0.30, 0.70] (24 tasks) | 0.776 (0.63, 0.90) | 0.853 (0.77, 0.93) | 0.857* (24 items) | 0.857* (24 items) |
| irt_2pl | 0.805 | 0.895 | 0.935 | 0.935 |
| pbis | 0.850 | 0.831 | 0.876 | 0.942 |
| oracle (greedy, in-sample) | 0.987 | 0.994 | 0.994 | 0.994 |

\* band exhausted: the band holds fewer items than k, so the selection is the whole band.

Paired bootstrap on the advantage over random at the same k (`delta_vs_random_boot`; 300 cell-level trial resamples, rule refit each rep):

| Rule | k=8 | k=16 | k=24 | k=32 |
| --- | --- | --- | --- | --- |
| band [0.10, 0.70] | +0.042 (-0.03, +0.13) | +0.031 (-0.02, +0.09) | +0.026 (-0.02, +0.07) | +0.028 (-0.01, +0.07) |
| band [0.25, 0.75] | +0.061 (-0.01, +0.15) | +0.051 (-0.01, +0.11) | +0.048 (-0.01, +0.10) | +0.043 (-0.05, +0.12) |
| band [0.30, 0.70] | +0.054 (-0.03, +0.14) | +0.038 (-0.04, +0.11) | +0.029 (-0.06, +0.12) | -0.003 (-0.11, +0.08) |
| irt_2pl | +0.095 (-0.03, +0.22) | +0.077 (-0.03, +0.17) | +0.063 (-0.02, +0.14) | +0.043 (-0.04, +0.11) |
| pbis | +0.128 (-0.02, +0.26) | +0.063 (-0.04, +0.17) | +0.052 (-0.05, +0.14) | +0.046 (-0.03, +0.11) |

Every interval contains zero. The fraction of bootstrap reps with a positive delta reaches 0.95 (band [0.25, 0.75] at k=8 and k=24; irt_2pl at k=24) but no cell clears a two-sided 95% interval. 15 of the 16 rule x k cells have a positive mean delta; the only negative is the degenerate [0.30, 0.70] band at k=32, which cannot draw 32 items from a 24-task band. The sign consistency across rules and k is what a real but small effect looks like at this sample size.

Spearman rho and mean rank distance agree with tau on the ordering of rules and are in the artifact; nothing below changes if they are substituted.

## Power

The binding constraint is the 13-submission panel, not trial count. A parametric bootstrap that varies the number of trials per cell (`selection.power_trials_per_cell`, k=16, pbis vs random-mean) gives the standard error of the paired delta:

| Trials per cell | SE(delta) | Mean delta |
| ---: | ---: | ---: |
| 1 | 0.074 | +0.099 |
| 2 | 0.064 | +0.081 |
| 5 (actual) | 0.063 | +0.061 |
| 20 | 0.051 | +0.044 |
| 50 | 0.043 | +0.032 |

Two things follow. First, at the actual design (5 trials/cell) the minimum detectable advantage at 80% power and two-sided alpha 0.05 is roughly 2.8 x 0.063 = 0.18 tau; the largest observed delta is 0.13. The experiment cannot certify the effect it appears to show. Second, SE(delta) has a floor near 0.04 that more trials per cell cannot cross — decomposing SE(m)^2 into a 1/m term plus a constant gives an asymptote of about 0.037, and even that understates the problem because the "full" ranking itself is estimated from the same 13 submissions. With 13 submissions there are 78 pairs and tau moves in quanta of ~0.026. Detecting a +0.05 advantage needs SE(delta) near 0.018, which on this scaling requires a submission panel roughly 2-4x larger (about 25-50 submissions), not more attempts per cell. What would move the answer is more ranked entities, not more repetitions.

## Method: rank recovery

Each of the 66 tasks x 13 submissions cell holds 5 scored trials; the cell score is the trial mean. The full ranking orders submissions by mean over all 66 tasks. A rule picks k of the 66 tasks; the subset ranking orders submissions by mean over those k; the score is tau / rho / mean absolute rank distance vs the full ranking. Rules:

- `random`: uniform k of 66.
- `band [lo, hi]`: pooled per-task solve rate (all 65 trials) inside the band, then uniform k of the band. Band sizes: 50, 30, and 24 tasks respectively.
- `irt_2pl`: joint-MLE 2PL (`irt.py` `fit_2pl`) on the 66x13 matrix of fractional cell scores — a fractional y is a valid binomial-proportion likelihood term — with Fisher information at the mean ability (theta = 0 after standardization) as the item score, I_i = a_i^2 p_i(0)(1 - p_i(0)). Items whose discrimination pins at the A_MIN floor or whose rest-score point-biserial is non-positive are dropped before the top-k.
- `pbis`: top-k by rest-score point-biserial (`irt.py` `item_point_biserial`), non-positive items dropped.
- `oracle`: greedy forward selection maximizing tau against the full ranking. In-sample by construction; it is a ceiling, not a candidate rule.

Uncertainty: sampling rules get 400 seeds for the observed-data distribution and 16 seeds inside each bootstrap rep; the trial bootstrap resamples each cell's 5 trials with replacement, refits every rule (bands recomputed, 2PL refit at max_iter 40), and rescored tau — 300 reps. The paired delta subtracts the same rep's E_seed[tau_random].

## Method: model/harness confound

`agent_name` and `model_name` are separate fields. The cross-tab (`confound` in the artifact):

- 4 harnesses (claude-code, codex, grok-build, mini-swe-agent) x 13 models = 52 possible cells; 13 populated; **zero models appear under more than one harness**. The design is fully block-diagonal, not crossed.
- Therefore `reward ~ model + harness` is not identifiable across blocks: every between-harness difference is aliased with the particular models that ran under that harness. The identifiable decomposition is nested — across the 13 submission means, 42.2% of the variance is between-harness (the confounded chunk) and 57.8% is within-harness across models (the pure model axis). The per-task median between-harness share is 38.1% (`confound.variance_overall_submission_means`, `confound.variance_per_task_share_between_median`).
- Harness-fixed durability slopes exist but live on shorter capability spans: within claude-code's 6 models (2/2/2 tiers) the median per-task slope is 0.40; within codex's 3 models (1/1/1) it is 0.10; grok-build and mini-swe-agent have only 2 models each and no top/bottom third. The naive 13-submission slope (doc 63, 5/4/4) has median 0.33. These are not directly comparable — the naive slope mixes harness gaps into the capability axis, which is exactly the confound stated in Part 2 — but they show the model axis alone still produces steep per-task curves inside one harness.
- Fix: a crossed design needs the same models under multiple harnesses. `terminalbench-trajectories` on HuggingFace (211 MB, apache-2.0, advertised 26 scaffolds x 49 models) would resolve the design **if** its scaffold x model cells are populated off the diagonal — a crossed subset of that matrix would bridge harness effects across shared models. Whether it is populated that way cannot be checked from disk; no download was performed for this document.

## Method: cost accounting

Per-trial `cost_usd` over the 4,290-row grid (`costs` in the artifact; 24 rows carry no cost and are excluded from the means):

- Overall: mean $11.72, median $4.48 per trial; total grid cost $50,007.
- By harness: claude-code $19.40 mean ($12.61 median), grok-build $8.88 ($2.35), codex $4.74 ($2.00), mini-swe-agent $1.91 ($0.14).
- Price of a difficulty gate at k=3 trials per task over 1,000 new tasks, per submission (`cost_k3_x_1000_tasks`): claude-sonnet-5 $87,573 (most expensive), claude-fable-5 $66,046, claude-opus-4-8 $58,921, claude-fable-5-1 $56,759, claude-opus-5 $55,091, grok-4.6 $32,950, glm-5.3 $24,872, gpt-5.6-sol $23,619, grok-4.5 $20,071, gpt-5.6-terra $15,807, gemini-3.7-flash $11,472, gpt-5.6-luna $3,161, gemini-3.8-flash $0.
- The cheapest model present is gemini-3.8-flash at a recorded $0.00 on all 330 trials — a metering artifact or free-tier pricing, either way not a real price; the cheapest non-zero model is gpt-5.6-luna at $1.05 mean ($0.42 median) per trial, which prices a 3x1000 gate at $3,161.

## Limits

- The selection question is answered on one snapshot: 13 submissions, 66 tasks, 5 trials per cell. All rank-recovery numbers are properties of this grid, not of selection rules in general. The oracle ceiling is in-sample and optimistic by construction.
- The paired bootstrap resamples trials within cells; it cannot create information the 13-submission panel does not contain. The near-identical SE(delta) floor across m says the noise that matters is which submissions got ranked, not how often each was run.
- Delta intervals are per-cell; no multiplicity correction across the 20 rule x k cells is applied, which makes the "all intervals contain zero" statement conservative in one direction and the sign-consistency observation weaker in the other.
- The 2PL is fit on fractional cell scores (5-trial means), a pseudo-likelihood use of the binary likelihood; item parameters are used only for ranking items, not interpreted as population parameters.
- Difficulty bands are computed on the same submissions the ranking is scored on — legitimate here because the rules are evaluated as instruments on this matrix, but a deployed gate would set bands from a pilot panel and could do worse.
- The confound decomposition is nested, not crossed: the 42% between-harness share is descriptive of this dump and cannot be attributed to harness quality versus model assignment. Nothing in the tb4 grid separates them.
- Cost figures are as recorded in the trial rows; the $0.00 gemini-3.8-flash trials and 24 missing costs are reported, not corrected. Token-price changes since the run date are not modeled.
