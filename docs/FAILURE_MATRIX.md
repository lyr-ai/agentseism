# Failure matrix

Every failure this project has paid a GPU to discover, and the check that now
catches it for free. Causes are read from the frozen logs
(`paper/GATE9_EXECUTION_LOG.md`, `paper/PILOT_EXECUTION_LOG.md`) and from the
commits, **not from recollection**; `tests/test_failure_matrix.py` asserts the
counts against those files so the history cannot drift.

`pilot_runs = 0` · `$6.67` spent across four hosts · no pilot evidence.

## Gate 9 — three aborted attempts, 2026-09-20

Each produced **zero valid responses** and wrote **no artifact**, asserted by
`test_every_gate9_attempt_produced_zero_responses_and_no_artifact`.

| # | Cause (frozen log) | Caught now by |
|---|---|---|
| 1 | `gate9.py` issued a plain non-streaming call, dropping registered `stream`, `attempt_timeout`, `max_attempts`; serving config missing `--reasoning-parser`, so reasoning returned as content and one root passed 36,000 tokens | the three parser keys are asserted in `model_h2.yaml` and verified on the **live command line** at step 11 |
| 2 | server rejected tool calls: `"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser`; `model_h2.yaml` never carried the keys its own header claimed | same check, plus `test_the_three_parser_keys_are_in_the_serving_config` |
| 3 | LiteLLM raised `Error calculating cost … isn't mapped yet` **after** generating, discarding every response. `MSWEA_COST_TRACKING=ignore_errors` was exported by `run_phase_a.sh` but not by `run_c2.py` or `gate9.py` | **P.9** — and see below |

Two further deployment defects from the same log:

| Cause | Caught now by |
|---|---|
| `requirements.txt` pins never resolved in a clean environment | environments built from frozen locks; `test_the_eval_lock_pins_what_the_suite_and_evaluator_need` |
| `start_vllm.sh` hardcoded `--host 0.0.0.0`, publishing an unauthenticated endpoint on a public-IP VM | `test_the_serving_host_is_loopback`, checking code rather than the comment that explains it |

## The pilot — hosts 2, 3, 4

| host | Cause | Caught now by |
|---|---|---|
| 2 | `READY_FOR_MANUAL_PILOT_CONFIRMATION` with **no runner in existence** — `--backend real` was a placeholder | preflight step 6b, `build(dry_run=True)`; harness scenario 6a asserts it never reports READY |
| 3 | bare model id reached LiteLLM: `LLM Provider NOT provided` | P.8 addressing; `_check_transport` refuses a bare or double-prefixed id, sending nothing |
| 4 | LiteLLM cost accounting discarded a **successful** response | P.9; the success-path probe reproduces it in 0.1 s |

## The repeat

`MSWEA_COST_TRACKING=ignore_errors` was **already registered** —
`CODING_EXPERIMENT_PREREG.md:91`, `INTERVENTION_PREREG_H2.md:228` — and set by
`gate9.py:182`, `c2h_backend.py:143` and `run_phase_a.sh`. At `77769d1` it
appeared **zero times** in `src/agentseism/real_backend.py` and
`inference/stage_b_preflight.sh`.

Gate 9 classified this as a *registered-environment propagation defect* and
fixed two runners. The pilot backend was a third runner, written later, that
never inherited it. The same variable stopped two experiments five months
apart.

`test_every_runner_in_the_tree_sets_the_cost_variable` now enumerates the
runners, and `test_every_registered_env_value_is_exported_by_the_script`
checks the general case: anything in `RETRY_ENV` or `COST_ENV` must be
exported before Python starts and asserted by the backend.

## The pattern

| host | defect | on the success path? | reachable offline? |
|---|---|---|---|
| 2 | no runner | — | yes |
| 3 | addressing | yes | yes |
| 4 | cost accounting | yes | yes |

Three smoke attempts, three defects, **all reachable without a GPU**. The
failure-path tests were thorough and none of them touched the path a *working*
response takes through the client — parse, price, parse actions, inject the
challenge. A stub that only returns errors cannot reach the code that raised
on host 4.

That gap is what `tests/_transport_probe.py`'s `success` mode closes, with a
`success_without_fix` control that reproduces host 4 exactly:

```
registered configuration   1 request, no exception, actions ["ls /testbed"]
control (neither fix)      RuntimeError: Error calculating cost … isn't mapped yet
```

## Registered values

```
protocol_hash  cc9b0c3ff329ef58
order_hash     cfe8856c9c9167b5
```
