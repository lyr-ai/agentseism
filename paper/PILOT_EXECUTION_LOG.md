# Pilot execution log

The pilot registered in `PREREG_PILOT.md` (frozen at `2ff84bb`). One record per
host, appended in order. A host that ran no pilot cell still gets a record:
the reason a host was abandoned is part of the cost account.

---

## preflight_host_1 — 2026-09-20/21

```text
status               = stopped_before_pilot
reason               = billing_baseline_unrecoverable
instance_started_at  = 2026-09-20T23:58:46Z
pilot_runs           = 0
model_requests       = 0
```

**Provisioned.** Lambda, 1× H100 80 GB PCIe, x86_64, us-west-3.

**Preflight checks — all pass.**

| check | reading |
|---|---|
| `uname -m` | `x86_64`, kernel 6.8.0-1046-nvidia, Ubuntu 22.04 |
| GPU | 1× H100 PCIe, 81559 MiB, 0 MiB in use, no processes |
| driver / CUDA | 580.105.08 / 13.0 |
| Docker | client+server 29.2.1, API 1.53, daemon active |
| disk | 968 GB free of 993 GB |
| RAM / vCPU | 221 GB / 26 |
| Python | 3.10.12 |
| NVIDIA Container Toolkit | 1.18.1 |

**One host preparation action.** `ubuntu` was absent from the `docker` group
(the group existed and was empty), so the socket refused a non-root client.
`sudo usermod -aG docker ubuntu`; after re-login `id` carries `998(docker)`,
`docker version` reports the server without `sudo`, and `docker run --rm
hello-world` exits 0. The runner was **not** changed to `sudo docker`. This
happened before any fingerprint was frozen and before pilot run 0, so it is
host preparation, not an experimental change.

**Why the host was abandoned.** The billing baseline must be the cumulative
account total *before* this instance launched, because the registration puts
launch, preparation, model download and teardown inside the pilot's cost. The
instance was already billing before the Usage page was read, and no pre-launch
cumulative total could be recovered from it. Freezing the current total as the
baseline would have deleted the launch-to-baseline interval from the pilot's
recorded cost.

The alternative — reconstructing the missing amount from boot time × hourly
price — was rejected. `budget.py` exists to keep an estimate from ever
authorising anything, and an estimate substituted for the origin is worse than
one substituted for a reading: every later difference inherits it.

So: 0 pilot runs, 0 model requests, no weights downloaded, no vLLM started, GPU
never left 0 MiB. The instance was terminated.

**Ordering for host 2**, which is the whole point of this record:

1. Terminate host 1 and wait for Lambda's Usage page to take up its charges.
2. Read the page with nothing running — cumulative total, currency, billing
   period, UTC time of the reading. Keep a screenshot.
3. Freeze that value as the **pre-launch baseline**.
4. Only then launch the replacement (same shape: 1× H100 80 GB PCIe).
5. Enter the current cumulative total as reading #1 immediately after launch.

Under that order `pilot_spend = current_total − baseline` contains the new
instance's billed increment and nothing else, and the launch interval is inside
it rather than lost before it.

**Gate for host 2.** The local suite must be green before the next boot. At the
time of writing it is not: 9 `test_c2h_backend.py` failures and one
uncollectable module, all `ModuleNotFoundError: minisweagent` — `.venv` has
`agentseism` without `minisweagent`, `.venv-eval` the reverse. That is an
environment defect, not a product failure, and it is fixed locally at no
instance cost. Two real defects found during this preflight were fixed and
committed separately: the registered `$20` warning was documented but inert
(`c1813be`), and the CLI regression test was seeded with `hash()`, hence
salted per process and failing about one run in eight (`1874833`).

---

## billing_baseline — frozen 2026-09-21T00:49:52Z

Read from the Lambda Usage dashboard with **no instance running**, after both
earlier hosts had been terminated and taken up by the page.

```yaml
cumulative_total:    7.16
currency:            USD
billing_period:      September 2026
source:              manual
source_page:         Lambda Usage Dashboard
observed_at_utc:     2026-09-21T00:49:18Z
screenshot_retained: true
```

The page total is authoritative. It is **not** recomputed from the two line
items it covers — Gate 9's host (2026-09-20 01:47–03:17 UTC, 1.50 hr) and
`preflight_host_1` (2026-09-21 00:00–00:41 UTC, 0.68 hr) — because a
`duration × rate` reconstruction is an estimate, and this value is the origin
every later difference is measured against.

