"""The Gate 2 pilot registration, as data (`paper/PREREG_PILOT.md` + P.1, P.2).

Nothing here is a command-line option. Arms, step limits, the recovery-hint
variant, task count, replicates, the run cap, the budget stops and the block
order are the registration; a flag that could change them is a flag that
eventually would.

The order is **regenerated** from the seed at startup and checked against the
frozen hash. A mismatch fails closed rather than warns: an order that differs
from the registered one is a different experiment, whatever produced the
difference.
"""

from __future__ import annotations

import hashlib
import json
import random

PREREG = "paper/PREREG_PILOT.md"

ARMS: dict[str, dict] = {
    "baseline": {"challenge": True, "step_limit": 250, "hint": "full"},
    "M1":       {"challenge": True, "step_limit": 40,  "hint": "full"},
    "M2":       {"challenge": True, "step_limit": 250, "hint": "error_only"},
}
"""Both comparisons are single-axis. M1 vs baseline changes only `step_limit`;
M2 vs baseline changes only `hint`. The challenge is a shared test condition
present in every arm, not a scored mutation."""

TASK_COUNT = 3
REPLICATES = 2
RUN_TIMEOUT_SECONDS = 1200
"""Infrastructure spend protection. **Not** an agent limit: a run stopped here
is `INFRA_TIMEOUT_1200S`, a censored observation, and never M1's effect."""

WARNING_USD = 20.0
NO_NEW_BLOCK_USD = 25.0
ABSOLUTE_LIMIT_USD = 30.0

ORDER_SEED = 20260920
ORDER_HASH = "cfe8856c9c9167b5"
CELLS = TASK_COUNT * len(ARMS) * REPLICATES      # 18

SCHEMA_VERSION = 1


class ProtocolMismatch(RuntimeError):
    """The regenerated plan is not the registered plan."""


def build_order(task_ids: list[str] | None = None) -> list[dict]:
    """The 18 cells, in the registered sequence.

    Interleaved rather than all-baseline-first, so drift over the session does
    not align with an arm. Generated from the seed over the whole registered
    arm set — never by deleting an arm from an older order.
    """
    names = task_ids or [f"task_{i + 1}" for i in range(TASK_COUNT)]
    if len(names) != TASK_COUNT:
        raise ProtocolMismatch(f"need {TASK_COUNT} tasks, got {len(names)}")
    rng = random.Random(ORDER_SEED)
    blocks = []
    for rep in range(REPLICATES):
        for i in range(TASK_COUNT):
            arms = list(ARMS)
            rng.shuffle(arms)
            blocks.append({"replicate": rep, "task": names[i], "arms": arms})
    return blocks


def order_hash(blocks: list[dict]) -> str:
    """Over positions, not task names, so the hash is fixed before the draw.

    Task ids are drawn mechanically on the instance and cannot be known when
    the order is registered. Hashing them would make the frozen hash
    unverifiable, so the hash covers replicate index, task *position* and arm
    sequence — the part the registration actually fixes.
    """
    canonical = [{"replicate": b["replicate"], "task": f"task_{i % TASK_COUNT + 1}",
                  "arms": b["arms"]} for i, b in enumerate(blocks)]
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:16]


def cells(blocks: list[dict]) -> list[dict]:
    """Flattened execution order: one dict per run, with its index."""
    out = []
    for b in blocks:
        for arm in b["arms"]:
            out.append({"order_index": len(out), "replicate": b["replicate"],
                        "task": b["task"], "arm": arm, **ARMS[arm]})
    return out


def verify(task_ids: list[str] | None = None) -> list[dict]:
    """Regenerate and check. Fails closed."""
    blocks = build_order(task_ids)
    got = order_hash(blocks)
    if got != ORDER_HASH:
        raise ProtocolMismatch(
            f"order hash {got} != registered {ORDER_HASH}; the regenerated "
            "plan is not the registered plan")
    c = cells(blocks)
    if len(c) != CELLS:
        raise ProtocolMismatch(f"{len(c)} cells, registered {CELLS}")
    return c


def protocol_hash() -> str:
    return hashlib.sha256(json.dumps(
        {"prereg": PREREG, "arms": ARMS, "tasks": TASK_COUNT,
         "replicates": REPLICATES, "timeout": RUN_TIMEOUT_SECONDS,
         "budget": [WARNING_USD, NO_NEW_BLOCK_USD, ABSOLUTE_LIMIT_USD],
         "order_seed": ORDER_SEED, "order_hash": ORDER_HASH,
         "schema": SCHEMA_VERSION}, sort_keys=True).encode()).hexdigest()[:16]


# ── termination codes: one meaning each ──
COMPLETED = "COMPLETED"
STEP_LIMIT_REACHED = "STEP_LIMIT_REACHED"
"""Part of M1's mechanism. A mutation outcome."""
INFRA_TIMEOUT_1200S = "INFRA_TIMEOUT_1200S"
"""Cost control. A censored observation, never M1's effect."""
INVALID = "INVALID"
"""Execution or scoring fault."""
NOT_ELIGIBLE = "NOT_ELIGIBLE"
"""No first valid tool call, so the challenge never fired. Affects only the
recovery denominator — never counted as a recovery failure."""

TERMINATIONS = (COMPLETED, STEP_LIMIT_REACHED, INFRA_TIMEOUT_1200S, INVALID,
                NOT_ELIGIBLE)

SCORABLE = (COMPLETED, STEP_LIMIT_REACHED)
"""What may enter a task-success rate. A censored or invalid run may not: the
budget cap must never be able to manufacture a regression."""

RECOVERY_DENOMINATOR = (COMPLETED, STEP_LIMIT_REACHED)
"""`NOT_ELIGIBLE` is excluded by construction."""
