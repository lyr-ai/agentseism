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
import re

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

# ── task selection (amendment P.3) ──
EXCLUDED_INSTANCES = ("pytest-dev__pytest-10051",)
"""It produced the frozen donors and both counterexamples. Reusing it would let
prior familiarity into a set meant to test the method."""

TASK_SELECTION = {
    "rule": "ascending_id_first_pullable_per_distinct_repository",
    "version": 2,
    "universe": "SWE-bench/SWE-bench_Verified:test",
    "wanted": TASK_COUNT,
    "exclude": list(EXCLUDED_INSTANCES),
    "repository_key": "instance id with the trailing -<number> removed",
    "skip_reasons": ["excluded_registered", "duplicate_repository", "pull_failed"],
    "exhausted": "fail_closed",
}
"""Version 1 was *first three that pull*, and on this universe it draws three
`astropy__astropy` instances: the ids sort ascending and one repository holds
enough of the head of the list to fill the draw. Three scenarios from one
repository are not three independent scenarios in the sense the pilot's
extrapolation assumes.

This was found before launch and with no pilot outcome in existence, so it is a
design defect in the sampling rule, not a result-driven change. Amendment P.3
records it.

**Selection is part of the experiment**, so `TASK_SELECTION` is inside
`protocol_hash` and the hash moves. `ORDER_HASH` does not: the order binds the
*positions* `task_1..task_3`, never the ids that fill them."""


def repository_of(instance_id: str) -> str:
    """`astropy__astropy-12907` -> `astropy__astropy`.

    Raises rather than guessing. An id this cannot parse means the universe is
    not the one the rule was registered against, and silently treating the
    whole id as a repository would make every such instance look distinct --
    which is the one failure mode this rule exists to prevent.
    """
    m = re.fullmatch(r"(?P<repo>.+)-\d+", instance_id)
    if not m:
        raise ValueError(
            f"{instance_id!r} is not <repository>-<number>; the candidate "
            "universe is not the registered one")
    return m.group("repo")


def select_tasks(candidates, pull, wanted: int = TASK_COUNT,
                 exclude=EXCLUDED_INSTANCES, rows: list | None = None):
    """The registered draw. Returns `(drawn, rows)`; every candidate examined
    appears in `rows` with why it was skipped.

    `pull` is injected so the rule is testable without Docker, and so this
    function can be read without reference to how an image is fetched.

    The repository check runs **before** the pull, and that ordering is an
    efficiency decision with no effect on the result: a candidate whose
    repository is already represented is never selected under either ordering,
    so the drawn set is identical. Pulling first would fetch every remaining
    instance of an already-selected repository -- on this universe upwards of a
    hundred multi-gigabyte images -- only to discard them.

    Exhaustion is a stop, not a relaxation: if the candidates run out before
    `wanted` distinct repositories are found, the caller gets `ProtocolMismatch`
    and no draw. Pass `rows` -- a list the caller owns -- to keep the record of
    a draw that failed: raising with the reasons still inside this function
    would throw away exactly the evidence that says why it failed.
    """
    drawn: list[str] = []
    repos: set[str] = set()
    rows = [] if rows is None else rows
    for iid in candidates:
        if len(drawn) == wanted:
            break
        if iid in exclude:
            rows.append((iid, "excluded_registered"))
            continue
        repo = repository_of(iid)
        if repo in repos:
            rows.append((iid, "duplicate_repository"))
            continue
        if not pull(iid):
            rows.append((iid, "pull_failed"))
            continue
        rows.append((iid, "selected"))
        drawn.append(iid)
        repos.add(repo)
    if len(drawn) != wanted:
        raise ProtocolMismatch(
            f"{len(drawn)} of {wanted} distinct repositories found in "
            f"{len(rows)} candidates examined; the rule is not relaxed to "
            "finish the draw")
    return drawn, rows


# ── the recovery hint (amendment P.5) ──
UPSTREAM_HINT_SOURCE = {
    "package": "mini-swe-agent==2.4.6",
    "path": "minisweagent/config/benchmarks/swebench.yaml",
    "key": "model.format_error_template",
    "file_sha256": "9a9c86ac10428b86b932c972b15fefc2f7b6e92230bac5ebdc47e83232a8315e",
}
"""Where `full` comes from. The package is pinned in
`inference/requirements-eval.lock.txt`, so the upstream side is frozen by the
lock and this records which bytes were read."""

