"""Projecting a variable-length agent trajectory onto alignable execution points.

ReAct-style agents (``model -> tools -> model -> ...`` until done) do not have a
fixed execution graph: one run takes three iterations, another takes seven.
Aligning those by occurrence index would pair a run's third model call with a
detour in another run and call the difference "variation" (DESIGN.md §11).

V0 therefore does not align raw iterations. It projects each trajectory onto a
small set of execution points that mean the same thing in every run:

    intake            the question as the agent received it
    plan              the first model output, before any tool result exists
    tool_selection#i  the tool chosen at iteration i (first K iterations)
    tool_result#i     what that tool returned
    tool_sequence     the ordered list of tools used, whole trajectory
    tool_set          the same tools, order- and repetition-insensitive
    evidence          the set of tool results, order-insensitive
    n_steps           trajectory length
    final_answer      the submitted answer

The per-iteration points cover only the first ``max_iterations`` iterations;
anything past that is summarised by the whole-trajectory points rather than
silently dropped. ``tool_sequence`` and ``evidence`` are what make a longer or
reordered trajectory visible as variation instead of as missing data.

``tool_set`` is separated from ``tool_sequence`` on purpose: an agent that used
a different tool and an agent that used the same tools with one extra loop are
different phenomena, and a single ordered-sequence slot scores them alike.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

DEFAULT_MAX_ITERATIONS = 3

OUTCOME_SLOT = "final_answer"
"""The projected point that *is* the outcome. Recorded so a trajectory can be
read end to end, but excluded from weak-point ranking: its outcome association
is 1.0 by construction, so ranking it would only restate the outcome."""


@dataclass
class Step:
    """One model/tool exchange in a trajectory."""

    kind: str  # "model" | "tool"
    content: Any = None
    tool_name: str | None = None
    tool_args: dict = field(default_factory=dict)


def _attr(message: Any, name: str, default: Any = None) -> Any:
    """Read a field from a LangChain message object or a plain dict."""
    if isinstance(message, dict):
        return message.get(name, default)
    return getattr(message, name, default)


def _message_kind(message: Any) -> str:
    kind = _attr(message, "type") or _attr(message, "role") or ""
    kind = str(kind).lower()
    if kind in ("ai", "assistant"):
        return "model"
    if kind == "tool":
        return "tool"
    return kind or "other"


def steps_from_messages(messages: Iterable[Any]) -> list[Step]:
    """Parse a LangChain-style message list into trajectory steps.

    Duck-typed on purpose: AgentSeism must not depend on LangChain to read a
    trajectory someone already captured.
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
                Step(
                    kind="tool",
                    content=_text(_attr(message, "content")),
                    tool_name=_attr(message, "name"),
                )
            )
    return steps


def _call_field(call: Any, name: str) -> Any:
    if call is None:
        return None
    if isinstance(call, dict):
        return call.get(name)
    return getattr(call, name, None)


def _text(content: Any) -> str:
    """Flatten LangChain's block-list content into text."""
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


def record_trajectory(
    trace,
    *,
    question: Any,
    steps: list[Step],
    answer: Any,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> dict:
    """Record the projected execution points on ``trace``.

    Returns a summary dict, including how many iterations exceeded
    ``max_iterations`` so that truncation is visible in the experiment record
    rather than implied.
    """
    trace.record("transform", "intake", output=question)

    model_steps = [s for s in steps if s.kind == "model"]
    tool_steps = [s for s in steps if s.kind == "tool"]

    trace.record(
        "model_call",
        "plan",
        output=model_steps[0].content if model_steps else "",
    )

    for i in range(min(len(model_steps), max_iterations)):
        trace.record(
            "decision",
            f"tool_selection#{i}" if i else "tool_selection",
            input=i,
            output={"tool": model_steps[i].tool_name, "args": model_steps[i].tool_args},
        )
    for i in range(min(len(tool_steps), max_iterations)):
        trace.record(
            "tool_call",
            f"tool_result#{i}" if i else "tool_result",
            input=tool_steps[i].tool_name,
            output=tool_steps[i].content,
        )

    tool_sequence = [s.tool_name for s in model_steps if s.tool_name]
    trace.record("transform", "tool_sequence", output=tool_sequence)
    trace.record("transform", "tool_set", output=sorted(set(tool_sequence)))
    trace.record(
        "transform", "evidence", output=sorted(str(s.content) for s in tool_steps)
    )
    trace.record("transform", "n_steps", output=len(steps))
    trace.record("model_call", "final_answer", output=answer)

    return {
        "n_steps": len(steps),
        "n_model_steps": len(model_steps),
        "n_tool_steps": len(tool_steps),
        "tool_sequence": tool_sequence,
        "iterations_beyond_projection": max(0, len(model_steps) - max_iterations),
    }
