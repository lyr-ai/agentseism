"""F3 as data: a three-cell evidence-path feasibility run, registered 2026-09-23.

`paper/PREREG_F3.md` is the registration; this module is the part a program can
check. It carries **values only** -- no execution logic -- because F3 runs on
exactly the same runner, backend, hints, transport, evaluator and evidence path
as the closed pilot. That reuse is the point: F3 tests that mechanism, and a
second copy of it would test a different one.

What F3 does *not* share is identity. Every artifact and log line stamps a
`protocol_hash` and an `order_hash`, and until this module existed both came
from `pilot_protocol` globals -- so running F3 on the unmodified runner would
have branded new evidence with a closed experiment's identity.

F3 answers one question: in a single pre-registered three-cell execution, does
the official entry point produce one complete, scorable, retrievable evidence
set for each arm? One observation per arm cannot establish a rate, so a pass
licenses `one_shot_execution_feasibility_established` and nothing wider.
"""

from __future__ import annotations

import hashlib
import json

from agentseism import protocol_spec as _spec
from agentseism.pilot_protocol import (
    ARMS, COST_ENV, COST_TRACKING, EXIT_STATUS_MAP, HINT_SHA256,
    LITELLM_PROVIDER, RETRY_ENV, RETRY_KNOBS, RUN_TIMEOUT_SECONDS,
    SCHEMA_VERSION, SCORABLE, TRANSPORT_ATTEMPTS,
)

PREREG = "paper/PREREG_F3.md"

# ── design ──
TASK = "pytest-dev__pytest-10051"
"""Fixed here, not drawn.

A deliberate reversal of the pilot's exclusion, and the reason for that
exclusion does not carry over. The pilot excluded this instance to keep prior
familiarity out of a set meant to *measure an effect*; F3 measures no effect,
so the criterion inverts -- minimise the chance an infrastructure accident is
misread as a path failure. The price is registered rather than hidden: F3 can
say nothing about an unfamiliar task.
"""

TASK_COUNT = 1
REPLICATES = 1
"""One execution per arm. This is why F3 may not claim stability or a rate."""

ORDER_SEED = 20260923
ORDER_HASH = "a83650caeae31ff6"
"""Arms run `M2`, `baseline`, `M1`.

Shuffled rather than baseline-first so drift over the session does not align
with an arm -- kept even though F3 will not compare arms, because the ordering
discipline should not depend on what a given run intends to conclude.
"""

# ── budget ──
WARNING_USD = 8.0
NO_NEW_BLOCK_USD = 10.0
ABSOLUTE_LIMIT_USD = 12.0
"""Grounded in the four observed pilot host costs -- $2.99, $2.12, $1.56,
$3.05 -- each of which covered bring-up through smoke.

**These are not in-block kill switches.** F3 has one block and billing is read
manually before it, so `NO_NEW_BLOCK_USD` has almost no operational force here
(there is no second block to withhold) and `ABSOLUTE_LIMIT_USD` cannot
interrupt a running cell -- nothing polls billing mid-block. Both act at the
pre-launch reading and the post-close accounting check. What actually bounds
in-block cost is `RUN_TIMEOUT_SECONDS` per cell, a cell count fixed at three by
the design, immediate teardown, and `HOST_WALL_CLOCK_SECONDS`.
"""

HOST_WALL_CLOCK_SECONDS = 12600          # 3.5 hours
"""The binding in-block control, covering setup, image pulls, model download,
serving, all three cells, evaluation and retrieval.

Set to stay inside `ABSOLUTE_LIMIT_USD` rather than the reverse: at the rate
the pilot's hosts billed at, 3.5 h lands around $9-12. It also covers the
failure billing cannot see at all -- a download, build or evaluator that hangs
without spending unusually fast.
"""

CLOSED_PILOT_SPEND_USD = 9.72
"""Carried so F3 cannot quietly zero the programme's cost history.

F3 has its own operational baseline for computing its own spend. Every report
states three figures: this one, F3 spend, and their sum. Reporting only F3's
would make the programme look cheaper than it has been.
"""

# ── conclusion language, registered before the result ──
PASS_CLAIM = "one_shot_execution_feasibility_established"
FORBIDDEN_CLAIMS = ("stable", "stability", "reliable", "reliability",
                    "success_rate", "generalises")
"""One observation per arm supports none of these, and naming them here makes
the prohibition checkable rather than a matter of tone."""

NO_SEPARATE_SMOKE = True
"""F3 *is* the feasibility run, on the same task the host 5 smoke used.

Paying for a smoke first would test the same composition twice while adding
task exposure and warm cache state. The consequence is registered in advance:
**cell 1 is the composition test**, and if it fails F3 ends -- retrieved,
recorded, terminated, no retry, no amendment.
"""


def protocol_hash() -> str:
    """Over the values F3 registered, not a union with the pilot's.

    A shared hashing function across both experiments would have moved the
    pilot's frozen `b7af66ca3ab783ab` the moment F3 added a field.
    """
    return hashlib.sha256(json.dumps(
        {"prereg": PREREG, "arms": ARMS, "task": TASK, "tasks": TASK_COUNT,
         "replicates": REPLICATES, "timeout": RUN_TIMEOUT_SECONDS,
         "budget": [WARNING_USD, NO_NEW_BLOCK_USD, ABSOLUTE_LIMIT_USD],
         "host_wall_clock": HOST_WALL_CLOCK_SECONDS,
         "order_seed": ORDER_SEED, "order_hash": ORDER_HASH,
         "hints": HINT_SHA256,
         "exit_status_map": EXIT_STATUS_MAP,
         "no_separate_smoke": NO_SEPARATE_SMOKE,
         "pass_claim": PASS_CLAIM,
         "transport": {"provider": LITELLM_PROVIDER,
                       "attempts": TRANSPORT_ATTEMPTS,
                       "retry_knobs": RETRY_KNOBS,
                       "retry_env": RETRY_ENV,
                       "cost_env": COST_ENV,
                       "cost_tracking": COST_TRACKING},
         "scorable": list(SCORABLE),
         "schema": SCHEMA_VERSION}, sort_keys=True).encode()).hexdigest()[:16]


SPEC = _spec.Spec(
    name="f3",
    task_count=TASK_COUNT,
    replicates=REPLICATES,
    arms=ARMS,
    order_seed=ORDER_SEED,
    order_hash=ORDER_HASH,
    protocol_hash=protocol_hash(),
    warning_usd=WARNING_USD,
    no_new_block_usd=NO_NEW_BLOCK_USD,
    absolute_limit_usd=ABSOLUTE_LIMIT_USD,
    host_wall_clock_seconds=HOST_WALL_CLOCK_SECONDS,
)