Frozen as entry 1 of `data/runs/pilot/run.jsonl`, with
`paper/manifests/pilot_billing_baseline.json` as the committed sidecar
(`sha256:176db393b3a2f353…`). Re-entry is refused by `baseline_already_set`,
verified against the real log.

`pilot_spend = current_total − 7.16`, checked end to end:

| page total | pilot spend | result |
|---|---|---|
| $7.16 | $0.00 | proceeds |
| $9.40 | $2.24 | proceeds — the actual difference, not zeroed |
| $27.16 | $20.00 | `budget_warning`, proceeds |
| $32.16 | $25.00 | `no_new_block` |
| $37.16 | $30.00 | `absolute` |

Reading #1 is entered immediately after host 2 launches. If the page still
reads $7.16 the initial spend is $0.00; if host 2's charges have already
appeared, the actual difference stands and is not reset to zero.

**Local gate for host 2: met.** Full suite 483 passed, 0 failed, three
consecutive runs, after `mini-swe-agent==2.4.6` was pinned into dev extras
(`2c7cc21`) and the unseeded CLI test was made deterministic (`1874833`).

---

## preflight_host_2 — 2026-09-21

```text
status               = preflight_complete_pilot_not_started
reason               = registered real backend absent
instance_started_at  = 2026-09-21T17:18:03Z
pilot_runs           = 0
model_requests       = 0
```

Lambda, 1× H100 80 GB PCIe, x86_64, us-west-3. Stage B was executed by
`inference/stage_b_preflight.sh` rather than by hand.

**Preflight reached `READY_FOR_MANUAL_PILOT_CONFIRMATION` twice**, once at
`2d31b54` and again, re-bound, at `491dc12`. Only the second authorises
anything; the first is setup evidence.

| | |
|---|---|
| binding commit | `491dc12e3ac9a12eedb8048a585e8a45955f673c` |
| report sha256 | `0e1fb1aa06ea56e95f3093e97c87315c58017268726a7ad3561deaad5ec0faf6` |
| vLLM | pid 6262, started 17:45:22Z, ready after 590 s |
| `max_model_len` | **131072 accepted** — KV cache 40.12 GiB, 631,254 tokens. The registered 65536 fallback was never approached |
| GPU | `GPU-b488b89e-6d66-b334-f320-cc9cd777ef38`, driver 580.105.08, CUDA 13.0 |
| vLLM / lock | 0.28.0 · `ba6a0feebbadd55c…` |
| parser flags | `--enable-auto-tool-choice`, `--tool-call-parser qwen3_coder`, `--reasoning-parser qwen3` all verified on the live command line |

**The draw (amendment P.3).** 254 candidates examined, 251
`duplicate_repository`, 3 `selected`, 0 `pull_failed`. The registered exclusion
never arose because `pytest-dev` sorts after `matplotlib`.

```
astropy__astropy-12907        @sha256:e082963099ed7d5a5f75a0be46e338be36faae33b2cba5289a9ddbd505997f1f
django__django-10097          @sha256:faf07f1d70370e9a4f76dac2cab0758300018f0eb4346b28aa55ac13630b873a
matplotlib__matplotlib-13989  @sha256:c84876a26e80d717b571a98a4bb339d0645ed601190c2078658788f0c9cc66ae
```

Identical across both runs, which is the determinism of the rule observed
rather than assumed.

## Why no cell ran

`agentseism.pilot` refuses `--backend real` with *"the real backend is wired on
the instance, after the six deployment checks"*. It never was. The only backend
in the tree is `fake_backend`, and nothing connects a cell to a task image, to
`mini-swe-agent`, to the `challenging()` wrapper or to the SWE-bench evaluator.

**The preflight verified the environment and never once verified that a cell
could execute.** That is the defect: a preflight able to report READY while the
runner does not exist. The next version must construct the real backend as a
check.

No backend was improvised on the billed instance. A runner written at run 0 is
not a frozen runner.

## Budget — the audit chain, kept whole

```text
baseline           $7.16   September 2026      frozen 2026-09-21T00:49:52Z
reading #1         $7.34   manual              17:27:21Z
budget_ok          after_setup   $0.18         17:45:29Z   SUPERSEDED
budget_superseded  + reason                    17:47:03Z
reading #2         $9.16   manual              17:56:43Z
budget_ok          after_setup   $2.00         17:56:43Z
reading #3         $9.25   manual              17:57:33Z
budget_ok          before_block  $2.09         17:57:33Z   SUPERSEDED
budget_superseded  + reason                    18:0x
```

