# Risk model

The gold table becomes supervised learning after evidence exists.

## Input / output

X is the evidence vector. r = P(Y=1 | X) where Y is material invalidity.

Start with logistic regression and gradient-boosted trees. This is not a prediction bake-off. We need calibration, coefficient signs we can explain, and cross-benchmark holdout.

## What we evaluate

- Discrimination: AUROC / AUPRC
- Calibration: a 5% score is about 5% invalid
- Operating point: P(Y=1 | accepted) after the machine filter
- Cross-source: train on SWE-bench, test on Terminal-Bench (once TB labels exist). Train on one lineage, test on another.

## What ML is not allowed to do

ML allocates expensive human attention. It does not certify the population.

If the model says tasks 913, 1427, and 8921 look suspicious, that is a queue. The bound still comes from units with known inclusion probabilities.

## Status in this checkout

First model is trained on frozen cheap artifact features. Severity axes are excluded by `assert_no_leakage`. Held-out-repo logistic AUROC is 0.76. Invalid-among-accepted is still high on this 68% invalid population. Docker mutation kill-rate is not yet in X. See [12-empirical-bridge.md](12-empirical-bridge.md).
