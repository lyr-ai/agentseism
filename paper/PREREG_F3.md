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

> Can the **official entry point**, on a real host with the real served model,
> produce **three complete, scorable, retrievable evidence sets** — one per arm
> — for a single pre-selected task?

That is the whole claim space. F3 answers yes or no and stops.

### What F3 explicitly does not answer

- It does **not** estimate the effect of M1 or M2.
- It does **not** report a direction, a risk difference, or a significance test.
- It does **not** compare arms at all. Three cells, one replicate: any
  difference between them is indistinguishable from run-to-run variance, and
  F3 is not powered to say otherwise — nor will it be discussed as suggestive.
- It does **not** say anything about task difficulty or generalisation, since
  it uses one task chosen for infrastructure reliability.

An F3 pass authorises **nothing** beyond the statement that the path works. A
confirmatory design, if one follows, is a separate registration.

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

Software is pinned at commit `5a2070a776c9a4217663b6756435ab0acfb10978`.

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
| all three cells meet 1–7 | **PASS** |
| any cell yields `INFRA_TIMEOUT_1200S` | **FAIL — infrastructure**, recorded, not retried |
| any cell yields `BACKEND_ERROR` or `INVALID` | **FAIL — path defect**, recorded |
| any cell yields `EVALUATOR_UNDECIDED` | **FAIL — evidence incomplete** |
| any evidence file missing or failing its digest | **FAIL — evidence not retrievable** |
| fewer than three cells complete before a budget stop | **FAIL — budget**, and the reached state is the artifact |

A FAIL is a result. It is retrieved, recorded, and the host is terminated. **No
amendment is registered in response to an F3 failure**, and there is no second
F3 host — the rule that closed the pilot applies here from the start rather
than after three attempts.

## 6. Budget — a new baseline, not the pilot's

The pilot's `experiment_billing_baseline` ($7.16) and its $20/$25/$30
thresholds are **not** carried over. F3 registers:

- `f3_billing_baseline`: a **settled** cumulative total, read manually from the
  billing page **before** the F3 host is launched, and frozen in the execution
  log at that moment. F3 does not start until that reading exists.
- thresholds, grounded in the four observed pilot host costs
  ($2.99, $2.12, $1.56, $3.05 — each covering bring-up through smoke):

| | |
|---|---|
| warning | **$8** |
| no new block | **$10** |
| absolute limit | **$12** |

Expected: ~$3 to reach a passing smoke, plus at most 1 h of runs. The limit is
roughly 4× the expected figure and about 40% of the closed pilot's.

The pilot's budget state machine is reused unchanged: readings are manual, one
reading authorises one block, `not_before` enforces freshness, and supersession
is append-only.

## 7. Stop rules

1. **F3 is authorised for exactly one block of three cells.** The design ends
   there. Expansion to a larger grid is not an F3 decision and cannot be made
   by observing F3's result.
2. The host is **terminated immediately** after the retrieval bundle is
   verified, pass or fail. Termination is not conditional on the outcome.
3. One host. No second attempt, no amendment-and-retry.
4. Any budget threshold breach stops F3 where it stands; the partial state is
   the artifact.

## 8. Open item that must be closed before any machine is rented

`pilot.py` stamps every cell artifact and log line with
`protocol_hash = b7af66ca3ab783ab` and `order_hash = cfe8856c9c9167b5` — the
**closed pilot's** identity — because both are read from `pilot_protocol.py`.
Running F3 on unmodified software would therefore brand F3's evidence with the
identity of a closed experiment, which is exactly what this registration
forbids.

So F3 requires one narrowly scoped software change before it can run: a
separate protocol module carrying F3's own values (1 task, 1 replicate, seed
`20260923`, `order_hash a83650caeae31ff6`, the $8/$10/$12 thresholds) and its
own `protocol_hash`, selected by the CLI. **No mechanism changes** — same arms,
same hints, same transport, same evaluator, same evidence path.

Until that change exists and is verified, F3 is registered but not runnable.

## 9. Amendments

F3 is small enough that it should need none. Any amendment must be registered
**before** the observation it governs, must state what it would have been
before, and may not be prompted by an F3 result — an amendment answering an F3
failure is forbidden outright by §5.
