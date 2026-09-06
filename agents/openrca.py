"""Execution features for OpenRCA's two-agent RCA loop.

The scaffold fixes the *diagnostic policy* -- workflow, P95 thresholds, the
metric -> trace -> log order, the localization heuristics are all written into
``agent_prompt.py`` and are identical on every run. What varies is how that
policy gets executed against a particular set of anomalies, so the features here
are decision-level rather than evidence-level.

That ordering matters. In the exploratory batch two of three runs named their
root-cause component *inside the instruction that requested the trace or log
query* -- the component was chosen from metrics, and the later evidence was
gathered to confirm it. A feature read off the evidence would therefore see the
divergence one step after it happened, and would describe a consequence as if it
were a cause.

Features are extracted from artifacts OpenRCA already writes, so nothing here
instruments the agent:

    prompt/{uid}.json        the Administrator's messages, one JSON decision each
    trajectory/{uid}.ipynb   the Executor's code and results
    result/{dataset}.csv     the graded prediction
"""

from __future__ import annotations

import json
import re
from typing import Any

from agentseism.features import FeatureSchema, FeatureSpec, ObservationRole

SCHEMA_VERSION = "openrca/1"

TELEMETRY = ("metric", "trace", "log")

COMPONENTS = (
    "apache01", "apache02", "Tomcat01", "Tomcat02", "Tomcat03", "Tomcat04",
    "MG01", "MG02", "IG01", "IG02", "Mysql01", "Mysql02", "Redis01", "Redis02",
)
"""The candidate set this scaffold gives the agent, from ``basic_prompt_Bank``."""

_EXAMPLE = re.compile(r"\(\s*e\.?g\.?[^)]*\)", re.I)
"""Parenthesised examples, which name components illustratively.

`Aggregate each KPI ... (e.g., Tomcat04-OSLinux-CPU_CPU_CPUCpuUtil)` names a
component without investigating it. Counting that as a commitment put the first
run's commit two steps before it happened, so examples are stripped first.
"""

SCHEMA = FeatureSchema(
    version=SCHEMA_VERSION,
    specs=[
        FeatureSpec(
            "commit_step", comparator="numeric",
            description="1-based step of the first instruction naming exactly one "
                        "candidate component; -1 if the run never narrowed to one",
        ),
        FeatureSpec(
            "candidate_width", comparator="numeric", predecessors=("commit_step",),
            description="how many candidates were still named in the last "
                        "multi-candidate instruction before committing",
        ),
        FeatureSpec(
            "telemetry_path", comparator="sequence", predecessors=("commit_step",),
            description="order of telemetry kinds the instructions asked for, "
                        "consecutive repeats collapsed",
        ),
        FeatureSpec(
            "service_focus", comparator="exact", predecessors=("commit_step",),
            description="the component named at the commit step; the investigation "
                        "target, which need not equal the reported answer",
        ),
        FeatureSpec("component", comparator="exact", role=ObservationRole.OUTCOME,
                    description="reported root-cause component"),
        FeatureSpec("reason", comparator="exact", role=ObservationRole.OUTCOME,
                    description="reported root-cause reason"),
        FeatureSpec("occurrence", comparator="exact", role=ObservationRole.OUTCOME,
                    description="reported root-cause datetime"),
    ],
)


def instructions(prompt_json: dict) -> list[str]:
    """The Administrator's per-step instructions, in order."""
    out = []
    for message in prompt_json.get("messages", []):
        if message.get("role") != "assistant":
            continue
        content = message.get("content", "")
        if '"instruction"' not in content:
            continue
        try:
            out.append(json.loads(content).get("instruction", ""))
        except (TypeError, ValueError):
            continue
    return out


def named_components(instruction: str) -> list[str]:
    text = _EXAMPLE.sub(" ", instruction or "")
    return [c for c in COMPONENTS if re.search(rf"\b{c}\b", text)]


def telemetry_kinds(instruction: str) -> list[str]:
    text = (instruction or "").lower()
    return [t for t in TELEMETRY if re.search(rf"\b{t}", text)]


def project_decisions(prompt_json: dict) -> dict[str, Any]:
    """The four decision-level features, from the Administrator's own messages."""
    steps = instructions(prompt_json)

    commit_step = -1
    service_focus = ""
    width = -1
    last_multi = -1
    for i, instruction in enumerate(steps, start=1):
        named = named_components(instruction)
        if len(named) > 1:
            last_multi = len(named)
        if len(named) == 1 and commit_step == -1:
            commit_step = i
            service_focus = named[0]
            width = last_multi if last_multi > 0 else 1

    path: list[str] = []
    for instruction in steps:
        for kind in telemetry_kinds(instruction):
            if not path or path[-1] != kind:
                path.append(kind)

    return {
        "commit_step": commit_step,
        "candidate_width": width,
        "telemetry_path": path,
        "service_focus": service_focus,
    }


def parse_prediction(prediction: str) -> dict[str, str]:
    """The graded answer's three fields, empty strings when absent."""
    try:
        first = next(iter(json.loads(prediction).values()))
    except (TypeError, ValueError, StopIteration):
        return {"component": "", "reason": "", "occurrence": ""}
    return {
        "component": str(first.get("root cause component", "")),
        "reason": str(first.get("root cause reason", "")),
        "occurrence": str(first.get("root cause occurrence datetime", "")),
    }