Two checkpoints were superseded and neither was deleted. The first because it
was authorised by a launch reading taken before setup spent anything — the
defect that produced `Budget.check(not_before=...)`. The second because it
authorised a block that could not run. The invalid judgements, the reasons they
were invalid, and the valid judgement between them all stand.

Final pilot spend **$2.09** against a $30 ceiling, all of it setup.

## Retrieved and verified

`data/runs/pilot/preflight_host_2/` — bundle
`ea71feb889b35b3645ba6e1d725f81e44d2c61863d78d7b4ae6ac532ec338d30`, matched
host to local, and `preflight_report.json`, `serving_fingerprint.json` and
`retrieval_rehearsal.tgz` each re-verified against their own `.sha256` after
transfer. `data/runs/pilot/run.jsonl` carries the ten budget records above.

The retrieval path was rehearsed on an empty artifact tree during preflight and
then used for real here, which is the only reason it worked first time.

## Closed

```text
terminated_at        = 2026-09-21T18:13:00Z
instance_interval    = 17:18–18:13 UTC
billed_hours         = 0.91
page_total_at_close  = $10.15 USD
pilot_spend          = $2.99   ($10.15 − $7.16)
pilot_runs           = 0
model_requests       = 0
```

$2.99 of a $30 ceiling, none of it on an agent. The closing reading is entered
as reading #4 and **authorises nothing** — no checkpoint is taken on it. The
spend is recorded because launch, preparation, download and teardown are inside
the pilot's registered cost, so the next host's baseline must be read after
this one settles, not before.

Nothing experimental was lost. The pilot has never produced a run.

---

## host_3 — 2026-09-21

```text
status               = registered_smoke_failure
reason               = LiteLLM provider address missing; no valid model call
instance_started_at  = 2026-09-21T22:55:03Z
bound_commit         = f911ed0   (unchanged throughout; fd163ea was NOT taken)
pilot_runs           = 0
pilot_evidence       = none
```

> Registered smoke failure; the backend reached the container but failed before
> a valid model call because the LiteLLM provider address was missing. Internal
> retries were observed and are being eliminated prospectively.

## What the smoke test proved, by failing

Preflight passed every step up to and including vLLM: the host checks, the
docker group, the repo at the verified commit, both environments from the
frozen locks, 674 tests, the frozen plan, **backend constructibility**, the
P.3 draw, the image digests and their binding, the weights, and vLLM ready
after 575 s.

Then the chain broke where nothing offline could have caught it.
`mini-swe-agent` routes through LiteLLM, which needs a provider prefix to know
where to send a request. The registered model id was passed bare:

```
litellm.BadRequestError: LLM Provider NOT provided.
  You passed model=Qwen/Qwen3.6-27B-FP8
```

The container **started** — `docker run` succeeded and the image is recorded
at `sha256:e38365e835d4ba57…`. What failed was the first model call.

| criterion | result |
|---|---|
| `image_started` | **fail** — the container ran but the agent never executed in it |
| `valid_tool_call` | **fail** |
| `challenge_injected_once` | **fail** — nothing to inject into |
| `termination_registered` | pass |
| `evaluator_decided` | **fail** — `evaluator_resolved: null` |
| `artifact_frozen` | pass |

`outcome_state: BACKEND_ERROR`. **No `RESOLVED_FALSE` was produced.** A broken
chain did not become a task failure, which is the property the six criteria
exist to hold.

`smoke_completed` was never marked, so `after_setup` could not be taken.
`serving_fingerprint.json` was never written, so nothing was bound. There was
no session to preserve.

## Why it was not fixed in place

P.4 freezes it: *a smoke failure stops the host and is not re-run with adjusted
parameters.* The root cause is client addressing and the fix is one line, the
weights and images were already local, vLLM was warm on pid 6714, and redoing
the setup costs roughly `$2`. None of that matters. "The cause was small" is
exactly the argument that turns a stop rule into *adjust until it passes*, and
the rule was registered before anyone knew what the failure would look like.

The host was terminated with the artifacts retrieved and verified.

## A second finding, recorded for P.8

LiteLLM retried the failing call **nine times** internally, backing off 4s →
60s, all inside what the pilot counts as one execution. `run_cell` did not
retry; the transport did. P.4 says one agent execution per cell and C2-H had a
*registered* transport policy; the pilot inherited LiteLLM's defaults instead.
An unregistered retry sitting underneath a registered no-retry rule is a gap,
and it is closed prospectively rather than argued about after the fact.

## Retrieved and verified

