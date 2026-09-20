"""C2-H, the registration turned into data (`paper/PREREG_C2H.md`).

Nothing here is a command-line option. Horizons, arm sizes, replicate counts,
the donor cap, the block order and the budget thresholds are the registration;
a flag that could change them is a flag that eventually would.

One structural difference from `c2_protocol.py`: C2's donors were already
frozen, so its 72 specs could be enumerated statically. C2-H acquires its
donors sequentially under §4, so the *rule* is frozen here and the manifest is
materialised only once donors are bound. `manifest_hash()` then pins what was
actually run, and `--resolve-only` proves the rule produces the registered
shape before any donor exists.
"""

from __future__ import annotations

import hashlib
import json

PREREG = "paper/PREREG_C2H.md"

HORIZONS = (16, 24, 28)
"""§5. Held from C2 to stay commensurable. A donor that does not reach a
horizon is ineligible there; it is never moved to a nearby checkpoint."""

ARMS = {"FAIL": {"donors": 4, "replicates": 4},
        "PASS": {"donors": 4, "replicates": 2}}
"""§3. 4x3x4 + 4x3x2 = 72, every cell run."""

DONOR_CAP = 30
"""§4.4. Reaching it without the registered FAIL count is a donor-yield
feasibility stop, not a smaller experiment."""

CONCURRENCY = 1
"""§5. Batched decoding is a serving condition, not a speed knob."""

STEP_LIMIT = lambda h: 250 - h  # noqa: E731

SUBSET_36 = {"FAIL": (0, 1), "PASS": (0,)}
"""§3.1. The nested descriptive subset, by replicate index, defined *before*
any run so it can never be produced by dropping cells afterwards. Completing
only these is a budget-censored run (§6.4), never a smaller success."""

BUDGET = {"no_new_block": 85.0, "stop_stage": 90.0, "absolute": 100.0}
"""§6.2, in USD of cumulative billed spend -- not script wall clock."""

CHECKPOINTS = ("after_setup", "after_donors", "before_block")
"""§6.1. The only moments a cost forecast is re-estimated. A block that has
started runs to completion."""

MODEL = {"id": "Qwen/Qwen3.6-27B-FP8",
         "revision": "e89b16ebf1988b3d6befa7de50abc2d76f26eb09",
         "max_model_len": 131072}
SAMPLING = {"temperature": 0, "seed": None}
SERVING_CONFIG = "inference/configs/model_h2.yaml"
DEP_LOCK = "inference/requirements-vllm.lock.txt"


def expand(donors: list[dict]) -> list[dict]:
    """The 72 specs, from donors bound by the §4 rule.

    `donors` is the ordered, already-selected set: exactly `ARMS[arm]["donors"]`
    entries per arm, each `{"arm", "donor_id", "seed", "run_id"}`, in the seed
    order they arrived. Order is part of the manifest, so a different arrival
    order is a different manifest and says so.
    """
    for arm, spec in ARMS.items():
        got = [d for d in donors if d["arm"] == arm]
        if len(got) != spec["donors"]:
            raise ValueError(f"{arm}: need {spec['donors']} donors, got {len(got)}")
    out = []
    for arm in ("FAIL", "PASS"):
        reps = ARMS[arm]["replicates"]
        for d in [x for x in donors if x["arm"] == arm]:
            for h in HORIZONS:
                for k in range(reps):
                    out.append({
                        "run_id": f"c2h__{arm}__{d['donor_id']}__h{h}__k{k}",
                        "arm": arm, "donor_id": d["donor_id"],
                        "donor_seed": d["seed"], "donor_run_id": d["run_id"],
                        "horizon": h, "replicate": k,
                        "step_limit": STEP_LIMIT(h),
                        "in_subset_36": k in SUBSET_36[arm],
                    })
    if len(out) != total_specs():
        raise ValueError(f"expand produced {len(out)}, registered {total_specs()}")
    return out


def total_specs() -> int:
    return sum(a["donors"] * len(HORIZONS) * a["replicates"] for a in ARMS.values())


def blocks(specs: list[dict]) -> list[dict]:
    """The 24 continuation blocks, in the fixed execution order.

    A block is one (arm, donor, horizon) group of replicates -- the unit §6.1
    says runs to completion once started, so a cost re-estimate can never land
    inside one.

    Order is FAIL before PASS, then donor arrival order, then ascending horizon.
    Fixed here so that a budget stop truncates a *known* sequence: what was run
    is determined by where the stop fell, not by any choice made during the run.
    """
    seen, out = {}, []
    for s in specs:
        seen.setdefault((s["arm"], s["donor_id"], s["horizon"]), []).append(s)
    order = sorted(seen, key=lambda k: (0 if k[0] == "FAIL" else 1,
                                        _donor_pos(specs, k[1]), k[2]))
    for i, key in enumerate(order):
        arm, donor, h = key
        out.append({"index": i, "arm": arm, "donor_id": donor, "horizon": h,
                    "specs": [s["run_id"] for s in seen[key]],
                    "size": len(seen[key])})
    return out


def _donor_pos(specs, donor_id):
    for i, s in enumerate(specs):
        if s["donor_id"] == donor_id:
            return i
    return 1 << 30


def _h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def protocol_hash() -> str:
    """The registration. Changes only if the registered plan changes."""
    return _h({"prereg": PREREG, "horizons": HORIZONS, "arms": ARMS,
               "donor_cap": DONOR_CAP, "concurrency": CONCURRENCY,
               "subset_36": SUBSET_36, "budget": BUDGET,
               "checkpoints": CHECKPOINTS, "model": MODEL,
               "sampling": SAMPLING, "serving_config": SERVING_CONFIG})


def manifest_hash(specs: list[dict]) -> str:
    """What was actually materialised, donors included."""
    return _h([{k: s[k] for k in ("run_id", "arm", "donor_id", "donor_seed",
                                  "horizon", "replicate", "step_limit")}
               for s in specs])


def order_hash(bl: list[dict]) -> str:
    """The execution order, so a truncated run is checkable against the plan."""
    return _h([(b["index"], b["arm"], b["donor_id"], b["horizon"], b["specs"])
               for b in bl])


def subset_36(specs: list[dict]) -> list[dict]:
    return [s for s in specs if s["in_subset_36"]]
