# Review packet: `django__django-10097`

Fill the checklist. Do not repair the task in this packet. Mark valid, invalid, or ambiguous.

## Identity

- Benchmark: `swe-bench` `SWE-bench/SWE-bench test`
- Provenance: `PENDING_HUMAN`
- Domain: unspecified
- Difficulty / expert hours: unspecified
- Current label: `pending`

## Artifacts

- `failing_command`: swebench 5.0.2 run_evaluation, run_id tv100-empty, empty patch; verifier entry logs/run_evaluation/tv100-empty/tv-empty/django__django-10097/eval.sh
- `verifier_output`: logs/run_evaluation/tv100-empty/tv-empty/django__django-10097/test_output.txt (+ report.json in same dir)
- `verifier_output_tail`:   Applying sites_framework.0001_initial... OK
System check identified no issues (14 silenced).
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
Destroying test database for alias 'other' ('file:memorydb_other?mode=memory&cache=shared')...
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '>>>>> End Test Output'
+ echo '>>>>> Test Exit Code: 1'
+ git checkout b9cf764be62e77b4777b3a75ec256f6209a57671 tests/validators/invalid_urls.txt tests/validators/valid_urls.txt
>>>>> Test Exit Code: 1
Updated 2 paths from d4eb2e5cc3
- `gold_log_dir`: logs/run_evaluation/tv100-gold/tv-gold/django__django-10097
- `empty_log_dir`: logs/run_evaluation/tv100-empty/tv-empty/django__django-10097
- `environment_fingerprint`: swebench 5.0.2; image swebench/sweb.eval.x86_64.django_1776_django-10097:latest; container sweb.eval.django__django-10097.tv100-empty; dataset SWE-bench/SWE-bench split test
- `machine_verdict`: invalid
- `label_protocol`: verifier_invalid.fresh_environment.execution

## Machine evidence (may be incomplete)

- oracle_pass: `True`
- nop_fail: `False`
- environment_builds: `True`
- evaluation_deterministic: `None`
- mutation_kill_rate: `None`
- exploit_probe_rejected: `None`

### Static

- `gold_resolved`: `True`
- `empty_resolved`: `True`
- `gold_status`: `executed`
- `empty_status`: `executed`
- `gold_f2p_failures`: `[]`
- `gold_p2p_failures`: `[]`
- `machine_evidence`: `empty patch resolved (false accept)`

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

