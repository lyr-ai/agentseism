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


OUTCOME_PROXIMAL: dict[str, tuple[str, ...]] = {
    "service_focus": ("component",),
}
"""Feature/outcome pairs where the feature is a near-copy of the outcome.

The general rule, not a special case for this adapter: **a feature is excluded
for an outcome dimension when it is a direct semantic precursor or near-copy of
it.** Ranking such a pair measures a restatement, not a mechanism.

`service_focus` is the component the agent settled on while investigating and
`component` is the component it then reported. On the Bank discovery set they
agreed in 31 of 40 runs, and their divergences agreed on 71 of 80 pairs, giving
`A_f = +0.79` at `p < 0.001` -- a number that says the agent reports what it
decided, which was never in question. It is the same leakage as ranking a
declared outcome observation, one step further upstream and correspondingly
harder to notice.

The exclusion is per outcome dimension, not global: `service_focus` remains
analysable against `reason` and `occurrence`, which it does not restate.

Proximity is a claim about meaning, so it is declared here rather than inferred
from a correlation -- a feature that genuinely drives an outcome would also
correlate highly, and dropping features for being predictive is how a method
talks itself out of its own findings. :func:`proximity_agreement` measures the
overlap so a declaration can be checked, never so one can be discovered.
"""


def proximity_agreement(runs: list[dict], feature: str, outcome: str) -> dict:
    """How often a feature and an outcome move together, for auditing a declaration."""
    same_value = sum(1 for r in runs if r.get(feature) == r.get(outcome))
    pairs = agree = 0
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            pairs += 1
            agree += (runs[i].get(feature) != runs[j].get(feature)) == (
                runs[i].get(outcome) != runs[j].get(outcome)
            )
    return {
        "identical_value_rate": same_value / len(runs) if runs else None,
        "codivergence_rate": agree / pairs if pairs else None,
        "declared_proximal": outcome in OUTCOME_PROXIMAL.get(feature, ()),
    }


def analysable_features(outcome: str, names: list[str]) -> list[str]:
    """``names`` minus those declared proximal to ``outcome``."""
    return [n for n in names if outcome not in OUTCOME_PROXIMAL.get(n, ())]


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


def early_commit(prompt_json: dict) -> bool:
    """Did the run name one component at or before it first asked for traces?

    Frozen for the Telecom confirmation. The scaffold's own rules make trace
    analysis the discriminating step -- "if multiple faulty components are
    identified at the same level, you should use traces and logs to identify the
    root cause component" -- so naming a single component no later than that
    request means the choice was made from metrics and the trace was gathered to
    confirm it.

    "At or before" rather than "before": in the discovery set two runs named
    their component inside the very instruction that requested the trace.

    Boolean by construction, so no threshold is chosen from data. A run that
    never commits, or never requests traces, is handled by the sentinels below
    rather than by a cut point.
    """
    steps = instructions(prompt_json)
    commit = next(
        (i for i, s in enumerate(steps, 1) if len(named_components(s)) == 1), None
    )
    trace = next(
        (i for i, s in enumerate(steps, 1) if "trace" in telemetry_kinds(s)), None
    )
    if commit is None:
        return False          # never narrowed to one: not an early commitment
    if trace is None:
        return True           # committed without ever consulting traces
    return commit <= trace


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
