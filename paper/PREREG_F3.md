# Pre-registration — F3, a three-cell evidence-path feasibility run

**Written 2026-09-23, before any F3 run exists and before any machine is
rented.** `study_mode: feasibility`, `verdict_authority: none`.

This is a **new experiment with its own identity**. It does not inherit the
closed Gate-2 pilot's registration, order, billing baseline, task draw, hosts,
or results, and it does not reopen them. The pilot is closed at
`infrastructure_feasibility_stop_before_run_0` and stays closed. F3 cites it
only for cost priors, which are observations about hardware, not results.

---

## 1. The one question

> In **one** pre-registered three-cell execution, does the **official entry
> point**, on a real host with the real served model, produce **one complete,
> scorable, retrievable evidence set for each of the three arms**?

That is the whole claim space. F3 answers yes or no and stops.

### Registered conclusion language

Each arm is executed **once**. One observation per arm cannot establish
stability, reliability, or a rate, and F3 will not be described as if it had.

| if all three cells meet §5 | F3 may state | F3 may **not** state |
|---|---|---|
| | `one_shot_execution_feasibility_established` | "the path is stable" |
| | the path produced three evidence sets **on this occasion** | "the path reliably produces evidence" |
| | | any success rate, or any projection to further runs |

A repeated-execution design, if one is wanted, is a separate registration with
replicates in it.

### What F3 explicitly does not answer

- It does **not** estimate the effect of M1 or M2.
- It does **not** report a direction, a risk difference, or a significance test.
- It does **not** compare arms at all. Three cells, one replicate: any
  difference between them is indistinguishable from run-to-run variance, and
  F3 is not powered to say otherwise — nor will it be discussed as suggestive.
- It does **not** say anything about task difficulty or generalisation, since
  it uses one task chosen to minimise infrastructure risk.

An F3 pass authorises **nothing** beyond the statement above.

## 2. Why this run is not redundant

Three things have been verified, never together:

| verified | by | gap |
|---|---|---|
| real Qwen through vLLM emits usable tool calls | host 5 smoke, 34 calls / 208 s | called `run_cell` directly, not the CLI |
| CLI → real container → real SWE-bench evaluator → digest-verified artifact | repair-phase Docker tests, 3 cells | **the model was stubbed** |
| evaluator report preserved, digest-anchored, refused when damaged | `tests/test_evaluator_evidence.py`, 18 tests | never exercised against a served model |

The untested composition is precisely *real model + official CLI + real
evaluator + evidence preservation, on one host, in one session*. That
composition is what stopped the pilot, and no local test can close it.

## 3. Subject — pinned, and unchanged from the pilot's mechanism

Agent, scaffold, prompt version, model, revision, serving configuration,
evaluator, arm definitions (`baseline` / `M1` / `M2`), hint texts and their
SHA-256, run cap (`RUN_TIMEOUT_SECONDS = 1200`), transport policy
(`transport_model()`, `TRANSPORT_ATTEMPTS = 1`, retry and cost-tracking env)
are reused **verbatim**. Reusing the mechanism is not inheriting the pilot's
identity: the mechanism is the thing under test.

## 4. Design

