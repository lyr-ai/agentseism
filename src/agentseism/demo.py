"""`seism demo`: see a CI decision in under a minute, at zero cost.

**The agent is simulated. AgentSeism is not.** Each scenario is a fixture:
it writes out every run's outcome explicitly, one `1` or `0` per run and per
task. That is the kind of pattern a stochastic agent produces, and it is
stated rather than drawn, so no seed or sample was chosen to make a point.
A stand-in agent replays those outcomes through the runner contract. What
they mean is decided by the product's own code, exactly as `seism baseline`
and `seism check` use it:

    resolve_and_validate   the frozen default contract, plus the capability gate
    fingerprint            comparability, checked before any candidate run
    run_trials             the real trial loop, runner and evaluator contracts
    _measure               per-task rates, paired bootstrap over tasks
    decide                 both gates, the verdict order, minimum evidence
    render                 the same PR report `seism check` posts

No API key, no Docker, no SWE-bench, no network. The numbers illustrate the
workflow and are **not evidence**. Real-agent evidence lives in
`analysis/ci_v1/stageC/RESULTS.md`.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agentseism.capability import evaluate as capability_evaluate
from agentseism.contract import _regressed, _sufficient, decide, precheck_comparability
from agentseism.execution import CallableRunner, fingerprint, run_trials
from agentseism.pr_report import render
from agentseism.resolve import resolve_and_validate

CONTRACT = {
    "contract_version": "surface-2",
    "features": {"task_success": {"gate": True, "regression_threshold": 0.10,
                                  "capability_regression": True}},
}
"""The shipped defaults: the 0.10 population threshold every user supplies,
and the frozen capability gate. Nothing here is tuned for the demo."""


@dataclass(frozen=True)
class Scenario:
    title: str
    story: str
    baseline: dict[str, str]       # task -> one "1"/"0" per run, in order
    candidate: dict[str, str]

    @property
    def trials(self) -> int:
        return len(next(iter(self.baseline.values())))


# A customer-support agent's suite. Most tasks usually succeed, a few are
# flaky: 51 of 56 runs pass.
BASELINE = {"checkout": "11111111", "refund-request": "11110111",
            "order-status": "11111111", "address-change": "11111101",
            "product-search": "11111111", "return-label": "10111101",
            "gift-card": "01111111"}

# The same agent, rerun with nothing changed. Four tasks lose a run and one
# gains a run, which is ordinary jitter for a stochastic agent: noise moves
# both ways. 48 of 56.
RERUN = BASELINE | {"refund-request": "11010111", "address-change": "11011101",
                    "product-search": "11111011", "return-label": "10110101",
                    "gift-card": "11111111"}

SCENARIOS = [
    Scenario(
        "Unchanged candidate: natural run-to-run variation",
        "The PR changes nothing the agent does. Its score still moves, "
        "because the agent is stochastic.",
        BASELINE, RERUN),
    Scenario(
        "One capability collapses",
        "The PR breaks checkout and leaves every other task alone. The "
        "average hides it; the capability gate should not.",
        BASELINE, BASELINE | {"checkout": "00000000"}),
    Scenario(
        "Too little evidence",
        "The score drops, but on three tasks run twice each. That is too "
        "little to call either way.",
        {"checkout": "11", "refund-request": "11", "order-status": "11"},
        {"checkout": "11", "refund-request": "10", "order-status": "11"}),
]


def _agent(outcomes: dict[str, str]):
    """A runner in AgentSeism's runner contract: `(task_file, artifact_dir)`.
    It replays the fixture's next outcome for the task and writes it as an
    artifact, as a real agent would. It scores nothing."""
    counter: dict[str, int] = {}

    def run(task_file: str, artifact_dir: str) -> dict:
        task = Path(task_file).stem
        trial = counter.get(task, 0)
        counter[task] = trial + 1
        resolved = outcomes[task][trial] == "1"
        (Path(artifact_dir) / "outcome.json").write_text(
            json.dumps({"task": task, "resolved": resolved}))
        return {}
    return run


def _evaluator(artifact_dir: str, run: dict) -> dict:
    """Deterministic, and reads only the artifact: the evaluator contract."""
    got = json.loads((Path(artifact_dir) / "outcome.json").read_text())
    return {"success": int(got["resolved"])}


def run_scenario(i: int, s: Scenario, workdir: Path) -> dict:
    """One baseline and one candidate, decided by the product. Returns the
    verdict and everything the summary prints."""
    from agentseism.cli import _measure      # the same measurement `check` uses

    contract, _, _ = resolve_and_validate(CONTRACT)
    tasks = [str(workdir / f"s{i}" / f"{t}.json") for t in s.baseline]
    fp_base = fingerprint()
    base_rows = run_trials(CallableRunner(_agent(s.baseline)),
                           _evaluator, tasks, s.trials, workdir / f"s{i}", "baseline")
    baseline = {"results": [r.__dict__ for r in base_rows]}

    incomparable = precheck_comparability(contract, fp_base, fingerprint())
    if incomparable:                                     # same process: never
        return {"verdict": incomparable}
    cand_rows = run_trials(CallableRunner(_agent(s.candidate)),
                           _evaluator, tasks, s.trials, workdir / f"s{i}", "candidate")
    cand = [r.__dict__ for r in cand_rows]

    ms, detail = _measure(contract, baseline, cand, tasks, s.trials)
    verdict = decide(contract, fp_base, fp_base, ms)
    f, m = contract.features["task_success"], ms["task_success"]
    broad = ("INSUFFICIENT EVIDENCE" if not _sufficient(f, m) else
             "REGRESSION" if _regressed(f, m) else "PASS")
    cap = verdict.get("capability", {}).get("task_success") or \
        capability_evaluate(f["capability_regression"], m.per_task)
    return {"verdict": verdict, "detail": detail["task_success"], "broad": broad,
            "capability": cap, "measurement": m, "contract": contract}


MARK = {"PASS": "✓ PASS", "REGRESSION": "✗ REGRESSION",
        "INSUFFICIENT_EVIDENCE": "? INSUFFICIENT EVIDENCE"}
MEANING = {
    "PASS": "The movement is within normal stochastic variation. Safe to merge.",
    "REGRESSION": "The evidence shows this PR made the agent worse. Block the merge.",
    "INSUFFICIENT_EVIDENCE": "Not a pass. There is too little evidence to call "
                             "it either way: run more trials or more tasks.",
}


def _summary(i: int, s: Scenario, r: dict) -> list[str]:
    d, cap, v = r["detail"], r["capability"], r["verdict"]["verdict"]
    k = len(s.baseline)
    lo, hi = d["ci"]
    out = [f"Scenario {i}/{len(SCENARIOS)}: {s.title}",
           f"  {s.story}",
           f"  {k} tasks × {s.trials} runs per side",
           "",
           f"  Task success           {d['baseline']:.0%} → {d['candidate']:.0%}"
           f"   ({(d['candidate'] - d['baseline']) * 100:+.0f} points)",
           f"  Broad reliability      {r['broad']:<22} effect {d['effect']:+.2f}"
           f" [{lo:+.2f}, {hi:+.2f}]"]
    if cap["fired"]:
        cap_state = "REGRESSION"
    elif cap["eligible"]:
        cap_state = "PASS"
    else:
        cap_state = "NOT MONITORED"
    few = s.trials < int(cap_spec_trials())
    out.append(f"  Capability regression  {cap_state:<22} " + (
        f"needs {cap_spec_trials()} runs per side to judge a single task"
        if few else
        f"{len(cap['eligible'])} of {cap['k']} tasks reliable enough to monitor"))
    if cap["fired"] and r["broad"] == "PASS":
        out.append("      The average fell, but the loss sits in one place, so the "
                   "suite-wide evidence is not conclusive. The capability gate "
                   "judges each task directly:")
    for t in cap["fired"] + cap["warnings"]:
        dd = cap["detail"][t]
        out.append(f"      {Path(t).stem:<16} {dd['baseline']} → {dd['candidate']}"
                   f"   {dd['decision']}")
    out += ["", f"  Verdict: {MARK[v]}", f"  {MEANING[v]}", ""]
    return out


def cap_spec_trials() -> int:
    """The capability gate's minimum trials, read from the frozen defaults."""
    from agentseism.capability import DEFAULTS
    return int(DEFAULTS["minimum_evidence"]["trials_per_condition"])


