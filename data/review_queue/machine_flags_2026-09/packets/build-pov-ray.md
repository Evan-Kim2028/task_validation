# Review packet: `build-pov-ray`

Fill the checklist. Do not repair the task in this packet. Mark valid, invalid, or ambiguous.

## Identity

- Benchmark: `terminal-bench` `2.1`
- Provenance: `PENDING_HUMAN`
- Domain: unspecified
- Difficulty / expert hours: unspecified
- Current label: `pending`

## Artifacts

- `task_path`: /home/evan/Documents/tb21-dataset/terminal-bench-2-1/build-pov-ray
- `failing_command`: harbor run -p /home/evan/Documents/tb21-dataset/terminal-bench-2-1/build-pov-ray --agent oracle --env docker --yes -n 1 --job-name build-pov-ray-oracle-20260912T104717 -o /tmp/tv-tb21census/jobs
- `verifier_output`: /tmp/tv-tb21census/jobs/build-pov-ray-oracle-20260912T104717/build-pov-ray__mePifkB/verifier/test-stdout.txt
- `verifier_output_tail`: E       assert False
E        +  where False = exists()
E        +    where exists = PosixPath('/app/povray-2.2').exists

/tests/test_outputs.py:95: AssertionError
=========================== short test summary info ============================
FAILED ../tests/test_outputs.py::test_illum1_render_and_verify - FileNotFound...
FAILED ../tests/test_outputs.py::test_povray_version - FileNotFoundError: [Er...
FAILED ../tests/test_outputs.py::test_povray_built_from_correct_source - Asse...
============================== 3 failed in 1.75s ===============================
- `nop_job`: /tmp/tv-tb21census/jobs/build-pov-ray-nop-20260912T104852
- `environment_fingerprint`: harbor 0.22.0, --env docker; task dir /home/evan/Documents/tb21-dataset/terminal-bench-2-1/build-pov-ray; dataset terminal-bench/terminal-bench-2-1; job build-pov-ray-oracle-20260912T104717
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

- `source_benchmark`: `build`
- `oracle_reward`: `0.0`
- `oracle_accepted`: `False`
- `nop_reward`: `0.0`
- `nop_accepted`: `False`
- `oracle_status`: `executed`
- `nop_status`: `executed`
- `failing_tests`: `['../tests/test_outputs.py::test_illum1_render_and_verify', '../tests/test_outputs.py::test_povray_version', '../tests/test_outputs.py::test_povray_built_from_correct_source']`
- `last_error_line`: `E        +    where exists = PosixPath('/app/povray-2.2').exists`
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

