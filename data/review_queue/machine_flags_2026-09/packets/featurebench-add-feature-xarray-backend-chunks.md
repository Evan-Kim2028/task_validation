# Review packet: `featurebench-add-feature-xarray-backend-chunks`

Fill the checklist. Do not repair the task in this packet. Mark valid, invalid, or ambiguous.

## Identity

- Benchmark: `harbor-index` `1.0`
- Provenance: `PENDING_HUMAN`
- Domain: unspecified
- Difficulty / expert hours: unspecified
- Current label: `pending`

## Artifacts

- `task_path`: /home/evan/Documents/harbor-index-dataset/harbor-index-1.0/featurebench-add-feature-xarray-backend-chunks
- `failing_command`: harbor run -p /home/evan/Documents/harbor-index-dataset/harbor-index-1.0/featurebench-add-feature-xarray-backend-chunks --agent oracle --env docker --yes -n 1 --job-name featurebench-add-feature-xarray-backend-chunks-oracle-20260912T034513 -o /tmp/tv-hindex/jobs
- `verifier_output`: /tmp/tv-hindex/jobs/featurebench-add-feature-xarray-backend-chunks-oracle-20260912T034513/featurebench-add-feature-xarray__jnhegtq/verifier/test-stdout.txt
- `verifier_output_tail`: FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks1-region1-nd_v_chunks1-expected_chunks1]
FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks2-region2-nd_v_chunks2-expected_chunks2]
FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks3-region3-nd_v_chunks3-expected_chunks3]
FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks4-region4-nd_v_chunks4-expected_chunks4]
FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks5-region5-nd_v_chunks5-expected_chunks5]
FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks6-region6-nd_v_chunks6-expected_chunks6]
FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks7-region7-nd_v_chunks7-expected_chunks7]
FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks8-region8-nd_v_chunks8-expected_chunks8]
========================= 9 failed, 9 passed in 1.87s ==========================
Reward: 0
- `nop_job`: /tmp/tv-hindex/jobs/featurebench-add-feature-xarray-backend-chunks-nop-20260912T035108
- `environment_fingerprint`: harbor 0.22.0, --env docker; task dir /home/evan/Documents/harbor-index-dataset/harbor-index-1.0/featurebench-add-feature-xarray-backend-chunks; dataset harbor-index/harbor-index-1.0; job featurebench-add-feature-xarray-backend-chunks-oracle-20260912T034513
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

- `source_benchmark`: `featurebench`
- `oracle_reward`: `0.0`
- `oracle_accepted`: `False`
- `nop_reward`: `0.0`
- `nop_accepted`: `False`
- `oracle_status`: `executed`
- `nop_status`: `executed`
- `test_stdout_tail`: `nk[enc_chunks4-region4-nd_v_chunks4-expected_chunks4]
FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks5-region5-nd_v_chunks5-expected_chunks5]
FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks6-region6-nd_v_chunks6-expected_chunks6]
FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks7-region7-nd_v_chunks7-expected_chunks7]
FAILED xarray/tests/test_backends_chunks.py::test_grid_rechunk[enc_chunks8-region8-nd_v_chunks8-expected_chunks8]
========================= 9 failed, 9 passed in 1.87s ==========================
Reward: 0`
- `stderr_tail`: `S validation for crystalxyz/add-feature-xarray-backend-chunks:20260624-212604: docker inspect returned 1
Collecting main service artifacts
Skipping image OS validation for ternuraz/harbor-index-batch3:featurebench-add-feature-xarray-backend-chunks-verifier-20260627-123800: docker inspect returned 1
`
- `machine_evidence`: `reference (oracle) rejected by official verifier`

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

