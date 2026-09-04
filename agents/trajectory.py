"""ReAct raw-trace recording and feature projection.

Two separate jobs, deliberately kept apart (DESIGN-FEATURE-PROJECTION.md §5, §6):

1. ``record_raw_trace`` writes the raw execution -- one event per model call and
   tool call -- and keeps it, so it stays available for debugging, later causal
   intervention, and future automatic feature extraction.
2. ``ReActProjector`` converts that raw trace into the declared feature schema
   that attribution actually ranks.

The projection is what makes a variable-length loop comparable. Run A's
``search -> calculator`` and run B's ``search -> search -> calculator -> search``
have no valid node correspondence, but they do have comparable behavior:
the same tool set, a different tool sequence, a different tool-call count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from agentseism.features import FeatureSchema, FeatureSpec, ObservationRole
from agentseism.types import Run

SCHEMA_VERSION = "react/1"

SUBMIT_TOOL = "submit_final_answer"


@dataclass
class Step:
    """One model/tool exchange in a trajectory."""

    kind: str  # "model" | "tool"
    content: Any = None
    tool_name: str | None = None
    tool_args: dict = field(default_factory=dict)


# -- raw trace ---------------------------------------------------------------


def record_raw_trace(trace, *, question: Any, steps: list[Step], answer: Any) -> dict:
    """Record the raw execution. No projection, no truncation."""
    trace.record("transform", "intake", output=question)
    for i, step in enumerate(steps):
        if step.kind == "model":
            trace.record(
                "model_call",
                "model_call",
                input=i,
                output={"content": step.content, "tool": step.tool_name, "args": step.tool_args},
            )
        else:
            trace.record("tool_call", "tool_call", input=step.tool_name, output=step.content)
    trace.record("final_submission", "final_submission", output=answer)
    return {"n_steps": len(steps)}


def record_graph_stream(trace, *, question: Any, updates: list) -> dict:
    """Record a LangGraph node-update stream as raw events, in order.

    One event per message produced by a node, named after the node that produced
    it. Capturing here rather than from the final state is what keeps a
    history-rewriting node (context trimming, summarisation) from erasing the
    evidence before anyone reads it.
    """
    trace.record("transform", "intake", output=question)
    nodes: list[str] = []
    for update in updates or []:
        for node, delta in (update or {}).items():
            nodes.append(node)
            for message in _delta_messages(delta):
                role = _message_kind(message)
                step = steps_from_messages([message])
                if not step:
                    # system / human messages a node injected: still behavior.
                    trace.record(
                        "transform", node, output=_text(_attr(message, "content")), role=role
                    )
                    continue
                one = step[0]
                trace.record(
                    "model_call" if one.kind == "model" else "tool_call",
                    node,
                    input=one.tool_name,
                    output={
                        "content": one.content,
                        "tool": one.tool_name,
                        "args": one.tool_args,
                    }
                    if one.kind == "model"
                    else one.content,
                    role=role,
                )
    return {"n_updates": len(updates or []), "nodes": nodes}


def _delta_messages(delta: Any) -> list:
    if isinstance(delta, dict):
        return list(delta.get("messages") or [])
    return list(getattr(delta, "messages", None) or [])


# -- projection --------------------------------------------------------------

SCHEMA = FeatureSchema(
    version=SCHEMA_VERSION,
    specs=[
        # Positioned: a ReAct loop really does plan before it gathers evidence,
        # and gathers evidence before the reasoning that precedes submission.
        FeatureSpec("initial_plan", comparator="text",
                    description="first model output, before tool interaction"),
        FeatureSpec("evidence_set", comparator="set", predecessors=("initial_plan",),
                    description="normalized set of tool results acquired"),
        FeatureSpec("pre_final_reasoning", comparator="text", predecessors=("evidence_set",),
                    description="reasoning immediately before submission; negative control"),
        # Aggregates: whole-trajectory summaries with no position in the DAG.
        # They get no propagation term rather than an invented one.
        FeatureSpec("tool_set", comparator="set",
                    description="distinct tools used; did the agent choose different capabilities?"),
        FeatureSpec("tool_sequence", comparator="sequence",
                    description="ordered tool calls; did the execution path differ?"),
        FeatureSpec("tool_call_count", comparator="numeric",
                    description="loop length, without pretending occurrence alignment is meaningful"),
        FeatureSpec("final_answer", role=ObservationRole.OUTCOME,
                    description="the outcome itself; never a localization candidate"),
    ],
)
"""Partial order, not a total one: the plan/evidence/reasoning chain is real
execution precedence, while the tool aggregates have no position at all. The
precedence declared here must describe the agent, never be tuned to make a score
look better (§16, §17)."""


class ReActProjector:
    """Projects a recorded ReAct trace into the §8 feature schema."""

    name = "react"
    version = SCHEMA_VERSION
    schema = SCHEMA

    def project(self, run: Run) -> dict[str, Any]:
        model_events = [e for e in run.events if e.name == "model_call"]
        tool_events = [e for e in run.events if e.name == "tool_call"]
        submission = next((e for e in run.events if e.name == "final_submission"), None)

        selections = [
            (e.output or {}).get("tool")
            for e in model_events
            if isinstance(e.output, dict) and (e.output or {}).get("tool")
        ]
        working_tools = [t for t in selections if t != SUBMIT_TOOL]
        evidence = [
            str(e.output) for e in tool_events if (e.input or "") != SUBMIT_TOOL
        ]

        return {
            "tool_set": sorted(set(working_tools)),
            "tool_sequence": working_tools,
            "tool_call_count": len(working_tools),
            "evidence_set": sorted(set(evidence)),
            "initial_plan": _content(model_events[0]) if model_events else "",
            "pre_final_reasoning": _pre_final(model_events),
            "final_answer": submission.output if submission else "",
        }


def _content(event) -> str:
    if isinstance(event.output, dict):
        return str(event.output.get("content", ""))
    return str(event.output or "")


def _pre_final(model_events: list) -> str:
    """The last model output, which is normally the submission turn's reasoning."""
    return _content(model_events[-1]) if model_events else ""


# -- message parsing ---------------------------------------------------------


def _attr(message: Any, name: str, default: Any = None) -> Any:
    if isinstance(message, dict):
        return message.get(name, default)
    return getattr(message, name, default)


def _message_kind(message: Any) -> str:
    kind = str(_attr(message, "type") or _attr(message, "role") or "").lower()
    if kind in ("ai", "assistant"):
        return "model"
    if kind == "tool":
        return "tool"
    return kind or "other"


def steps_from_messages(messages: Iterable[Any]) -> list[Step]:
    """Parse a LangChain-style message list into trajectory steps.

    Duck-typed on purpose: reading a trajectory must not require LangChain.
    """
    steps: list[Step] = []
    for message in messages or []:
        kind = _message_kind(message)
        if kind == "model":
            calls = _attr(message, "tool_calls") or []
            first = calls[0] if calls else None
            steps.append(
                Step(
                    kind="model",
                    content=_text(_attr(message, "content")),
                    tool_name=_call_field(first, "name"),
                    tool_args=_call_field(first, "args") or {},
                )
            )
        elif kind == "tool":
            steps.append(
                Step(kind="tool", content=_text(_attr(message, "content")),
                     tool_name=_attr(message, "name"))
            )
    return steps


def _call_field(call: Any, name: str) -> Any:
    if call is None:
        return None
    if isinstance(call, dict):
        return call.get(name)
    return getattr(call, name, None)


def _text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", block.get("content", ""))))
            else:
                parts.append(str(block))
        return " ".join(p for p in parts if p)
    return str(content)
