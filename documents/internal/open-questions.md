# Open questions

Status: open / blocked / answered.

## Q-TVB. Can Task Verification Bench be opened?  — blocked

OpenReview `QdDcI0Ftvo` did not yield a PDF or dataset. If it appears, ingest as a separate provenance. Do not assume the 129+129 SWE-bench counts from the chat plan.

## Q-138. Can we get the 138-task 2026 Verified audit IDs?  — open

Without instance IDs, we cannot treat that audit as a biased-but-known subset of the 500.

## Q-jobs. Should packets attach local Harbor rewards?  — open

Yes for the reviewer, no for the public tree until we have a redacted CTRF extract. Implement as an optional `--jobs-root` later.

## Q-stratified. Is the normal+FPC UCB calibrated at small n_h?  — open

200-rep coverage was 94.5% at n=100. Re-run 2,000. If it undershoots, switch the published stratified bound to a bootstrap or Satterthwaite interval.

## Q-IAA. Can one generalist match an expert on these 16 Harbor packets?  — open

That is Q12 from eval_tasks. The first six-packet slice is the pilot.

## Q-epsilon. 5% or 2% for eval_tasks accepted set?  — open

Sample size: 59 vs 149 with zero events. Decide after the pilot, not before.

## Q-mutation. First Harbor family for Q2a?  — open

Candidates: lakehouse (seven named defects) and logged-bandit-ope (generator). eval_tasks Q10 wanted TB4 first for calibration.

## Q-github. Public remote  — open

Local repo only until `gh repo create` (or an org) is pointed at this tree.
