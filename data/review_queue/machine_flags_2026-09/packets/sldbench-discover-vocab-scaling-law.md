# Review packet: `sldbench-discover-vocab-scaling-law`

Fill the checklist. Do not repair the task in this packet. Mark valid, invalid, or ambiguous.

## Identity

- Benchmark: `harbor-index` `1.0`
- Provenance: `PENDING_HUMAN`
- Domain: unspecified
- Difficulty / expert hours: unspecified
- Current label: `pending`

## Artifacts

- `task_path`: /home/evan/Documents/harbor-index-dataset/harbor-index-1.0/sldbench-discover-vocab-scaling-law
- `failing_command`: harbor run -p /home/evan/Documents/harbor-index-dataset/harbor-index-1.0/sldbench-discover-vocab-scaling-law --agent oracle --env docker --yes -n 1 --job-name sldbench-discover-vocab-scaling-law-oracle-20260912T061134 -o /tmp/tv-hindex/jobs
- `verifier_output`: /tmp/tv-hindex/jobs/sldbench-discover-vocab-scaling-law-oracle-20260912T061134/sldbench-discover-vocab-scaling__SdMJhWP/verifier/test-stdout.txt
- `verifier_output_tail`: `num_characters`. The fitted all-data coefficients are:

A=2856.8648050643937, alpha=2.2229172622805675e-05,
B=-7812.224949975335, beta=7.235503377025556e-06,
C=6687.910407905492, gamma=0.3792793472479527,
E=4950.502628383051.
---- EXPLAIN END ----
Starting evaluation for task: vocab_scaling_law
Reward written to /logs/verifier/reward.txt: 0.9663633622783212
Test harness exited with code: 0
- `nop_job`: /tmp/tv-hindex/jobs/sldbench-discover-vocab-scaling-law-nop-20260912T061224
- `environment_fingerprint`: harbor 0.22.0, --env docker; task dir /home/evan/Documents/harbor-index-dataset/harbor-index-1.0/sldbench-discover-vocab-scaling-law; dataset harbor-index/harbor-index-1.0; job sldbench-discover-vocab-scaling-law-oracle-20260912T061134
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

- `source_benchmark`: `sldbench`
- `oracle_reward`: `0.0`
- `oracle_accepted`: `False`
- `nop_reward`: `0.0`
- `nop_accepted`: `False`
- `oracle_status`: `executed`
- `nop_status`: `executed`
- `test_stdout_tail`: `D ----
---- EXPLAIN BEGIN ----
The submitted law uses the vocabulary scaling form:

L(N, V, D) = A / N**alpha + B / V**beta + C / D**gamma + E

where N is `non_vocab_parameters`, V is `vocab_size`, and D is
`num_characters`. The fitted all-data coefficients are:

A=2856.8648050643937, alpha=2.2229172622805675e-05,
B=-7812.224949975335, beta=7.235503377025556e-06,
C=6687.910407905492, gamma=0.3792793472479527,
E=4950.502628383051.
---- EXPLAIN END ----
Starting evaluation for task: vocab_scaling_law
Reward written to /logs/verifier/reward.txt: 0.9663633622783212
Test harness exited with code: 0`
- `stderr_tail`: `Collecting main service artifacts
Skipping image OS validation for docker.io/ternuraz/harbor-index-batch3:sldbench-discover-vocab-scaling-law-verifier-20260613-044124: docker inspect returned 1
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

