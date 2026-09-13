# Review packet: `qemu-alpine-ssh`

Fill the checklist. Do not repair the task in this packet. Mark valid, invalid, or ambiguous.

## Identity

- Benchmark: `terminal-bench` `2.1`
- Provenance: `PENDING_HUMAN`
- Domain: unspecified
- Difficulty / expert hours: unspecified
- Current label: `pending`

## Artifacts

- `task_path`: /home/evan/Documents/tb21-dataset/terminal-bench-2-1/qemu-alpine-ssh
- `failing_command`: harbor run -p /home/evan/Documents/tb21-dataset/terminal-bench-2-1/qemu-alpine-ssh --agent oracle --env docker --yes -n 1 --job-name qemu-alpine-ssh-oracle-20260912T145428 -o /tmp/tv-tb21census/jobs
- `verifier_output`: /tmp/tv-tb21census/jobs/qemu-alpine-ssh-oracle-20260912T145428/qemu-alpine-ssh__8ZJy8Np/verifier/test-stdout.txt
- `verifier_output_tail`:   404  Not Found [IP: 199.232.178.132 80]
Get:7 http://deb.debian.org/debian bullseye/main amd64 libldap-common all 2.4.57+dfsg-3+deb11u1 [95.8 kB]
Get:8 http://deb.debian.org/debian bullseye/main amd64 sshpass amd64 1.09-1+b1 [13.0 kB]
Fetched 635 kB in 1s (1213 kB/s)
E: Failed to fetch http://deb.debian.org/debian-security/pool/updates/main/c/curl/libcurl4_7.74.0-1.3%2bdeb11u16_amd64.deb  404  Not Found [IP: 199.232.178.132 80]
E: Failed to fetch http://deb.debian.org/debian-security/pool/updates/main/c/curl/curl_7.74.0-1.3%2bdeb11u16_amd64.deb  404  Not Found [IP: 199.232.178.132 80]
E: Unable to fetch some archives, maybe run apt-get update or try with --fix-missing?
/tests/test.sh: line 8: curl: command not found
/tests/test.sh: line 10: /root/.local/bin/env: No such file or directory
/tests/test.sh: line 19: uvx: command not found
- `nop_job`: /tmp/tv-tb21census/jobs/qemu-alpine-ssh-nop-20260912T145648
- `environment_fingerprint`: harbor 0.22.0, --env docker; task dir /home/evan/Documents/tb21-dataset/terminal-bench-2-1/qemu-alpine-ssh; dataset terminal-bench/terminal-bench-2-1; job qemu-alpine-ssh-oracle-20260912T145428
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

- `source_benchmark`: `qemu`
- `oracle_reward`: `0.0`
- `oracle_accepted`: `False`
- `nop_reward`: `0.0`
- `nop_accepted`: `False`
- `oracle_status`: `executed`
- `nop_status`: `executed`
- `failing_tests`: `[]`
- `last_error_line`: ``
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

