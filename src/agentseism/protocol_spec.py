"""What distinguishes one experiment from another, separated from what does not.

`pilot_protocol` grew as a single module because there was a single experiment,
and every consumer reached for it as `import pilot_protocol as P`. That is why
`pilot.py` stamped `protocol_hash` and `order_hash` from module globals: there
was no other place for them to come from. Running a second experiment on that
code would have branded its evidence with the first experiment's identity.

The split is by **what a second experiment would have to change**, not by
subject area:

  * **Spec** -- task count, replicates, the order and its seed, the budget
    thresholds, the registered `protocol_hash`. Injected.
  * **Mechanism** -- arms, hint texts, transport policy, retry and cost env,
    exit-status mapping, termination vocabulary, the run cap. Shared, and left
    exactly where it was.

The mechanism is not experiment-specific here because F3 deliberately reuses it
verbatim: the mechanism is the thing F3 tests. An experiment that changed a
hint or the transport would be changing the subject, and would need more than a
new Spec.

The alternative -- copying the runner -- was rejected. Two runners drift, and
the drift stays invisible until one of them produces evidence the other cannot.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random


class ProtocolMismatch(RuntimeError):
    """The regenerated plan is not the registered plan."""


@dataclasses.dataclass(frozen=True)
class Spec:
    """One experiment's identity and design, frozen at registration.

    `protocol_hash` is supplied by the owning module rather than computed here.
    Each experiment hashes the values *it* registered, and a shared function
    would have to hash a union of them -- which would move the pilot's frozen
    `b7af66ca3ab783ab` the moment F3 added a field.
    """

    name: str
    task_count: int
    replicates: int
    arms: dict
    order_seed: int
    order_hash: str
    protocol_hash: str
    warning_usd: float
    no_new_block_usd: float
    absolute_limit_usd: float
    host_wall_clock_seconds: int | None = None

    @property
    def cell_count(self) -> int:
        return self.task_count * len(self.arms) * self.replicates

    @property
    def thresholds(self) -> dict:
        """The registered stops, mapped onto the budget machine's four slots.

        `stop_stage` is unreachable rather than aliased to `no_new_block`:
        aliasing would turn "do not start another block" into "abandon the
        block you are in", which is stricter than anything registered and
        would truncate work already paid for.
        """
        return {"warning": self.warning_usd,
                "no_new_block": self.no_new_block_usd,
                "stop_stage": float("inf"),
                "absolute": self.absolute_limit_usd}

    def build_order(self, task_ids: list[str] | None = None) -> list[dict]:
        """The blocks, in the registered sequence.

        Interleaved rather than all-baseline-first, so drift over the session
        does not align with an arm. Generated from the seed over the whole
        registered arm set -- never by deleting an arm from an older order.
        """
        names = task_ids or [f"task_{i + 1}" for i in range(self.task_count)]
        if len(names) != self.task_count:
            raise ProtocolMismatch(
                f"need {self.task_count} tasks, got {len(names)}")
        rng = random.Random(self.order_seed)
        blocks = []
        for rep in range(self.replicates):
            for i in range(self.task_count):
                arms = list(self.arms)
                rng.shuffle(arms)
                blocks.append({"replicate": rep, "task": names[i],
                               "arms": arms})
        return blocks

    def compute_order_hash(self, blocks: list[dict]) -> str:
        """Over positions, not task names, so the hash is fixed before the draw.

        Task ids are drawn mechanically on the instance and cannot be known
        when the order is registered. Hashing them would make the frozen hash
        unverifiable, so the hash covers replicate index, task *position* and
        arm sequence -- the part the registration actually fixes.
        """
        canonical = [{"replicate": b["replicate"],
                      "task": f"task_{i % self.task_count + 1}",
                      "arms": b["arms"]} for i, b in enumerate(blocks)]
        return hashlib.sha256(
            json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:16]

    def cells(self, blocks: list[dict]) -> list[dict]:
        """Flattened execution order: one dict per run, with its index."""
        out: list[dict] = []
        for b in blocks:
            for arm in b["arms"]:
                out.append({"order_index": len(out), "replicate": b["replicate"],
                            "task": b["task"], "arm": arm, **self.arms[arm]})
        return out

    def verify(self, task_ids: list[str] | None = None) -> list[dict]:
        """Regenerate and check. Fails closed."""
        blocks = self.build_order(task_ids)
        got = self.compute_order_hash(blocks)
        if got != self.order_hash:
            raise ProtocolMismatch(
                f"order hash {got} != registered {self.order_hash}; the "
                "regenerated plan is not the registered plan")
        c = self.cells(blocks)
        if len(c) != self.cell_count:
            raise ProtocolMismatch(
                f"{len(c)} cells, registered {self.cell_count}")
        return c
