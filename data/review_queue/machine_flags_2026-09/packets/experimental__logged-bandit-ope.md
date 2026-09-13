# Review packet: `experimental/logged-bandit-ope`

Fill the checklist. Do not repair the task in this packet. Mark valid, invalid, or ambiguous.

## Identity

- Benchmark: `eval_tasks` `local`
- Provenance: `PENDING_HUMAN`
- Domain: Evaluation
- Difficulty / expert hours: unspecified
- Current label: `pending`

## Artifacts

- `task_path`: /home/evan/Documents/eval_tasks/experimental/logged-bandit-ope
- `failing_command`: harbor run -p /home/evan/Documents/eval_tasks/experimental/logged-bandit-ope --agent oracle --env docker --yes -n 1 --job-name logged-bandit-ope-reference-20260912T004406 -o /tmp/tv-interrogate-pilot/jobs
- `verifier_output`: /tmp/tv-interrogate-pilot/jobs/logged-bandit-ope-reference-20260912T004406/reference__B9gBww6/verifier/test-stdout.txt
- `verifier_output_tail`: PASSED test_state.py::test_mixed_heldout_matches_exact_value[43]
PASSED test_state.py::test_column_snips_misses_mixed_log
PASSED test_state.py::test_edge_snips_misses_mixed_log
PASSED test_state.py::test_column_snips_misses_edge_regime
PASSED test_state.py::test_edge_snips_misses_lab_regime
PASSED test_state.py::test_dashboard_mix_snips_misses_mixed_log
PASSED test_state.py::test_mean_reward_misses_mixed_log
FAILED test_state.py::test_live_json_snips_misses_mixed_log - FileNotFoundErr...
======================== 1 failed, 16 passed in 16.42s =========================
round 1/1 failed (rc=1)
- `interrogation_id`: logged-bandit-ope-20260912T004406
- `environment_fingerprint`: harbor 0.22.0, --env docker; task dir /home/evan/Documents/eval_tasks/experimental/logged-bandit-ope; harbor-official verifier, environment_mode separate; job logged-bandit-ope-reference-20260912T004406
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

- `reference_reward`: `0.0`
- `reference_accepted`: `False`
- `nop_reward`: `0.0`
- `nop_accepted`: `False`
- `diagnosis_class`: `verifier_invalid.hidden_test_requirement_reference_fails`
- `diagnosis_evidence`: `16/17 tests pass; test_live_json_snips_misses_mixed_log reads /app/policies/live.json. environment/policies has only logging.json and target.json. instruction.md never names live.json. solution does not create it. tests/generator.py comment says 'Do not read live.json'.`
- `machine_evidence`: `reference fails own verifier (hand-confirmed, doc 20)`

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

