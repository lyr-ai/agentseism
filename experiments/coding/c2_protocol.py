"""The frozen C2 protocol, as data.

Everything the runner is allowed to vary lives here and nowhere else. There are
no command-line options for horizons, trajectories or replication counts,
because the registration in `paper/PREREG_C2_RECOVERABILITY.md` fixed them and a
flag that can change them is a flag that will.

`protocol_hash()` goes into every result directory so that a set of outcomes can
never be orphaned from the protocol that produced it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# ── frozen by paper/PREREG_C2_RECOVERABILITY.md ───────────────────────────────

TASK = "pytest-dev__pytest-10051"
IMAGE = "swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-10051:latest"

HORIZONS = [16, 24, 28]
"""20 was dropped: the C1 effect table shows it carrying no information between
16 and 24, and it would have cost a quarter of the batch."""

FAIL_RUNS = ["r4", "A_3", "A_6", "B_0"]
PASS_RUNS = ["r0", "r1", "r2", "r3"]

REPLICATES = {"FAIL": 4, "PASS": 2}
"""The control is deliberately smaller. It is sized to catch an obvious
regression or a non-specific effect, not to estimate its own curve."""

STEP_LIMIT_BASE = 250
MODEL = {"id": "Qwen/Qwen3.6-27B-FP8",
         "revision": "e89b16ebf1988b3d6befa7de50abc2d76f26eb09",
         "max_model_len": 131072}
SAMPLING = {"temperature": 0, "seed": None}
"""Seed stays null. Variation is the object of study, not a nuisance."""

# Where each trajectory lives, and the donor fork step that makes its archive
# step numbering local rather than absolute.
LOCATION = {
    "r0": ("h2_phase_a1", f"{TASK}__r0", 0),
    "r1": ("h2_phase_a1", f"{TASK}__r1", 0),
    "r2": ("h2_phase_a1", f"{TASK}__r2", 0),
    "r3": ("h2_phase_a1", f"{TASK}__r3", 0),
    "r4": ("h2_phase_a1", f"{TASK}__r4", 0),
    "A_3": ("h2_phase_b", "A_3", 8),
    "A_6": ("h2_phase_b", "A_6", 8),
    "B_0": ("h2_phase_b", "B_0", 10),
}


def protocol_hash() -> str:
    payload = {"task": TASK, "image": IMAGE, "horizons": HORIZONS,
               "fail_runs": FAIL_RUNS, "pass_runs": PASS_RUNS,
               "replicates": REPLICATES, "step_limit_base": STEP_LIMIT_BASE,
               "model": MODEL, "sampling": SAMPLING}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def expand() -> list[dict]:
    """The full execution plan, deterministic and in a fixed order."""
    specs = []
    for arm, runs in (("FAIL", FAIL_RUNS), ("PASS", PASS_RUNS)):
        for source in runs:
            batch, name, donor_fork = LOCATION[source]
            for horizon in HORIZONS:
                for replicate in range(REPLICATES[arm]):
                    specs.append({
                        "run_id": f"c2__{arm}__{source}__h{horizon}__k{replicate}",
                        "arm": arm,
                        "source_run_id": source,
                        "source_batch": batch,
                        "source_name": name,
                        "horizon": horizon,
                        # Archives of replayed continuations number their steps
                        # locally; the absolute horizon has to be translated.
                        "archive_step": horizon - donor_fork,
                        "donor_fork_step": donor_fork,
                        "replicate": replicate,
                        "step_limit": STEP_LIMIT_BASE - horizon,
                        "sampling_seed": SAMPLING["seed"],
                    })
    return specs
