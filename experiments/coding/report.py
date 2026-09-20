"""The PR report. The thing a developer actually reads.

The decision comes first, then the scorecard, then the evidence, then — only
for a regression — the localisation. A reader who stops after the first three
lines should already know whether to merge.

Renders from a verdict (`contract.decide`) and the measurements behind it. It
computes nothing and decides nothing: a renderer that can change a verdict is a
second decision layer nobody registered.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class Row:
    """One scorecard line, already measured."""
    capability: str
    baseline: str
    candidate: str
    change: str
    decision: str


HEADLINE = {
    "REGRESSION": "REGRESSION — do not merge without review",
    "INSUFFICIENT_EVIDENCE": "INSUFFICIENT EVIDENCE — not a pass",
    "INCOMPARABLE": "INCOMPARABLE — these runs cannot be compared",
    "PASS_WITH_CHANGE": "PASS — behaviour changed, outcomes held",
    "PASS": "PASS",
}

ACTION = {
    "REGRESSION": "Investigate the localised stage below before merging.",
    "INSUFFICIENT_EVIDENCE": "Neither safe nor unsafe: the evidence was not "
                             "enough to decide. Add trials or narrow the task "
                             "set — do not read this as a pass.",
    "INCOMPARABLE": "Rebuild the baseline on this stack, or explicitly approve "
                    "the comparison. No regression was computed.",
    "PASS_WITH_CHANGE": "Trajectories moved and outcomes did not. Not a reason "
                        "to block.",
    "PASS": "No gating capability regressed.",
}


def render(verdict: dict, rows: list[Row] | None = None,
           evidence: list[str] | None = None,
           rca: list[str] | None = None,
           unaffected: str | None = None) -> str:
    v = verdict["verdict"]
    out = [f"## AgentSeism: {HEADLINE[v]}", "", ACTION[v], ""]

    if v == "INCOMPARABLE":
        out += ["**Fingerprint fields that differ**", ""]
        out += [f"- `{f}`" for f in verdict["mismatched"]]
        out += ["", f"Trials run: **{verdict.get('trials_run', 0)}** — the check "
                    "stops before spending on a comparison that cannot be used.",
                ""]
    elif rows:
        out += ["| Capability | Baseline | PR | Change | Decision |",
                "|---|---:|---:|---:|---|"]
        out += [f"| {r.capability} | {r.baseline} | {r.candidate} | "
                f"{r.change} | {r.decision} |" for r in rows]
        out.append("")

    if verdict.get("warnings"):
        out += ["**Warnings** (do not block a merge): "
                + ", ".join(f"`{w}`" for w in verdict["warnings"]), ""]

    if evidence:
        out += ["**Evidence**", ""] + [f"- {e}" for e in evidence] + [""]

    if v == "REGRESSION" and rca:
        out += ["**Root-cause analysis** — run because the outcome regressed, "
                "not because the trace moved", ""]
        out += [f"- {line}" for line in rca] + [""]
        if unaffected:
            out += [f"**Unaffected:** {unaffected}", ""]
    elif rca:
        # Defensive: RCA output must not appear under a non-regression verdict,
        # because a reader would take it as a reason the merge is risky.
        raise ValueError(f"RCA supplied for verdict {v}; RCA runs only on "
                         "REGRESSION")

    out += ["---", "",
            f"<sub>contract `{verdict['contract_version']}` "
            f"`{verdict['contract_sha256']}` · protocol "
            f"v{verdict['protocol_version']}"]
    if verdict.get("verdict_authority") == "descriptive_only":
        out[-1] += (" · **descriptive only** — this run is a feasibility study "
                    "and its verdict is not a release decision")
    out[-1] += "</sub>"
    return "\n".join(out)


def as_json(verdict: dict, rows: list[Row] | None = None, **extra) -> str:
    return json.dumps({"verdict": verdict,
                       "scorecard": [r.__dict__ for r in (rows or [])],
                       **extra}, indent=2, sort_keys=True)