def _report(r: dict, s: Scenario) -> str:
    """The same markdown PR report `seism check` writes and posts."""
    d, v = r["detail"], r["verdict"]
    from agentseism.cli import _capability_lines, scorecard_rows
    rows = scorecard_rows(r["contract"], v, {"task_success": d},
                          {"task_success": r["measurement"]})
    ev = [f"Synthetic demo: {len(s.baseline)} tasks, {s.trials} trials per side.",
          "Independent unit: scenario. Intervals are paired bootstrap over tasks, "
          "not over runs."] + _capability_lines(v.get("capability") or {})
    return render(v, rows, ev)


def main(report: bool = False, out=print) -> int:
    out("AgentSeism demo: a simulated agent, the real decision engine")
    out("No API key, no Docker, no network. The agent replays fixed, stated "
        "outcomes; every verdict below comes from AgentSeism's own contract, "
        "gates and report code.")
    out("")
    with tempfile.TemporaryDirectory() as tmp:
        for i, s in enumerate(SCENARIOS, 1):
            r = run_scenario(i, s, Path(tmp))
            for line in _summary(i, s, r):
                out(line)
            if report:
                out(_report(r, s))
                out("")
    out("This is a synthetic demonstration of the CI workflow, not evidence.")
    out("Real-agent evidence (7 unseen SWE-bench tasks, 224 runs, pre-registered):")
    out("  analysis/ci_v1/stageC/RESULTS.md")
    out("To see the full PR report for each scenario: seism demo --report")
    return 0