| | |
|---|---|
| tasks | 1 |
| arms | `baseline`, `M1`, `M2` |
| replicates | 1 |
| cells | **3** |
| order seed | `20260923` (new; the pilot's `20260920` is not reused) |
| arm order | `M2`, `baseline`, `M1` |
| `order_hash` | `a83650caeae31ff6` |

The arm order is shuffled rather than baseline-first so that drift over the
session does not align with an arm — the same reason the pilot interleaved,
kept here even though F3 will not compare arms.

### Task selection

One instance, fixed here and not revised: **`pytest-dev__pytest-10051`**.

This is a deliberate reversal of the pilot's exclusion, and the reason the
pilot excluded it does not apply. The pilot excluded it to keep prior
familiarity out of a set meant to *measure an effect*. F3 measures no effect.
For F3 the selection criterion is the opposite one — minimise the chance that
an infrastructure accident is misread as a path failure — and this instance is
the one whose image, container behaviour and evaluator output are already
known to work locally.

The cost is stated rather than hidden: **F3 can say nothing about whether the
path works on an unfamiliar task.** It is not designed to.

## 5. Evidence contract — the pass condition, registered before observation

F3 **passes** only if, for each of the three cells, all of the following exist
and verify after retrieval to a different machine:

1. a cell artifact with `synthetic: false` and all 22 required fields;
2. the artifact's `.sha256`, matching the artifact;
3. the preserved evaluator `report.json`, byte-identical to the evaluator's own
   output;
4. its `.sha256`, matching the report;
5. the report re-hashing to the digest **recorded in the artifact**, after
   unpacking from the retrieval bundle;
6. `agent_termination_code` ∈ `{COMPLETED, STEP_LIMIT_REACHED,
   FORMAT_ERROR_LIMIT_REACHED}` — i.e. `SCORABLE`;
7. `evaluator_resolved` ∈ `{RESOLVED_TRUE, RESOLVED_FALSE}`.

Note what conditions 6 and 7 do and do not require. A cell that runs cleanly
and resolves **false** is a *pass* for F3. F3 asks whether the path produces a
verdict, not which verdict. Reading `RESOLVED_FALSE` as a failure would be
reading an agent outcome as an infrastructure outcome — the exact conflation
the three-axis schema exists to prevent.

### Registered failure vocabulary

| observation | F3 outcome |
|---|---|
| all three cells meet 1–7 | **PASS** (`one_shot_execution_feasibility_established`) |
| any cell yields `INFRA_TIMEOUT_1200S` | **FAIL — infrastructure**, recorded, not retried |
| any cell yields `BACKEND_ERROR` or `INVALID` | **FAIL — path defect**, recorded |
| any cell yields `EVALUATOR_UNDECIDED` | **FAIL — evidence incomplete** |
| any evidence file missing or failing its digest | **FAIL — evidence not retrievable** |
| the host wall-clock limit (§7) is reached | **FAIL — host time**, partial state retrieved |
| a budget control (§6) stops F3 before three cells | **FAIL — budget**, and the reached state is the artifact |

A FAIL is a result. It is retrieved, recorded, and the host is terminated. **No
amendment is registered in response to an F3 failure**, and there is no second
F3 host — the rule that closed the pilot applies here from the start rather
than after three attempts.

## 6. Budget — what these numbers can and cannot do

F3 registers its own **operational baseline**:

- `f3_billing_baseline`: a **settled** cumulative total, read manually from the
  billing page **before** the F3 host is launched, and frozen in the execution
  log at that moment. F3 does not start until that reading exists.

Thresholds, grounded in the four observed pilot host costs ($2.99, $2.12,
$1.56, $3.05 — each covering bring-up through smoke):

| | | acts when |
|---|---|---|
| warning | **$8** | at the pre-launch reading |
| no new block | **$10** | at the pre-launch reading |
| absolute limit | **$12** | at the pre-launch and post-close readings |

### These are not in-block kill switches, and must not be described as such

F3 has exactly one block, and billing is read manually before it. Therefore:

- **`$10 no_new_block` has almost no operational force in F3** — there is no
  second block for it to withhold. It is carried for consistency with the
  state machine and to bind a future multi-block design, not because it can
  act here.
- **`$12 absolute` cannot interrupt the three cells while they run.** Nothing
  polls billing mid-block; the reading is manual. It is a pre-launch gate and a
  post-close accounting check, nothing more.

Calling $12 an "absolute stop" without this paragraph would claim more than the
implementation can do. What actually bounds in-block cost is §7.

## 7. What actually bounds cost inside the block

1. **Per cell:** `RUN_TIMEOUT_SECONDS = 1200`, enforced by the runner.
2. **Cell count:** exactly 3, fixed by the design, not withheld by a gate.
3. **Retrieval and termination immediately** after the third cell, or after the
   first failure, whichever comes first.
4. **Host wall-clock limit: 3.5 hours** from instance launch, covering setup,
   image pulls, model download, serving, all three cells, evaluation and
   retrieval. On reaching it the host is terminated with whatever state exists,
   and F3 records **FAIL — host time**.

The wall-clock limit is the binding control, and it is set to stay inside the
$12 figure rather than the other way round: at the observed H100 rate the
pilot's hosts billed at, 3.5 h lands around $9–12. It also covers the failure
mode billing cannot see at all — a download, a build or an evaluator that hangs
without spending unusually fast.

## 8. Cost reporting — F3 does not zero the project's history

A separate baseline is for computing F3's own spend. It is **not** a reset of
the project's cost narrative. Every F3 report states all three figures:

| figure | definition |
|---|---|
| closed pilot historical spend | **$9.72** (fixed, final, not revised by F3) |
| F3 spend | F3 close total − `f3_billing_baseline` |
| combined project spend | the sum of the two |

Reporting only the F3 figure would make the programme look cheaper than it has
been. The pilot's $9.72 bought a closed feasibility result and stays visible.

## 9. Sequence — no separate paid smoke

F3 *is* the feasibility run, and it uses the same task the host 5 smoke used. A
separate paid smoke before it would add task exposure, warm cache state and
cost while testing the same composition twice. The registered sequence is:

> preflight constructibility checks → bind the serving session → fresh settled
> billing reading → **F3 cell 1 → cell 2 → cell 3** → retrieval → terminate

The consequence is registered rather than discovered: **cell 1 is the
composition test.** If it fails, F3 ends by §5 — retrieved, recorded,
terminated, no retry, no amendment. That is the accepted price of not paying
for a smoke, and it is accepted here, before the result is known.

## 10. Implementation constraints

F3 needs its own identity. It must not get one by cloning the runner.

1. **`f3_protocol.py` carries values only** — task, arms, replicates, order
   seed, arm order, `order_hash`, budget thresholds, wall-clock limit, success
   conditions, and its own `protocol_hash`. No execution logic.
2. **The runner takes a protocol spec as a parameter.** The minimal refactor is
   to stop `pilot.py` and the backend reading a module-global
   `import pilot_protocol as P` and have them receive the spec instead. Both
   experiments then run the *same* code path.
3. **No second runner, no second backend.** Backend, hints, transport,
   evaluator and evidence preservation are reused as-is. Duplicating them is
   the failure this constraint exists to prevent: two paths drift, and the
   drift is invisible until one of them produces evidence the other cannot.
4. **Artifact and log hashes come from the injected spec**, never from a
   module-level constant.
5. **A test asserts the negative:** no F3 artifact or log line may contain
   `b7af66ca3ab783ab` or `cfe8856c9c9167b5`, the closed pilot's
   `protocol_hash` and `order_hash`. An identity claim that is only asserted
   positively is not checked against the thing it must differ from.
6. **Before any machine:** the three F3 cells must pass through the public CLI
   against local Docker and the real evaluator, exactly as the pilot's repair
   was verified. F3 is registered but not runnable until that passes.

## 11. Amendments

F3 is small enough that it should need none. Any amendment must be registered
**before** the observation it governs, must state what it would have been
before, and may not be prompted by an F3 result — an amendment answering an F3
failure is forbidden outright by §5.