`data/runs/pilot/host_3_smoke_failure/` — bundle
`d08f327456c28315862b6f6e08722d31a96301662f9901ffed3ce3d8078722ad`, matched
host to local; `smoke_run.json` and `smoke_report.json` each re-verified
against their own `.sha256` after transfer.

Recorded serving context at the moment of failure: vLLM pid **6714**, started
`Mon Sep 21 23:10:09 2026`, ready `23:19:47Z`, endpoint
`http://127.0.0.1:8000/v1`, revision `e89b16eb…eb09`, dependency lock
`fe76ffa6…`, serving config `afed5110…`.

## Naming correction, appended not overwritten

The log's `host_start` record named `$10.47`, a reading taken **after** this
host launched, which already contains what it had billed. Correct names:

| | |
|---|---|
| `experiment_billing_baseline` | `$7.16` — frozen, never reset |
| `host_start_total` | `$10.15` — settled, nothing running, before launch |
| `launch_reading` | `$10.47` — after launch |
| `cumulative_pilot_spend` | `$3.31` |
| billed between the two readings | `$0.32` — a direction, not a duration; the page lags |

Appended as `billing_provenance_note #14`. Everything before it is
byte-identical — the same SHA-256 before and after the append. Fixed
prospectively in `fd163ea`, which host 3 deliberately did not take.

## host_3 closed

```text
terminated_at        = 2026-09-21T23:34:00Z
instance_interval    = 22:56–23:34 UTC
billed_hours         = 0.65
page_total_at_close  = $12.27 USD
host_3_cost          = $2.12   ($12.27 − $10.15)
cumulative_pilot_spend = $5.11 ($12.27 − $7.16)
pilot_runs           = 0
smoke_outcome        = BACKEND_ERROR
pilot_evidence       = none
```

| stop | page total | remaining |
|---|---|---|
| `$20` warning | $27.16 | $14.89 |
| `$25` no new block | $32.16 | $19.89 |
| `$30` absolute | $37.16 | $24.89 |

`$5.11` of a `$30` ceiling across three hosts, none of which produced a pilot
run. The closing reading authorises nothing and no checkpoint is taken on it.

What the three hosts bought: a preflight that fails closed on a missing runner,
a budget machine that cannot be restarted by a new machine, and a smoke test
that stopped an eighteen-run batch before a single cell ran against a chain
that could not make a model call. None of that was reachable from a mock.

---

## host_4 — 2026-09-22

```text
status               = registered_smoke_failure
reason               = LiteLLM cost accounting discarded a successful response
instance_started_at  = 2026-09-22T05:03:30Z
terminated_by        = the operator (no Lambda credentials exist in this
                       working environment; the assistant cannot rent,
                       terminate, or read the billing page)
bound_commit         = 77769d1
page_total_at_close  = $13.83 USD
host_4_cost          = $1.56   ($13.83 − $12.27)
cumulative_pilot_spend = $6.67 ($13.83 − $7.16)
pilot_runs           = 0
pilot_evidence       = none
```

> Registered smoke failure after one successful model transport attempt. The
> response was discarded by LiteLLM cost accounting for an unmapped local
> model. No retry, no evaluator verdict, no pilot evidence.

**The end time shown on the Host 4 row is not recorded here**, because it was
not supplied and cannot be read from this environment. The closing total is
`$13.83`, settled.

## What failed

```
Error calculating cost for model openai/Qwen/Qwen3.6-27B-FP8:
  This model isn't mapped yet.
```

LiteLLM prices a response **after** generating it. A locally served model has
no price entry, so `_calculate_cost` raised on a response that had already
arrived. `n_calls: 0`, `challenge_status: NOT_ELIGIBLE`,
`infrastructure_status: BACKEND_ERROR`, `evaluator_resolved: None`.

**This project had already paid for this defect once.** It destroyed a Gate 9
attempt, was diagnosed, and the fix — `MSWEA_COST_TRACKING=ignore_errors` —
was written down. It was never carried into the pilot backend. Three preflight
gates, eight amendments and a registered smoke test did not include a check
against this project's own failure history.

## What held

| | |
|---|---|
| addressing (P.8) | `openai/Qwen/Qwen3.6-27B-FP8` reached the server; the container started; host 3's failure did not recur |
| retries (P.8.1) | `transport_attempts: 1`, **0 retries observed**, 1 cost error. Under the old policy that single failure would have become ten attempts with 4 s–60 s backoff |
| the smoke gate (P.4) | four criteria failed, `BACKEND_ERROR`, **no `RESOLVED_FALSE`** |
| the budget machine | `smoke_completed` unmarked, so `after_setup` was unreachable; no fingerprint frozen; nothing bound |

