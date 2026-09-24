# F3 local verification — the precondition named in PREREG_F3 §10.6

F3 is registered but not runnable until its three cells pass through the
**public CLI** against real containers and the real SWE-bench evaluator. This
records that they did, with the numbers rather than a summary of them.

Recorded 2026-09-23 at `e89a5db` (plus the Docker guard commit that follows it).
Local Docker, stubbed model — the served model is exactly what F3 has not yet
been run against, and is the whole reason F3 exists.

## `tests/test_f3_cli_docker.py`

    7 passed in 17.73 s

Run alone, not as part of a batch.

## The three cells, from the probe's own output

    experiment        f3
    rc                0        exception: None
    elapsed_seconds   16.5
    registered_cells  3
    report            state=complete_3  cells_done=3  verdict_allowed=False
    report hashes     c145bebf3e39bc7d  a83650caeae31ff6

| artifact | digest_ok | synthetic | termination | outcome | protocol / order |
|---|---|---|---|---|---|
| `run_00_pytest-dev__pytest-10051_M2_r0.json` | **True** | False | `COMPLETED` | `RESOLVED_FALSE` | `c145bebf3e39bc7d` / `a83650caeae31ff6` |
| `run_01_pytest-dev__pytest-10051_baseline_r0.json` | **True** | False | `COMPLETED` | `RESOLVED_FALSE` | `c145bebf3e39bc7d` / `a83650caeae31ff6` |
| `run_02_pytest-dev__pytest-10051_M1_r0.json` | **True** | False | `COMPLETED` | `RESOLVED_FALSE` | `c145bebf3e39bc7d` / `a83650caeae31ff6` |

### Three of three `RESOLVED_FALSE` is the registered pass

Under §5 conditions 6 and 7 a cell passes when it terminates `SCORABLE` and the
evaluator returns a boolean. All three did. The stub model appends a line to
`CHANGELOG.rst` and submits, so nothing was ever going to resolve true; reading
that as a failure would be reading an agent outcome as an infrastructure one.

### `complete_3`, not a budget stop

The pilot's equivalent test asserts the runner *stops* after one block, because
17 unauthorised cells follow it. F3 has none: three cells are the design, so
completion is the correct ending. Both ran through the same `run_pilot`.

### No closed-pilot identity anywhere

Every artifact carries F3's hashes. `b7af66ca3ab783ab` and `cfe8856c9c9167b5`
appear in no file either run produced -- asserted directly, because a test that
only checks F3's own hashes are present would pass with the pilot's beside them.

## What this does *not* establish

The model was stubbed. F3's actual question -- the real served model through the
official entry point -- is untouched by this, and one execution per arm could
not establish a rate even if it had been real. This is a precondition being
met, not a feasibility result.

## The batch run that preceded it

An earlier batch of all five Docker modules hung for 49 minutes:
`swebench.harness.run_evaluation` asleep at 0% CPU, report directory empty,
alongside a container idle for an hour. **Recorded as an environment wedge:
neither a pass nor a failure.** It was killed, the containers removed, the
daemon confirmed healthy, and the modules re-run separately -- F3 in 17.73 s
and the remaining four at 55 passed in 110 s, matching the pre-refactor figure.

`tests/_docker_guard.py` now bounds every Docker probe at 1500 s and removes
stray containers on timeout, failure and success alike. A wedge fails loudly
rather than skipping: auto-skipping would hide a real regression that happens
to manifest as a hang, which is the same error as calling a hang a pass.
