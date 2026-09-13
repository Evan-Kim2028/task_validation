# Review packet: `mcmc-sampling-stan`

Fill the checklist. Do not repair the task in this packet. Mark valid, invalid, or ambiguous.

## Identity

- Benchmark: `terminal-bench` `2.1`
- Provenance: `PENDING_HUMAN`
- Domain: unspecified
- Difficulty / expert hours: unspecified
- Current label: `pending`

## Artifacts

- `task_path`: /home/evan/Documents/tb21-dataset/terminal-bench-2-1/mcmc-sampling-stan
- `failing_command`: harbor run -p /home/evan/Documents/tb21-dataset/terminal-bench-2-1/mcmc-sampling-stan --agent oracle --env docker --yes -n 1 --job-name mcmc-sampling-stan-oracle-20260912T152718 -o /tmp/tv-tb21census/jobs
- `verifier_output`: /tmp/tv-tb21census/jobs/mcmc-sampling-stan-oracle-20260912T152718/mcmc-sampling-stan__nqsmwbf/verifier/test-stdout.txt
- `verifier_output_tail`: test_outputs.py:147: AssertionError
==================================== PASSES ====================================
=========================== short test summary info ============================
PASSED test_outputs.py::test_posterior_alpha_estimation
PASSED test_outputs.py::test_posterior_beta_estimation
FAILED test_outputs.py::test_rstan_package_installed - AssertionError: RStan ...
FAILED test_outputs.py::test_hierarchical_model_implemented - AssertionError:...
FAILED test_outputs.py::test_r_script_created_and_used_rstan - AssertionError...
FAILED test_outputs.py::test_stan_model_sampling - AssertionError: R analysis...
========================= 4 failed, 2 passed in 0.24s ==========================
- `nop_job`: /tmp/tv-tb21census/jobs/mcmc-sampling-stan-nop-20260912T153313
- `environment_fingerprint`: harbor 0.22.0, --env docker; task dir /home/evan/Documents/tb21-dataset/terminal-bench-2-1/mcmc-sampling-stan; dataset terminal-bench/terminal-bench-2-1; job mcmc-sampling-stan-oracle-20260912T152718
- `machine_verdict`: invalid
- `label_protocol`: verifier_invalid.fresh_environment.execution

## Machine evidence (may be incomplete)

- oracle_pass: `False`
- nop_fail: `True`
- environment_builds: `True`
- evaluation_deterministic: `None`
- mutation_kill_rate: `None`
- exploit_probe_rejected: `None`

### Static

- `source_benchmark`: `mcmc`
- `oracle_reward`: `0.0`
- `oracle_accepted`: `False`
- `nop_reward`: `0.0`
- `nop_accepted`: `False`
- `oracle_status`: `executed`
- `nop_status`: `executed`
- `failing_tests`: `['test_outputs.py::test_rstan_package_installed', 'test_outputs.py::test_hierarchical_model_implemented', 'test_outputs.py::test_r_script_created_and_used_rstan', 'test_outputs.py::test_stan_model_sampling']`
- `last_error_line`: `E           assert False`
- `machine_evidence`: `reference fails own verifier`

## Checklist

### Q1. Oracle / reference

Did a clean-container oracle (or documented equivalent) pass, and is the log attached or cited?

- [ ] yes
- [ ] no
- [ ] cannot tell from this packet

Notes:


### Q2. Nop / mutation

Did a no-op fail, and would a plausible wrong patch fail at least one check?

- [ ] yes
- [ ] no
- [ ] cannot tell from this packet

Notes:


### Q3. Cheat / exploit

Did an adversarial or cheat trial end at reward 0, or is the gap explicitly recorded?

- [ ] yes
- [ ] no
- [ ] cannot tell from this packet

Notes:


### Q4. Instruction-test alignment

Can every hidden check be derived from the instruction, the environment, or docs the agent can read?

- [ ] yes
- [ ] no
- [ ] cannot tell from this packet

Notes:


### Q5. Single interpretation

Would two competent engineers agree on what 'done' means from the instruction alone?

- [ ] yes
- [ ] no
- [ ] cannot tell from this packet

Notes:


### Q6. Material invalidity

If evaluation can no longer be read as evidence about the intended capability, mark invalid.

- [ ] yes
- [ ] no
- [ ] cannot tell from this packet

Notes:


## Verdict

Primary outcome (exactly one):

- [ ] valid
- [ ] invalid
- [ ] ambiguous

If invalid, name the failure (impossible, spec/verifier disagreement, hidden unstated tests, wrong reference, nondeterminism, cheap game, leak):


Reviewer:

Minutes spent:

