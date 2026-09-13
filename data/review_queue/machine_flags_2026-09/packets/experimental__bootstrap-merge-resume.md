# Review packet: `experimental/bootstrap-merge-resume`

Fill the checklist. Do not repair the task in this packet. Mark valid, invalid, or ambiguous.

## Identity

- Benchmark: `eval_tasks` `local`
- Provenance: `PENDING_HUMAN`
- Domain: Data engineering
- Difficulty / expert hours: unspecified
- Current label: `pending`

## Artifacts

- `task_path`: /home/evan/Documents/eval_tasks/experimental/bootstrap-merge-resume
- `failing_command`: harbor run -p /home/evan/Documents/eval_tasks/experimental/bootstrap-merge-resume --agent oracle --env docker --yes -n 1 --job-name bootstrap-merge-resume-reference-20260912T003035 -o /tmp/tv-interrogate-pilot/jobs
- `verifier_output`: /tmp/tv-interrogate-pilot/jobs/bootstrap-merge-resume-reference-20260912T003035/reference__Ujv9J8V/verifier/test-stdout.txt
- `verifier_output_tail`:            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
test_state.py:7: in <module>
    from harness import (
harness.py:9: in <module>
    from warehouse.jobs.first_load import ingest_shards, publish_if_pending, replay_interrupt, resume_load
E   ModuleNotFoundError: No module named 'warehouse.jobs'
=========================== short test summary info ============================
ERROR test_state.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.14s ===============================
- `interrogation_id`: bootstrap-merge-resume-20260912T003035
- `environment_fingerprint`: harbor 0.22.0, --env docker; task dir /home/evan/Documents/eval_tasks/experimental/bootstrap-merge-resume; harbor-official verifier, environment_mode separate; job bootstrap-merge-resume-reference-20260912T003035
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
- `diagnosis_class`: `verifier_invalid.hidden_requirement_and_reference_fails_verifier`
- `diagnosis_evidence`: `pytest collection error: tests/harness.py imports warehouse.jobs.first_load (ingest_shards, publish_if_pending, replay_interrupt, resume_load). No warehouse/jobs/ exists in environment/ or solution/. instruction.md names ingest/probe/resume/pipeline commands under /app/warehouse but never a jobs.first_load module.`
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