The apparatus did its job. It stopped an eighteen-run batch on a chain that
could not deliver one response.

## The methodological finding

Three smoke attempts, three different defects, **all of them on the success
path**:

| host | defect | reachable offline? |
|---|---|---|
| 2 | no runner existed at all | yes — now a constructibility gate |
| 3 | bare model id reached LiteLLM | yes — now a transport check |
| 4 | cost accounting discarded a successful response | yes — now a success-path test |

Every one was reachable without a GPU. The failure-path tests were extensive
and none of them touched the path a *working* response takes through the
client: parse, price, parse actions, inject the challenge. A stub that only
returns errors cannot reach the code that raised on host 4.

## Retrieved and verified

`data/runs/pilot/host_4_smoke_failure/` — bundle
`83fb8441bac278a03c2a843196d283a6ee76facc531d2a99e0b19c757bc38b0e`, matched
host to local; `smoke_run.json` and `smoke_report.json` each re-verified after
transfer. vLLM pid 6315, started `Tue Sep 22 05:19:05 2026`, ready after 580 s.

## Paid experiments paused

The registered stop condition — a second Host-4-class failure from a defect
findable offline — has fired. `$6.67` of `$30` spent across four hosts, zero
pilot runs, zero pilot evidence, zero contaminated data.

### host_4 — termination record, correction (appended, nothing overwritten)

The section above left the terminating actor implicit and the end time absent.
Recorded explicitly:

```text
termination_actor:    user
termination_method:   manual Lambda console action
terminated_at_utc:    unknown / not captured
page_total_at_close:  13.83 USD
```

`terminated_at_utc` is **unknown**, not inferred. The moment SSH stopped
answering is when this environment lost contact, not when Lambda stopped
billing, and substituting one for the other would put a fabricated timestamp
into a cost record.

No Lambda credential, config or API client exists in this working environment
— checked at the time — so termination could only have been performed from the
console by the operator.

The figures in the section above are unchanged and correct: `host_4_cost`
`$1.56`, `cumulative_pilot_spend` `$6.67`, `pilot_runs` `0`, `pilot_evidence`
`none`.

---

## host_5 — 2026-09-23

```text
status               = infrastructure_feasibility_stop_before_run_0
reason               = pilot entry point cannot construct or invoke the
                       registered real backend
instance_started_at  = 2026-09-23T17:50:23Z
bound_commit         = 52d7c2b
smoke                = PASS
pilot_runs           = 0
pilot_evidence       = none
```

## The registered smoke test passed

The one question no offline work could answer is answered: **the pinned
`Qwen/Qwen3.6-27B-FP8`, served by the registered vLLM with
`--tool-call-parser qwen3_coder` and `--reasoning-parser qwen3`, emits tool
calls the agent can use.**

| criterion | |
|---|---|
| `image_started` | ok |
| `valid_tool_call` | ok |
| `challenge_injected_once` | ok — fired once, original recorded and not executed |
| `termination_registered` | ok |
| `evaluator_decided` | ok |
| `artifact_frozen` | ok |

34 model calls in 208 s, `transport_attempts: 1`, `cost_tracking:
ignore_errors`, `recovered: true`, `suppressed_actions_executed: false`. The
real SWE-bench harness returned `resolved: true` — **reported, never gated on**;
a `false` would have passed identically and says nothing about any hypothesis.

vLLM pid **5821**, started `Wed Sep 23 18:05:53 2026`, identical before and
after the smoke run. `smoke_completed` at `18:18:48Z`. The fingerprint binds
that session, and step 13 matched smoke's serving record to it field by field.

`after_setup` was then taken on a reading that postdates the smoke run —
`$16.56` at `18:42:03Z`, `pilot_spend $9.40` — the first checkpoint in this
pilot that actually covers setup *and* smoke.

## Why it stopped anyway

`agentseism.pilot` still refuses `--backend real`:

> the real backend is wired on the instance, after the six deployment checks.
> Nothing here runs an agent.

Nothing in `pilot.py` constructs a `BackendConfig`, calls `build()`, or reaches
`run_cell`. The backend exists, is constructible, and was exercised
end-to-end — but **only through `run_smoke`, which calls `run_cell` directly.**
The registered pilot entry point was never connected to it.

Preflight's gate 6b verifies the backend is *constructible*. Nothing verified
that the **entry point can invoke it**. That is Host 2's defect in a new place,
and the smoke test could not catch it because the smoke test does not use that
entry point.

