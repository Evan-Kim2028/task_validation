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

No trained model. SWE-bench gold has labels and almost no execution features. Using the 2024 severity axes as X to predict `filter_out` would be circular (`filter_out` is defined from those axes). Coverage simulations that need a *risk* score used FAIL_TO_PASS severity only as a **weak proxy** for H2 discovery, and the UCB was still computed from the SRS arm. That proxy is not a production model.
