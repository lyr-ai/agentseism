# Final offline review — before Host 3

**2026-09-21.** `pilot_runs = 0`, `model_requests = 0`. Nothing is rented.

Reviewed at `HEAD` of `eval/pilot-outcome-grounded-ci`.

```
protocol_hash   5f4b95c9a250fccf
order_hash      cfe8856c9c9167b5     18 cells
pytest          648 passed
mock harness    108 passed
shellcheck      clean
```

---

## 1. Four cross-module invariants

These cut across the protocol, the backend, the budget and the shell, so no
single module's tests cover them.

### 1.1 The same vLLM session before and after the smoke test — **was broken, fixed**

`fingerprint` read a pid file. A server that died during the smoke run and
restarted — possibly reusing the pid — would have been bound as the session
that answered it.

`vllm_identity()` is the pid **plus its start time**, because a pid alone is
not an identity. It is captured when the server comes up, compared before and
after the smoke run, and compared again at fingerprint time. A restart clears
the `smoke.done` marker so the smoke test re-runs against the new session, and
the step-13 cross-check remains as the backstop.

### 1.2 The smoke test ran against the stack the pilot will use — **was unverifiable, fixed**

The smoke report recorded nothing about serving. It now carries the endpoint,
model, revision, vLLM pid, dependency-lock digest and serving-config digest,
and step 13 compares them **field by field** against the fingerprint.

A smoke test that proved some *other* stack works proves nothing about the one
that will serve the pilot, and a restart is exactly how that happens quietly.

### 1.3 `after_setup` postdates the smoke test — **was one stage too weak, fixed**

The checkpoint required only the `setup_started` marker, so a reading taken
*before* the smoke run would have satisfied it — host 2's defect one stage
later. A `smoke_completed` marker is written after a passing smoke run, and
the checkpoint demands a reading newer than that.

`after_setup` authorises `after_setup` only. Block 0 needs its own reading:
`check("before_block")` refuses any reading already consumed, which was
verified on a copy of the real host-2 log.

### 1.4 The smoke pull is the only new pull — **clean, no change needed**

The only `docker pull` in the shell is inside `run_smoke_test`, asserted by a
test that checks both the count and the call site. `build(dry_run=True)` and
both constructibility gates verify digests against **local** `docker image
inspect` metadata; a missing image fails and is never fetched, because a
digest that arrives during preflight was not the digest that was frozen. The
draw's pulls belong to `task_draw.py`, one per candidate, never retried.

### 1.5 The budget survives the host — **not a blocker, but a defect beside it**

Host 3 cannot re-base on its own start total. Nothing in the preflight path
calls `record_baseline`, and `record_baseline` refuses when a baseline exists.
Proven against the **real host-2 log**, not a fixture: a `$10.15` reading
yields `$2.99`, and re-basing raises `baseline_already_set`.

The defect sitting next to it: the launch-reading guard asked whether *any*
`billing_reading` existed in the log — and the log is carried from host to
host, which is what keeps the baseline frozen. Every host after the first
would have skipped its own launch reading entirely. The guard is now per host,
keyed on hostname plus boot time.

Two concepts are now distinct in the log:

| | |
|---|---|
| `experiment_billing_baseline` | `$7.16`, frozen, the only origin for every budget decision, **never reset** |
| `host_start` | the settled page total when a host launched. Records what that machine adds; authorises nothing, moves no threshold, and its own note says so |

Because the origin never moves, the stops correspond to **fixed page totals**,
and step 3b prints them so the operator reads numbers rather than doing
arithmetic:

| pilot state | page total |
|---|---|
| `$20` warning | **$27.16** |
| `$25` no new block | **$32.16** |
| `$30` absolute stop | **$37.16** |

Host 2's `$2.99` is inside every one of those figures and is not forgiven by
starting a new machine.

---

## 2. Amendments against the code

| | Registered | Enforced by |
|---|---|---|
| P.1 | the 1200 s cap is censoring, not failure | `INFRA_TIMEOUT_1200S` outside `SCORABLE`; invariant 2 forbids a verdict on a censored run |
| P.2 | 3 arms, 3 tasks, 2 replicates, 18 cells | `ARMS`, `TASK_COUNT`, `REPLICATES`, `verify()` fails closed on the order hash |
| P.3 | three distinct repositories | `select_tasks`, pure and unit-tested; `task_draw.py` the only Docker caller |
| P.4 | registered smoke test | `smoke.py`, six chain criteria, output confined to a `smoke` directory |
| P.5 | the recovery hint frozen as text | `HINTS` with both templates in full, `verify_hints()` failing closed both ways |
| P.6 | `FORMAT_ERROR_LIMIT_REACHED` + exit mapping | `EXIT_STATUS_MAP`, `SCORABLE`, and the `LimitsExceeded` assertion |