## Why there is no Host 6

P.10 names a *smoke* failure, and the smoke passed. The letter of it would
permit renting again. That reading is rejected.

Four hosts have now ended the same way: find an execution-chain gap, fix it,
add tests, rent again. Using a textual boundary to take a fifth step in that
loop is the loop. The honest finding is not about this particular missing
wire:

> The test apparatus repeatedly proves the **components** and repeatedly fails
> to prove the **registered entry point is executable end to end.**

`pilot.py` can be fixed offline. That is subsequent software work. **A host
rented after it does not belong to this pre-registered pilot.**

## What this pilot established

| | |
|---|---|
| smoke chain | works, on real hardware, with the registered model and parser |
| real backend | constructible and exercised end to end against a real container and the real evaluator |
| registered entry point | **not executable** |
| pilot runs | 0 |
| pilot evidence | none |
| infrastructure feasibility | **not reached** |

## Retrieved and verified

`data/runs/pilot/host_5_stop_before_run_0/` — bundle
`522d133a5e99cf3d9450d82ff4f8be74f19fbe8477d067afd86ff55674e1095c`, matched
host to local. Four artifacts re-verified against their own digests after
transfer: `smoke_run.json`, `smoke_report.json`, `serving_fingerprint.json`,
`preflight_report.json`.

## host_5 closed, and the pilot ends

```text
termination_actor:    user
termination_method:   manual Lambda console action
terminated_at_utc:    unknown / not captured
page_total_at_close:  $16.88 USD
host_5_cost:          $3.05   ($16.88 − $13.83)
```

## Final accounting for the pre-registered pilot

```text
experiment_billing_baseline  $7.16    frozen 2026-09-21T00:49:52Z, never reset
final page total             $16.88
cumulative_pilot_spend       $9.72    32% of the $30 absolute stop
unspent                      $20.28
billing readings             11
checkpoints taken            4  (two superseded, with reasons)
pilot_runs                   0
pilot_evidence               none
```

| host | outcome | cost |
|---|---|---|
| Gate 9 host | (pre-baseline) | — |
| `preflight_host_1` | baseline unrecoverable, stopped before pilot | (pre-baseline) |
| `preflight_host_2` | READY, no runner existed | $2.99 |
| `host_3` | smoke failure — bare model id reached LiteLLM | $2.12 |
| `host_4` | smoke failure — cost accounting discarded a successful response | $1.56 |
| `host_5` | **smoke PASS**, entry point not executable | $3.05 |

No budget stop was ever reached. The pilot did not end because it ran out of
money; it ended because the registered entry point could not run a cell, and
because continuing would have meant a fifth fix-and-rent cycle.

## What was established, and what was not

**Established.** The registered serving stack works: the pinned
`Qwen/Qwen3.6-27B-FP8` under vLLM 0.28.0 with `qwen3_coder` /`qwen3` parsers
emits usable tool calls; the challenge fires exactly once and the suppressed
action never executes; recovery happens; the real SWE-bench harness returns an
explicit verdict; one transport attempt per logical request; a wall-clock cap
censors without grading. Most of that is now provable on CPU and Docker alone.

**Not established.** Whether reducing `max_steps` or removing the recovery
hint changes anything. **No cell of the registered 18 was ever executed.** The
pilot has no outcome data and supports no claim about M1, M2, or the method's
sensitivity.

## The engineering finding

Across four hosts the same shape recurred: a defect in the execution chain
that every component test passed over.

| host | defect | the test that should have caught it |
|---|---|---|
| 2 | no runner existed | constructibility gate — added after |
| 3 | bare model id reached LiteLLM | transport check — added after |
| 4 | cost accounting discarded a response | success-path test — added after |
| 5 | entry point never wired to the backend | **none existed** |

Two of these — the cost policy and the evaluator's report reader — were
mechanisms the project had already built and verified elsewhere, and the pilot
reimplemented or omitted rather than reused.

> The apparatus reliably proves components. It has never proved that the
> registered entry point is executable end to end.

Every added gate checked a *part*. The smoke test exercised the chain through
`run_smoke`, which calls `run_cell` directly, so the one path the pilot would
actually take — `agentseism.pilot --backend real` — was never executed by
anything, on any host, at any point.

## Status

`infrastructure_feasibility_stop_before_run_0`. This pre-registered pilot is
closed. `pilot.py` may be repaired as ordinary software work; a host rented
afterwards is **not** part of this registration and would require its own.
