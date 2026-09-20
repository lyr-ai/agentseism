"""C2-H budget state machine and append-only run log (`PREREG_C2H.md` §6).

Two things this module refuses to do.

**It does not read the billing page.** A runner cannot reliably scrape Lambda's
billing, and an estimate presented as a bill is how a $100 ceiling becomes a
$140 invoice. Cumulative spend enters only by explicit human entry, stamped
with when it was entered and by whom. An estimate may be *logged alongside* a
reading, never instead of one.

**It does not re-estimate continuously.** §6.1 fixes exactly three moments:
after setup, after donor acquisition, and before each block. A block that has
started runs to completion, so no threshold can fire inside one.
"""

from __future__ import annotations

import getpass
import json
import os
import platform
import socket
import subprocess
import time
from pathlib import Path

from experiments.coding import c2h_protocol as P


class BudgetStop(RuntimeError):
    """A registered stop fired. Carries the state for the report."""

    def __init__(self, kind: str, detail: str, state: dict):
        self.kind, self.detail, self.state = kind, detail, state
        super().__init__(f"{kind}: {detail}")


def session_fingerprint() -> dict:
    """Identity of this instance, this boot and this serving process.

    C2-H is defined as donors and continuations produced in one session on one
    instance (§1). Resume across machines is not a degraded run, it is a
    different experiment, so the fingerprint is checked rather than trusted.
    """
    def read(path, default=""):
        try:
            return Path(path).read_text().strip()
        except Exception:  # noqa: BLE001
            return default

    def gpu():
        try:
            return subprocess.run(
                ["nvidia-smi", "--query-gpu=uuid,name,driver_version",
                 "--format=csv,noheader"],
                capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:  # noqa: BLE001
            return "unavailable"

    return {
        "hostname": socket.gethostname(),
        "boot_id": read("/proc/sys/kernel/random/boot_id"),
        "machine": platform.machine(),
        "gpu": gpu(),
        "vllm_pid": _vllm_pid(),
    }


def _vllm_pid() -> str:
    try:
        out = subprocess.run(["pgrep", "-f", "vllm.entrypoints.openai.api_server"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        return out[0] if out else ""
    except Exception:  # noqa: BLE001
        return ""


class RunLog:
    """Append-only JSONL. Every request, block, billing reading and fingerprint.

    Append-only because the log is the evidence that the registered stops were
    applied as written; a log that can be rewritten proves nothing.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, kind: str, **fields) -> dict:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "kind": kind, **fields}
        with self.path.open("a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        return rec

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def last_billing(self) -> dict | None:
        r = [x for x in self.read() if x["kind"] == "billing_reading"]
        return r[-1] if r else None


class Budget:
    """The $85 / $90 / $100 state machine of §6.2."""

    def __init__(self, log: RunLog):
        self.log = log

    def record_reading(self, usd: float, source: str = "manual",
                       note: str = "") -> dict:
        """Enter a cumulative spend read from the billing page.

        `source` is recorded verbatim. Anything other than "manual" is treated
        as an estimate by `check`, never as a bill.
        """
        return self.log.append("billing_reading", usd=float(usd), source=source,
                               operator=getpass.getuser(), note=note,
                               entered_by_env=os.environ.get("C2H_OPERATOR", ""))

    def check(self, checkpoint: str, block_index: int | None = None) -> dict:
        """Evaluate the registered thresholds. Only at a registered checkpoint."""
        if checkpoint not in P.CHECKPOINTS:
            raise ValueError(f"{checkpoint!r} is not one of {P.CHECKPOINTS}; "
                             "§6.1 fixes when a forecast is re-estimated")
        last = self.log.last_billing()
        if last is None:
            raise BudgetStop("no_billing_reading",
                             "no cumulative spend has been entered; §6.2 is a "
                             "billed-spend rule and cannot run on estimates",
                             {"checkpoint": checkpoint})
        usd, stale = last["usd"], last["source"] != "manual"
        state = {"checkpoint": checkpoint, "block_index": block_index,
                 "usd": usd, "reading_ts": last["ts"], "estimate_only": stale}

        if usd >= P.BUDGET["absolute"]:
            self.log.append("budget_stop", reason="absolute", **state)
            raise BudgetStop("absolute", f"${usd:.2f} >= ${P.BUDGET['absolute']}", state)
        if usd >= P.BUDGET["stop_stage"]:
            self.log.append("budget_stop", reason="stop_stage", **state)
            raise BudgetStop("stop_stage",
                             f"${usd:.2f} >= ${P.BUDGET['stop_stage']}: stop after "
                             "the current stage, retrieve artifacts, terminate", state)
        if usd >= P.BUDGET["no_new_block"] and checkpoint == "before_block":
            self.log.append("budget_stop", reason="no_new_block", **state)
            raise BudgetStop("no_new_block",
                             f"${usd:.2f} >= ${P.BUDGET['no_new_block']}: start no "
                             "new block", state)
        self.log.append("budget_ok", **state)
        return state
