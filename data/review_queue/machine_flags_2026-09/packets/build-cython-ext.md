# Review packet: `build-cython-ext`

Fill the checklist. Do not repair the task in this packet. Mark valid, invalid, or ambiguous.

## Identity

- Benchmark: `terminal-bench` `2.1`
- Provenance: `PENDING_HUMAN`
- Domain: unspecified
- Difficulty / expert hours: unspecified
- Current label: `pending`

## Artifacts

- `task_path`: /home/evan/Documents/tb21-dataset/terminal-bench-2-1/build-cython-ext
- `failing_command`: harbor run -p /home/evan/Documents/tb21-dataset/terminal-bench-2-1/build-cython-ext --agent oracle --env docker --yes -n 1 --job-name build-cython-ext-oracle-20260912T104237 -o /tmp/tv-tb21census/jobs
- `verifier_output`: /tmp/tv-tb21census/jobs/build-cython-ext-oracle-20260912T104237/build-cython-ext__9fpbRd8/verifier/test-stdout.txt
- `verifier_output_tail`: PASSED ../tests/test_outputs.py::test_pyknotid_core_import
PASSED ../tests/test_outputs.py::test_chelpers_cython_extension
PASSED ../tests/test_outputs.py::test_ccomplexity_cython_extension
PASSED ../tests/test_outputs.py::test_cinvariants_cython_extension
PASSED ../tests/test_outputs.py::test_chelpers
PASSED ../tests/test_outputs.py::test_ccomplexity
PASSED ../tests/test_outputs.py::test_cinvariants_python_vs_cython
PASSED ../tests/test_outputs.py::test_example_usage
FAILED ../tests/test_outputs.py::test_pyknotid_repository_tests - AssertionEr...
========================= 1 failed, 10 passed in 4.95s =========================
- `nop_job`: /tmp/tv-tb21census/jobs/build-cython-ext-nop-20260912T104427
- `environment_fingerprint`: harbor 0.22.0, --env docker; task dir /home/evan/Documents/tb21-dataset/terminal-bench-2-1/build-cython-ext; dataset terminal-bench/terminal-bench-2-1; job build-cython-ext-oracle-20260912T104237
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
- `failing_tests`: `['../tests/test_outputs.py::test_pyknotid_repository_tests']`
- `last_error_line`: `E                +  where 1 = CompletedProcess(args=['python', '-m', 'pytest', '/tmp/tmp1gapwwh0/tests', '--ignore', '/tmp/tmp1gapwwh0/tests/test_ra...onstructed_space_curve\n========================= 1 failed, 17 passed in 2.19s =========================\n", stderr='').returncode`
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

