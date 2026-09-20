# Pilot deployment checklist — stage A audit

**Branch:** `eval/pilot-outcome-grounded-ci` · **frozen start:** `2ff84bb`
**Date:** 2026-09-20. No machine rented, no agent run, no model call.

## A. Local audit — all pass

| # | Question | Answer |
|---|---|---|
| 1 | Registered parameters match `2ff84bb`? | Yes. `pilot_protocol.ARMS` is baseline 250/full · M1 **40**/full · M2 250/**error_only**, all with `challenge: True`; 3 tasks × 2 replicates; 1200 s cap; $20/$25/$30. |
| 2 | Order hash matches? | Yes. Regenerated from seed `20260920` → **`cfe8856c9c9167b5`**, 18 cells, verified at startup and **fails closed** on mismatch. |
| 3 | Any frozen parameter overridable from the CLI? | No. A test greps `main` for `--step-limit`, `--trials`, `--replicates`, `--timeout`, `--budget`, `--arms`, `--seed`, `--order`. `--tasks` passes drawn ids only; the hash is over **positions**, so ids cannot change the plan. |
| 4 | Hidden retries? | No new layer. The registered transport policy is used as-is and `transport_attempts` rides in every artifact. |
| 5 | Any branch decided after seeing results? | No. Budget checks occur at registered points only (`after_setup`, `before_block`); inside a block nothing is re-decided. Cell interpretability is a fixed 2-of-2 rule. |
| 6 | Could a timeout be read as a task failure? | No. `INFRA_TIMEOUT_1200S` is excluded from `SCORABLE`, and a test asserts the cap cannot manufacture a regression. `STEP_LIMIT_REACHED` is separate and **is** scorable — it is M1's mechanism. |
| 7 | Could a third replicate be run? | No. The plan is 18 fixed cells; a test counts backend calls per (task, arm) and asserts exactly `REPLICATES`. |
| 8 | Could an estimate authorise a run? | No. `source != "manual"` raises `estimate_only`; one reading authorises one block; a reading below baseline, a changed period or a changed currency each stop. |
| 9 | Could fake output reach the real results directory? | No. `--backend fake` writes under `.../synthetic/`, every artifact carries `synthetic: true`, and the report prints *synthetic execution test — not pilot evidence*. |
| 10 | Does the real runner need a double gate? | Yes. `--backend real` requires `--execute-registered-pilot`, and even then refuses locally: the real backend is wired on the instance, after the six deployment checks. |

## Two defects the tests found, both fixed

**The budget thresholds were C2-H's.** `Budget` imported `$85/$90/$100` from
`c2h_protocol`, so the pilot would have run under a ceiling nearly three times
its registered one. Thresholds are now injected, and a budget rule belonging to
one experiment is no longer another's default.

**`$25` was aliased to a stage stop.** Mapping it onto both `no_new_block` and
`stop_stage` turned *do not start another block* into *abandon the block you
are in* — stricter than registered, and it would truncate work already paid
for. `stop_stage` is now unreachable, because the pilot registration has no
such level.

## Verification run locally

```
pytest -q                                477 passed
python -m agentseism.pilot --resolve-only  18 cells · cfe8856c9c9167b5 · PASS
python -m agentseism.pilot --backend fake  18/18 cells frozen, digests verified
```

The fake run completes all 18 and is labelled synthetic throughout.

## B. On the instance — not started

1. rent `1× H100 80 GB PCIe`, Ubuntu 22.04, ≥100 GB disk, Docker;
2. **freeze the billing baseline first** — total, currency, period, UTC time;
3. draw three tasks by the registered rule, recording every pull attempt
   including failures;
4. freeze agent commit, image digests, `uname -m`, `nvidia-smi`, `docker
   version`, `pip freeze`;
5. start vLLM from the registered config and record PID, endpoint, model,
   revision, `max_model_len`, decoding parameters, GPU UUID, driver, CUDA,
   vLLM version, dependency-lock digest;
6. preflight: images run, evaluator yields a definite `resolved`, challenge
   path imports, artifact directory empty, retrieval rehearsed, disk
   sufficient, serving PID stable, and `--resolve-only` on the instance still
   gives 18 cells and `cfe8856c9c9167b5`.

**Any failure stops. No pilot run is produced.**

## C. Stop conditions during the run

Runtime fingerprint drift · vLLM PID change · image digest change · missing
transport attempts · an evaluator that cannot decide · an artifact that fails
its digest · needing a new block past $25 · reaching $30 · needing to change a
frozen parameter to continue.

Artifacts are kept; the output is a **feasibility / censored run** and never a
release verdict.
