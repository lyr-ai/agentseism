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

Two rules follow from those and are enforced here rather than remembered:

*Each block needs its own reading.* A reading is consumed by the check that
authorises a block, so the next block cannot reuse it. Otherwise one early
reading would authorise twenty-four blocks and the ceiling would be decorative.

*An estimate never authorises anything.* It is logged, and it warns, and it is
refused as authority for a checkpoint or a block start.

**Thresholds apply to this experiment's spend, not to the account's history.**
The billing page shows a cumulative account total, and this account already
carries the first H100's Gate 9 run. Comparing that number against $85 would
have made C2-H's ceiling depend on money spent before it existed. A baseline is
frozen before donor 0 and every later reading is the raw page total; the state
machine judges the difference:

    c2h_spend = current_total - billing_baseline

The operator enters what the page says. They never enter "what I think this run
cost" -- a delta typed by hand is an estimate wearing a bill's clothes.
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
    """The three-threshold state machine.

    Thresholds are **injected**, not imported. They were hardwired to C2-H's
    $85/$90/$100, which would have silently run the pilot — registered at
    $20/$25/$30 — under the wrong ceiling. A budget rule that belongs to one
    experiment must not be the default for another.
    """

    def __init__(self, log: RunLog, thresholds: dict | None = None):
        self.log = log
        self.thresholds = dict(thresholds or P.BUDGET)
        missing = {"no_new_block", "stop_stage", "absolute"} - set(self.thresholds)
        if missing:
            raise ValueError(f"budget thresholds missing {sorted(missing)}")

    def record_baseline(self, current_total: float, billing_period: str,
                        currency: str = "USD", note: str = "") -> dict:
        """Freeze the origin: what the account had already spent before C2-H.

        Entered once, before donor 0. `billing_period` and `currency` are
        recorded so that a page showing a different period or currency later is
        caught rather than silently differenced against the wrong origin.
        """
        prior = self.baseline()
        if prior is not None:
            raise BudgetStop("baseline_already_set",
                             f"a baseline of ${prior['current_total']:.2f} was "
                             f"frozen at {prior['ts']}; it is the origin and is "
                             "not re-entered", prior)
        return self.log.append("billing_baseline",
                               current_total=float(current_total),
                               billing_period=str(billing_period),
                               currency=str(currency),
                               operator=getpass.getuser(), note=note)

    def baseline(self) -> dict | None:
        r = [x for x in self.log.read() if x["kind"] == "billing_baseline"]
        return r[0] if r else None

    def record_reading(self, usd: float, source: str = "manual",
                       note: str = "", billing_period: str | None = None,
                       currency: str | None = None) -> dict:
        """Enter a cumulative spend read from the billing page.

        `source` is recorded verbatim. Anything other than "manual" is an
        estimate: it is logged and it warns, and `check` refuses to be
        authorised by it.
        """
        base = self.baseline()
        seq = 1 + max([r.get("seq", 0) for r in self.log.read()
                       if r["kind"] == "billing_reading"] or [0])
        return self.log.append(
            "billing_reading", seq=seq, current_total=float(usd),
            billing_period=billing_period or (base or {}).get("billing_period"),
            currency=currency or (base or {}).get("currency", "USD"),
            source=source, operator=getpass.getuser(), note=note,
            entered_by_env=os.environ.get("C2H_OPERATOR", ""))

    def _consumed_seq(self) -> int:
        return max([r.get("consumed_seq", 0) for r in self.log.read()
                    if r["kind"] == "budget_ok"] or [0])

    def check(self, checkpoint: str, block_index: int | None = None) -> dict:
        """Evaluate the registered thresholds. Only at a registered checkpoint."""
        if checkpoint not in P.CHECKPOINTS:
            raise ValueError(f"{checkpoint!r} is not one of {P.CHECKPOINTS}; "
                             "§6.1 fixes when a forecast is re-estimated")
        base = self.baseline()
        if base is None:
            raise BudgetStop("no_billing_baseline",
                             "no billing baseline is frozen; C2-H's thresholds "
                             "apply to its own spend, and without an origin the "
                             "account's history would be charged to it",
                             {"checkpoint": checkpoint})
        last = self.log.last_billing()
        if last is None:
            raise BudgetStop("no_billing_reading",
                             "no cumulative spend has been entered; §6.2 is a "
                             "billed-spend rule and cannot run on estimates",
                             {"checkpoint": checkpoint})

        total, stale = last["current_total"], last["source"] != "manual"
        # The page can only go up, and only within one period and currency.
        if last.get("billing_period") != base["billing_period"]:
            raise BudgetStop("billing_period_changed",
                             f"reading period {last.get('billing_period')!r} != "
                             f"baseline period {base['billing_period']!r}; the "
                             "difference would not be this experiment's spend",
                             {"baseline": base, "reading": last})
        if last.get("currency") != base.get("currency"):
            raise BudgetStop("currency_changed",
                             f"reading currency {last.get('currency')!r} != "
                             f"baseline {base.get('currency')!r}",
                             {"baseline": base, "reading": last})
        if total < base["current_total"]:
            raise BudgetStop("reading_below_baseline",
                             f"${total:.2f} is below the frozen baseline of "
                             f"${base['current_total']:.2f}; a cumulative total "
                             "cannot fall, so one of the two is wrong",
                             {"baseline": base, "reading": last})

        usd = round(total - base["current_total"], 2)     # this run's spend
        state = {"checkpoint": checkpoint, "block_index": block_index,
                 "usd": usd, "current_total": total,
                 "billing_baseline": base["current_total"],
                 "billing_period": base["billing_period"],
                 "currency": base.get("currency", "USD"),
                 "reading_ts": last["ts"], "estimate_only": stale,
                 "reading_seq": last.get("seq", 0)}

        # An estimate is information, never authority.
        if stale:
            self.log.append("budget_refused", reason="estimate_only", **state)
            raise BudgetStop("estimate_only",
                             f"the latest reading (total ${total:.2f}) has source "
                             f"{last['source']!r}; only a manual billing-page "
                             "reading authorises a checkpoint or a block",
                             state)

        # One reading authorises one block. Reusing it would make 24 blocks run
        # on a single early number.
        if checkpoint == "before_block" and last.get("seq", 0) <= self._consumed_seq():
            self.log.append("budget_refused", reason="stale_reading", **state)
            raise BudgetStop("stale_reading",
                             f"reading #{last.get('seq', 0)} already authorised a "
                             "block; enter a fresh cumulative spend before the next",
                             state)

        if usd >= self.thresholds["absolute"]:
            self.log.append("budget_stop", reason="absolute", **state)
            raise BudgetStop("absolute", f"this run has spent ${usd:.2f} (total ${total:.2f} - baseline "
                             f"${base['current_total']:.2f}) >= ${self.thresholds['absolute']}", state)
        if usd >= self.thresholds["stop_stage"]:
            self.log.append("budget_stop", reason="stop_stage", **state)
            raise BudgetStop("stop_stage",
                             f"this run has spent ${usd:.2f} (total ${total:.2f} - baseline "
                             f"${base['current_total']:.2f}) >= ${self.thresholds['stop_stage']}: stop after "
                             "the current stage, retrieve artifacts, terminate", state)
        if usd >= self.thresholds["no_new_block"] and checkpoint == "before_block":
            self.log.append("budget_stop", reason="no_new_block", **state)
            raise BudgetStop("no_new_block",
                             f"this run has spent ${usd:.2f} (total ${total:.2f} - baseline "
                             f"${base['current_total']:.2f}) >= ${self.thresholds['no_new_block']}: start no "
                             "new block", state)
        self.log.append("budget_ok", consumed_seq=state["reading_seq"], **state)
        return state


def write_atomic(path: Path, data: str) -> str:
    """Write, fsync, rename. Returns the SHA-256 of what landed.

    An interrupted write must not leave a file that looks complete. A partial
    JSON that happens to parse is worse than no file, because the next reader
    treats it as an artifact.
    """
    import hashlib
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    digest = hashlib.sha256(data.encode()).hexdigest()
    Path(str(path) + ".sha256").write_text(f"{digest}  {path.name}\n")
    return digest
