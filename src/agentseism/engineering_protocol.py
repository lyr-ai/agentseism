"""An execution namespace, not a third experiment.

`engineering` exists to answer one question with no research content: can a
single real cell execute end to end, through the public CLI, against the real
backend and the real evaluator, on a real host? That is the thing the pilot
never checked and F3 never reached.

It is deliberately not an experiment, and the distinction is enforced rather
than described:

  * `experimental_evidence: False` is stamped on every artifact it produces,
    so a file carries its own status even after it is copied somewhere else.
  * It has its own `protocol_hash` and `order_hash`, so nothing it writes can
    be mistaken for pilot or F3 evidence.
  * It reads and writes `data/runs/engineering/` only.
  * Exactly one cell. There is no arm to compare against and no replicate, so
    there is nothing here that could be read as a result.

Everything that executes is shared: same runner, same backend, same hints,
same transport, same evaluator, same preflight. Validating a private copy of
the production path would validate nothing.
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

PURPOSE = ("validate that one real cell can execute end-to-end on the real "
           "backend through the public CLI")

TASK = "pytest-dev__pytest-10051"
"""The instance whose image, container behaviour and evaluator output are
already known to work locally. Choosing an unfamiliar one would risk reading a
task problem as a path problem, and this run is only about the path."""

TASK_COUNT = 1
REPLICATES = 1
ARM = "baseline"
ENGINEERING_ARMS = {ARM: ARMS[ARM]}
"""One arm. Two would invite a comparison, and there is nothing here to
compare -- a single execution per arm cannot support one."""

ORDER_SEED = 20260925
ORDER_HASH = "2140f30ac3768b4d"

BILLING_ORIGIN_USD = 16.88
BILLING_ORIGIN_PERIOD = "September 2026"
BILLING_ORIGIN_CURRENCY = "USD"
"""**Not a new origin.** The same frozen figure the paid validation activity is
already anchored to.

Execution identity and billing accounting are different things, and separating
the first must not silently reset the second. Giving `engineering` its own
origin would have made every dollar already spent -- F3's $1.28, the aborted
host, everything since -- disappear from the count, which is a budget reset
wearing a provenance fix as a disguise.

So spend here is still `page total - $16.88`, cumulative across everything
since that reading. It is carried as a constant rather than read out of
`data/runs/f3/run.jsonl`: that log is closed, and a closed record is not a
dependency of new work.
"""

WARNING_USD = 9.0
NO_NEW_BLOCK_USD = 11.0
ABSOLUTE_LIMIT_USD = 13.0
"""Cumulative from the shared origin, **not** marginal for this host.

About $2.94 of that origin was already consumed before this namespace existed,
so thresholds sized for "one cell from scratch" would fire on history rather
than on anything engineering did. These leave roughly one host of headroom
above what is already spent: page totals of $25.88, $27.88 and $29.88."""

HOST_WALL_CLOCK_SECONDS = 10800          # 3 hours


def protocol_hash() -> str:
    return hashlib.sha256(json.dumps(
        {"purpose": PURPOSE, "arms": ENGINEERING_ARMS, "task": TASK,
         "tasks": TASK_COUNT, "replicates": REPLICATES,
         "timeout": RUN_TIMEOUT_SECONDS,
         "budget": [WARNING_USD, NO_NEW_BLOCK_USD, ABSOLUTE_LIMIT_USD],
         "billing_origin": BILLING_ORIGIN_USD,
         "host_wall_clock": HOST_WALL_CLOCK_SECONDS,
         "order_seed": ORDER_SEED, "order_hash": ORDER_HASH,
         "hints": HINT_SHA256, "exit_status_map": EXIT_STATUS_MAP,
         "experimental_evidence": False,
         "transport": {"provider": LITELLM_PROVIDER,
                       "attempts": TRANSPORT_ATTEMPTS,
                       "retry_knobs": RETRY_KNOBS,
                       "retry_env": RETRY_ENV,
                       "cost_env": COST_ENV,
                       "cost_tracking": COST_TRACKING},
         "scorable": list(SCORABLE),
         "schema": SCHEMA_VERSION}, sort_keys=True).encode()).hexdigest()[:16]


SPEC = _spec.Spec(
    name="engineering",
    task_count=TASK_COUNT,
    replicates=REPLICATES,
    arms=ENGINEERING_ARMS,
    order_seed=ORDER_SEED,
    order_hash=ORDER_HASH,
    protocol_hash=protocol_hash(),
    warning_usd=WARNING_USD,
    no_new_block_usd=NO_NEW_BLOCK_USD,
    absolute_limit_usd=ABSOLUTE_LIMIT_USD,
    host_wall_clock_seconds=HOST_WALL_CLOCK_SECONDS,
    experimental_evidence=False,
    registered_task=TASK,
)
