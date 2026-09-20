"""Execute C2-H, or prove it could be executed (`paper/PREREG_C2H.md`).

    --resolve-only   verify the plan, the hashes, the budget logic and the
                     artifact layout. **No vLLM, no model load, no request.**
    (default)        acquire donors, then run the 24 blocks in the fixed order.

The runner executes frozen rules; it decides nothing. Horizons, arm sizes,
replicate counts, the donor cap, the block order and the budget thresholds come
from `c2h_protocol.py`.

**Fail closed.** Resume is permitted only on the same instance, the same boot
and the same serving process that produced the existing artifacts. C2-H is
defined as donors and continuations from one session on one host (§1); a run
reassembled across instances is not a degraded C2-H, it is a different
experiment, and the runner refuses rather than annotates.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# The registered run environment, set here rather than inherited from a shell;
# see the same note in run_c2.py.
import os  # noqa: E402
os.environ.setdefault("MSWEA_COST_TRACKING", "ignore_errors")

from experiments.coding import c2h_protocol as P  # noqa: E402
from experiments.coding.c2h_budget import (  # noqa: E402
    Budget, BudgetStop, RunLog, session_fingerprint, write_atomic,
)


class FailClosed(RuntimeError):
    pass


def bind_session(log: RunLog, fp: dict) -> None:
    """Record this session, or refuse to continue someone else's."""
    prior = [r for r in log.read() if r["kind"] == "session"]
    if not prior:
        log.append("session", fingerprint=fp, protocol_hash=P.protocol_hash())
        return
    old = prior[0]["fingerprint"]
    differing = [k for k in ("hostname", "boot_id", "machine", "gpu", "vllm_pid")
                 if old.get(k) != fp.get(k)]
    if differing:
        raise FailClosed(
            "refusing to resume: this is not the session that produced the "
            f"existing artifacts (differs on {', '.join(differing)}). C2-H is "
            "one session on one instance with one serving process; a run "
            "reassembled across instances is a different experiment.")
    if prior[0]["protocol_hash"] != P.protocol_hash():
        raise FailClosed("refusing to resume: the protocol hash changed since "
                         "these artifacts were written")


def acquire_donors(log: RunLog, budget: Budget, generate) -> list[dict]:
    """§4. Fixed seed order, label immediately, earliest qualifying, cap 30."""
    need = {a: P.ARMS[a]["donors"] for a in P.ARMS}
    held: dict[str, list[dict]] = {"FAIL": [], "PASS": []}
    for seed in range(P.DONOR_CAP):
        if all(len(held[a]) >= need[a] for a in need):
            break
        run_id = f"c2h_donor_{seed:02d}"
        label = generate(seed, run_id)          # frozen checker's verdict
        log.append("donor", seed=seed, run_id=run_id, label=label,
                   held={a: len(held[a]) for a in held})
        if label in held and len(held[label]) < need[label]:
            held[label].append({"arm": label, "donor_id": run_id,
                                "seed": seed, "run_id": run_id})
    short = {a: need[a] - len(held[a]) for a in need if len(held[a]) < need[a]}
    if short:
        log.append("donor_yield_stop", short=short, generated=seed + 1)
        raise BudgetStop("donor_yield_feasibility_stop",
                         f"cap {P.DONOR_CAP} reached without {short}; no "
                         "continuations run, and this is not a recoverability "
                         "verdict", {"short": short})
    return held["FAIL"] + held["PASS"]