Every registered value that can drift is checked against its source by
`tests/test_preflight_constants.py`: the protocol hash, the order hash, the
cell count, the model id, revision and `max_model_len` against
`model_h2.yaml`, the baseline dollars, currency and period against the frozen
run log, and `EXPECTED_TESTS` against what pytest actually collects.

---

## 3. The nine backend conditions

| Condition | Test |
|---|---|
| `--backend real` is not a placeholder | `test_the_missing_execution_path_is_detected`, `test_a_placeholder_execution_path_is_rejected` |
| the full chain is connected | `build(dry_run=True)` + the registered smoke test |
| arms differ only by the registered mutation | `test_the_hint_is_indexed_exactly`, `_agent_result` sets only `step_limit` and `format_error_template` |
| the challenge fires exactly once, original not executed | `test_the_challenge_is_recorded_as_fired_once`, `test_the_suppressed_action_is_recorded_and_not_executed` |
| `INFRA_TIMEOUT_1200S` separate from `STEP_LIMIT_REACHED` | `test_a_censored_run_is_never_graded`, invariant 2 |
| only an explicit `resolved`; infra errors are not FAIL | `test_an_undecided_evaluator_is_not_a_failure`, `test_no_infrastructure_failure_becomes_resolved_false` |
| each cell frozen atomically with its digest | `run_pilot` freezes and verifies per cell before continuing |
| preflight verifies the backend is constructible | step 6b, and scenario 6a asserts it never reports READY |
| `run_pilot` reads its authorisation, never spends it | `test_the_runner_does_not_consume_the_first_blocks_reading` |

---

## 4. Findings

Three implementation defects, all fixed, none a design change:

1. the vLLM session was not re-verified across the smoke run (1.1);
2. the smoke report recorded no serving stack (1.2);
3. `after_setup` did not have to postdate the smoke run (1.3);
4. the launch-reading guard was global, so every host after the first would
   have skipped its own reading (1.5).

Two more found while fixing them:

5. a restarted vLLM kept a stale `smoke.done` marker; a new session now
   invalidates it;
6. the phase-ordering check read an `n` field that records written before `n`
   existed do not carry.

**No new amendment is required.** None of these changed a registered value;
each made the code do what P.4 and P.6 already say.

One earlier finding is worth repeating because it was a process failure rather
than a code one: blunt numeric string replaces, used to bump the frozen test
count, silently rewrote `MOCK_DRIVER="570.195.03"` through 574 and 588 to 614.
The "driver too old" scenario spent three commits asserting that a driver
*newer* than the minimum is rejected — passing while testing nothing. Count
bumping now uses targeted regexes and the fixture is a named constant.

---

## 5. Host 3 — the frozen sequence

No step is skipped and none is reordered.

1. wait for the `$10.15` page total to settle and read it with **nothing
   running**. It is recorded as `host_start`, **not** as a baseline: the
   experiment's origin stays `$7.16` and the cumulative spend opens at
   `$2.99`;
2. launch Host 3, `1× H100 80 GB PCIe`;
3. environment and dependency checks (steps 1–5: host, docker group, repo at a
   verified commit, environments from the frozen locks, the full suite);
4. **real backend constructibility gate** (6b) — before anything expensive;
5. restore or fetch the registered images and weights (7–9, 8b binds the
   digests);
6. start vLLM (10);
7. run the registered smoke test **once** (10b);
8. verify the smoke artifact and its digest (inside 10b; `artifact_frozen` is
   a pass criterion);
9. confirm the same vLLM pid is alive and freeze the serving fingerprint (11);
10. read a **new** billing total and authorise `after_setup`
    (`--not-before @smoke_completed`);
11. read **another** new total and authorise block 0;
12. execute the first three-cell block.

Reading #1 is entered at launch and authorises nothing but the early budget
check. One reading authorises one block, and a reading older than the work it
covers authorises nothing at all.

**Any failure between 3 and 11 stops the host.** Artifacts are retrieved and
verified, the instance is terminated, and the record says which condition
failed.