HINT_TRANSFORM = (
    "In the `else` branch keep `Tool call error:` and the <error> block; "
    "delete from `Here is general guidance on how to submit correct "
    "toolcalls:` to the end of that branch. The `finish_reason` branch is "
    "kept verbatim."
)
"""How `error_only` was derived. The rule is recorded **and** both results are
frozen byte-for-byte below: a rule alone would let a different upstream
version produce a different mutation under the same registration."""

HINTS: dict[str, str] = {
    "full": '{% if finish_reason is defined and (finish_reason == "length" or (finish_reason == "tool_calls" and not has_tool_calls)) -%}\nYour previous response reached the output token limit (finish_reason={{ finish_reason }}) before you produced a tool call, so it was cut off. Respond more concisely and finish with exactly one bash tool call. If you need to think more, do so briefly.\n{%- else -%}\nTool call error:\n\n<error>\n{{error}}\n</error>\n\nHere is general guidance on how to submit correct toolcalls:\n\nEvery response needs to use the \'bash\' tool at least once to execute commands.\n\nCall the bash tool with your command as the argument:\n- Tool: bash\n- Arguments: {"command": "your_command_here"}\n\nIf you have completed your assignment, please consult the first message about how to\nsubmit your solution (you will not be able to continue working on this task after that).\n{%- endif %}\n',
    "error_only": '{% if finish_reason is defined and (finish_reason == "length" or (finish_reason == "tool_calls" and not has_tool_calls)) -%}\nYour previous response reached the output token limit (finish_reason={{ finish_reason }}) before you produced a tool call, so it was cut off. Respond more concisely and finish with exactly one bash tool call. If you need to think more, do so briefly.\n{%- else -%}\nTool call error:\n\n<error>\n{{error}}\n</error>\n{%- endif %}\n',
}
"""The two templates, verbatim.

`full` is the complete upstream guidance: what went wrong **and** how to
recover. `error_only` is the same message with the recovery instructions
removed: what went wrong, and nothing about how to fix it. Everything else --
the `finish_reason` branch, the error block, the surrounding structure -- is
identical, so baseline and M2 differ on one axis.

**Estimand, deliberately narrow.** Under the registered synthetic
malformed-call challenge, compare recovery when the agent receives the complete
upstream recovery guidance against the error content alone. This does not
generalise to "removing error handling reduces agent success", and it estimates
nothing about how often malformed calls occur naturally."""

HINT_SHA256 = {
    "full": "0f35cfbd448dd46e17e80b571d346256d4a75cd5ceffafc5c0d088ed0e1c0d9a",
    "error_only": "450d5d015b1518c7903a90b6c1fcba6a76923c32582b9448b8300a7a29da428c",
}


def verify_hints() -> None:
    """`full` must still be byte-identical to the pinned upstream.

    Checked at startup. A newer mini-swe-agent that reworded the template is a
    different experiment, and adapting the frozen text to it would silently
    change what M2 removes. Fails closed; it does not adapt.
    """
    for name, text in HINTS.items():
        got = hashlib.sha256(text.encode()).hexdigest()
        if got != HINT_SHA256[name]:
            raise ProtocolMismatch(
                f"HINTS[{name!r}] hashes to {got}, registered "
                f"{HINT_SHA256[name]}")
    try:
        import os as _os

        import minisweagent as _m
        import yaml as _yaml
        path = _os.path.join(_os.path.dirname(_m.__file__),
                             UPSTREAM_HINT_SOURCE["path"].split("/", 1)[1])
        upstream = _yaml.safe_load(open(path))["model"]["format_error_template"]
    except Exception as e:                      # noqa: BLE001
        raise ProtocolMismatch(
            f"cannot read the pinned upstream template: {e}") from e
    if upstream != HINTS["full"]:
        raise ProtocolMismatch(
            "the installed mini-swe-agent's format_error_template differs from "
            "the registered `full`. This is a different experiment; the frozen "
            "text is not adapted to it")


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
         # The hint text is the M2 mutation; a different string is a
         # different experiment (amendment P.5).
         "hints": HINT_SHA256,
         # How the tasks are drawn is part of the design, so changing the rule
         # has to move the hash.
         "task_selection": TASK_SELECTION,
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