def freeze_manifest(log: RunLog, out: Path, donors: list[dict]) -> dict:
    """Materialise and pin the manifest once donors are bound (§3, §4.6).

    After this, the plan is the plan. A later run whose donors, arrival order
    or specs differ produces a different manifest hash and is refused, rather
    than quietly executing a second experiment into the first one's directory.
    """
    pl = plan(donors)
    prior = [r for r in log.read() if r["kind"] == "manifest_frozen"]
    if prior:
        old = prior[0]
        if (old["manifest_hash"], old["order_hash"]) != (pl["manifest_hash"],
                                                         pl["order_hash"]):
            raise FailClosed(
                "refusing to continue: the manifest changed after it was frozen "
                f"(manifest {old['manifest_hash']} -> {pl['manifest_hash']}, "
                f"order {old['order_hash']} -> {pl['order_hash']})")
        return pl
    digest = write_atomic(out / "manifest.json", json.dumps(
        {k: pl[k] for k in ("protocol_hash", "manifest_hash", "order_hash")}
        | {"donors": donors, "specs": pl["specs"], "blocks": pl["blocks"]},
        indent=2, sort_keys=True))
    log.append("manifest_frozen", protocol_hash=pl["protocol_hash"],
               manifest_hash=pl["manifest_hash"], order_hash=pl["order_hash"],
               file_sha256=digest, n_specs=len(pl["specs"]),
               n_blocks=len(pl["blocks"]))
    return pl


def completed_specs(log: RunLog) -> set[str]:
    """Only specs inside a block that both started and ended.

    A block interrupted mid-flight has a `block_start` and no `block_end`; its
    specs are not completed, however many of them happen to have written a
    result. Counting those would let a killed process contribute to a verdict.
    """
    started, done = {}, set()
    for r in log.read():
        if r["kind"] == "block_start":
            started[r["block_index"]] = r
        elif r["kind"] == "block_end":
            done.update(r["specs"])
    return done


def incomplete_blocks(log: RunLog) -> list[int]:
    started = [r["block_index"] for r in log.read() if r["kind"] == "block_start"]
    ended = {r["block_index"] for r in log.read() if r["kind"] == "block_end"}
    return sorted(set(started) - ended)


def run_blocks(log: RunLog, budget: Budget, out: Path, pl: dict, backend) -> None:
    """The 24 blocks, in the frozen order (§6.1).

    The budget is consulted *before* a block and never inside one. Once
    `block_start` is written the block runs to completion or is left visibly
    incomplete; there is no partial credit.
    """
    by_id = {s["run_id"]: s for s in pl["specs"]}
    done = completed_specs(log)
    for b in pl["blocks"]:
        if set(b["specs"]) <= done:
            continue
        budget.check("before_block", b["index"])       # may raise; nothing started
        log.append("block_start", block_index=b["index"], arm=b["arm"],
                   donor_id=b["donor_id"], horizon=b["horizon"],
                   specs=b["specs"])
        results = []
        for run_id in b["specs"]:
            spec = by_id[run_id]
            t0 = time.time()
            r = backend(spec)
            results.append({"run_id": run_id, "seconds": round(time.time() - t0, 1),
                            **r})
            log.append("continuation", block_index=b["index"], run_id=run_id, **r)
        digest = write_atomic(out / f"block_{b['index']:02d}.json",
                              json.dumps({"block": b, "results": results},
                                         indent=2, sort_keys=True))
        log.append("block_end", block_index=b["index"], specs=b["specs"],
                   file_sha256=digest)


def classify(log: RunLog, pl: dict | None) -> dict:
    """The four terminal states (§6.3, §6.4, §6.5, §3).

    Only `complete_72` may proceed to a recoverability verdict.
    """
    kinds = [r["kind"] for r in log.read()]
    if "donor_yield_stop" in kinds:
        return {"state": "donor_yield_feasibility_stop", "verdict_allowed": False,
                "reason": "the donor cap was reached without the registered FAIL "
                          "count; no continuations were run"}
    if "integrity_stop" in kinds:
        return {"state": "integrity_stop", "verdict_allowed": False,
                "reason": "an environment or serving integrity check failed"}
    if pl is None:
        return {"state": "integrity_stop", "verdict_allowed": False,
                "reason": "no manifest was frozen"}
    done = completed_specs(log)
    want = {s["run_id"] for s in pl["specs"]}
    if done == want:
        return {"state": "complete_72", "verdict_allowed": True,
                "reason": f"all {len(want)} specs completed"}
    v = verdict_for([s for s in pl["specs"] if s["run_id"] in done], pl["specs"])
    return {"state": "budget_censored_feasibility_run", "verdict_allowed": False,
            "reason": v["classification"], "completed": len(done),
            "of": len(want), "incomplete_blocks": incomplete_blocks(log)}


def plan(donors: list[dict]) -> dict:
    specs = P.expand(donors)
    bl = P.blocks(specs)
    return {"specs": specs, "blocks": bl,
            "protocol_hash": P.protocol_hash(),
            "manifest_hash": P.manifest_hash(specs),
            "order_hash": P.order_hash(bl)}


def _fake_donors() -> list[dict]:
    """Placeholders for --resolve-only. Shape only; no donor exists yet."""
    d = [{"arm": "FAIL", "donor_id": f"resolve_fail_{i}", "seed": i,
          "run_id": f"resolve_fail_{i}"} for i in range(P.ARMS["FAIL"]["donors"])]
    d += [{"arm": "PASS", "donor_id": f"resolve_pass_{i}", "seed": 100 + i,
           "run_id": f"resolve_pass_{i}"} for i in range(P.ARMS["PASS"]["donors"])]
    return d


def resolve_only(out: Path) -> int:
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"  [{'ok ' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))

    print(f"protocol hash {P.protocol_hash()}   prereg {P.PREREG}")
    pl = plan(_fake_donors())
    specs, bl = pl["specs"], pl["blocks"]

    print("\n── cartesian product ──")
    check("72 specs", len(specs) == 72, f"got {len(specs)}")
    for arm, a in P.ARMS.items():
        want = a["donors"] * len(P.HORIZONS) * a["replicates"]
        got = sum(1 for s in specs if s["arm"] == arm)
        check(f"{arm}: {a['donors']}x{len(P.HORIZONS)}x{a['replicates']}",
              got == want, f"{got}/{want}")
    check("every cell distinct", len({s["run_id"] for s in specs}) == len(specs))
    check("horizons exactly 16/24/28",
          {s["horizon"] for s in specs} == set(P.HORIZONS))
    check("step_limit = 250 - h",
          all(s["step_limit"] == 250 - s["horizon"] for s in specs))

    print("\n── the 36 is a strict nested subset, by replicate index ──")
    sub = P.subset_36(specs)
    ids, sub_ids = {s["run_id"] for s in specs}, {s["run_id"] for s in sub}
    check("36 members", len(sub) == 36, f"got {len(sub)}")
    check("subset ⊂ manifest", sub_ids < ids, "strict subset")
    check("defined only by replicate index",
          all((s["replicate"] in P.SUBSET_36[s["arm"]]) == s["in_subset_36"]
              for s in specs))
    check("drops no donor", {s["donor_id"] for s in sub} == {s["donor_id"] for s in specs})
    check("drops no horizon", {s["horizon"] for s in sub} == set(P.HORIZONS))
    check("drops no arm", {s["arm"] for s in sub} == set(P.ARMS))
    check("completing 36 yields NO recoverability verdict",
          verdict_for(sub, specs)["verdict"] is None,
          verdict_for(sub, specs)["classification"])

    print("\n── blocks and execution order ──")
    check("24 blocks", len(bl) == 24, f"got {len(bl)}")
    check("blocks partition the specs",
          sorted(r for b in bl for r in b["specs"]) == sorted(s["run_id"] for s in specs))
    check("FAIL blocks precede PASS",
          [b["arm"] for b in bl] == ["FAIL"] * 12 + ["PASS"] * 12)
    check("block sizes 4 (FAIL) / 2 (PASS)",
          {b["size"] for b in bl if b["arm"] == "FAIL"} == {4}
          and {b["size"] for b in bl if b["arm"] == "PASS"} == {2})
    check("order is deterministic", P.order_hash(P.blocks(specs)) == pl["order_hash"])

    print("\n── budget logic ──")
    import tempfile
    log = RunLog(Path(tempfile.mkdtemp()) / "probe.jsonl")
    b = Budget(log)
    try:
        b.check("after_setup"); check("refuses with no billing reading", False)
    except BudgetStop as e:
        check("refuses with no billing reading", e.kind == "no_billing_reading")
    for usd, cp, want in ((10.0, "after_setup", None), (86.0, "before_block", "no_new_block"),
                          (91.0, "after_donors", "stop_stage"),
                          (101.0, "after_setup", "absolute")):
        b.record_reading(usd)
        try:
            b.check(cp, 0); got = None
        except BudgetStop as e:
            got = e.kind
        check(f"${usd:.0f} at {cp} -> {want}", got == want, f"got {got}")
    try:
        b.check("whenever_i_feel_like_it"); check("rejects ad-hoc checkpoints", False)
    except ValueError:
        check("rejects ad-hoc checkpoints", True)
    check("billing entry is manual-only by default",
          log.last_billing()["source"] == "manual")

    print("\n── artifact layout ──")
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(
        {k: pl[k] for k in ("protocol_hash", "manifest_hash", "order_hash")}
        | {"specs": specs, "blocks": bl}, indent=2))
    check("plan.json written", (out / "plan.json").exists())
    check("run log is append-only JSONL", RunLog(out / "run.jsonl").read() == [])

    print(f"\nprotocol {pl['protocol_hash']}  manifest {pl['manifest_hash']}"
          f"  order {pl['order_hash']}")
    print("\nNOTE: manifest and order hashes above are for PLACEHOLDER donors.")
    print("The real ones are fixed once §4 binds donors, and are logged then.")
    print("\nRESOLVE-ONLY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def verdict_for(completed: list[dict], specs: list[dict]) -> dict:
    """§6.4. Anything short of all 72 is censored, and gives no verdict.

    Explicitly including the case where the completed cells coincide with the
    descriptive 36: coinciding with a subset defined in advance does not turn a
    truncated run into a smaller experiment that succeeded.
    """
    done = {s["run_id"] for s in completed}
    if done == {s["run_id"] for s in specs}:
        return {"verdict": "recoverability", "classification": "complete"}
    if done == {s["run_id"] for s in P.subset_36(specs)}:
        return {"verdict": None,
                "classification": "budget-censored feasibility run "
                                  "(coincides with the descriptive 36; still censored)"}
    return {"verdict": None, "classification": "budget-censored feasibility run"}


def execute(out: Path, generate, backend, fingerprint=None) -> dict:
    """The whole pipeline: setup check, donors, freeze, blocks, classify.

    `generate(seed, run_id) -> "FAIL" | "PASS" | other` is the donor producer
    plus the frozen checker; `backend(spec) -> dict` runs one continuation.
    Both are injected so the control flow can be exercised end to end with no
    model, which is how every stop below is tested.
    """
    log = RunLog(out / "run.jsonl")
    pl = None
    try:
        bind_session(log, fingerprint or session_fingerprint())
        budget = Budget(log)
        budget.check("after_setup")
        donors = acquire_donors(log, budget, generate)
        budget.check("after_donors")
        pl = freeze_manifest(log, out, donors)
        run_blocks(log, budget, out, pl, backend)
    except BudgetStop as e:
        log.append("stopped", stop_kind=e.kind, detail=e.detail)
    except FailClosed:
        raise
    if pl is None:
        prior = [r for r in log.read() if r["kind"] == "manifest_frozen"]
        if prior and (out / "manifest.json").exists():
            m = json.loads((out / "manifest.json").read_text())
            pl = {"specs": m["specs"], "blocks": m["blocks"],
                  "manifest_hash": m["manifest_hash"],
                  "order_hash": m["order_hash"]}
    report = classify(log, pl)
    if pl:
        report |= {"manifest_hash": pl["manifest_hash"],
                   "order_hash": pl["order_hash"]}
    report["protocol_hash"] = P.protocol_hash()
    report["incomplete_blocks"] = incomplete_blocks(log)
    digest = write_atomic(out / "report.json", json.dumps(report, indent=2,
                                                          sort_keys=True))
    log.append("report", file_sha256=digest, **{k: report[k]
                                                for k in ("state", "verdict_allowed")})
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "data/runs/c2h"))
    ap.add_argument("--resolve-only", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)

    if args.resolve_only:
        return resolve_only(out)

    raise SystemExit(
        "the live donor generator and continuation backend are not wired: "
        "they are the next commit, and no machine is rented yet. The control "
        "flow is complete and exercised end to end by tests/test_c2h_e2e.py "
        "through injected backends.")


if __name__ == "__main__":
    raise SystemExit(main())
