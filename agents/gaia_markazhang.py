"""Adapter for the multi-node GAIA agent at github.com/MarkAZhang/gaia-agent.

Graph shape (read from that repository, not vendored -- it carries no license):

```text
START → core_agent ─┬→ tools → memory_management → core_agent
                    ├→ return_llm_refusal → END
                    ├→ return_llm_tool_not_available → END
                    └→ check_and_get_final_answer ─┬→ core_agent   (format retry)
                                                   └→ output_formatter → END
```

Three properties of that graph drive this adapter:

1. **`memory_management` rewrites history.** It replaces earlier tool messages
   with the string ``"removed"`` to save input tokens. Reading the trajectory
   from the final state would therefore report the agent as having gathered
   almost no evidence. This adapter requires stream capture, and refuses to run
   from a final state.
2. **There are two answers.** `check_and_get_final_answer` extracts the agent's
   own ``Ans:`` line; `output_formatter` then rewrites it with a second model.
   Both are declared outcome observations: the raw answer is the outcome before
   formatting, so ranking it would only restate the outcome. The rankable part
   is `formatter_changed_answer`, which keeps "the agent decided differently"
   apart from "the formatter formatted differently".
3. **A run can end without an answer.** Refusal and tool-not-available are
   terminal nodes, so how a run ended is itself behavior.
"""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from agents.gaia import SYSTEM_PROMPT, answer_equivalent
from agentseism.features import FeatureSchema, FeatureSpec, ObservationRole
from agentseism.types import Run

SCHEMA_VERSION = "gaia-mz/2"
"""Schema history.

``gaia-mz/1`` compared ``evidence_set`` entries as the raw serialization of each
tool response. For the search tool that response carries a fresh ``request_id``
UUID and a ``response_time`` float per call, so two runs that retrieved
byte-identical documents still compared unequal: evidence similarity of 1 was
impossible by construction, and the resulting variation would have propagated
through a positioned feature as if it were behavior. Rejected during the §5
instrumentation check, before any pilot data was collected.

``gaia-mz/2`` compares canonicalized evidence content instead: what was
retrieved, not how the provider served it. Transport and runtime metadata are
excluded from the comparison and remain in the raw trace, where they stay
available as variables in their own right.
"""

NODE_CORE = "core_agent"
NODE_TOOLS = "tools"
NODE_MEMORY = "memory_management"
NODE_CHECK = "check_and_get_final_answer"
NODE_FORMAT = "output_formatter"
NODE_REFUSAL = "return_llm_refusal"
NODE_NO_TOOL = "return_llm_tool_not_available"
TERMINAL_NODES = (NODE_FORMAT, NODE_REFUSAL, NODE_NO_TOOL)

TRIMMED = "removed"
"""What memory_management writes over earlier tool results."""

TRANSPORT_KEYS = frozenset({"request_id", "response_time", "id"})
"""Per-call transport metadata: identity of the HTTP call, not of the evidence.

``request_id`` and ``response_time`` sit on the response; ``id`` is assigned per
result *per call*, so the same document carries a different one each time it is
returned. None of the three says anything about what the agent read.

Excluded from ``evidence_set`` only. The raw trace keeps every response intact,
so a later experiment can still ask whether provider latency relates to outcome.
"""

RANKING_KEYS = frozenset({"score"})
"""Provider ranking, which is retrieval behavior rather than evidence content.

Kept out of ``evidence_set`` so that "the agent saw the same documents" and "the
provider ordered them the same way" stay separable questions.
"""

MODEL_ROLE = "model"
"""Role recorded for assistant messages by the raw-trace recorder."""

SCHEMA = FeatureSchema(
    version=SCHEMA_VERSION,
    specs=[
        # Positioned: real execution precedence in this graph.
        FeatureSpec("initial_plan", comparator="text",
                    description="first core_agent output, before any tool result"),
        FeatureSpec("evidence_set", comparator="set", predecessors=("initial_plan",),
                    description="canonicalized evidence retrieved by tools, captured before "
                                "memory_management trims it; transport and ranking metadata excluded"),
        FeatureSpec("pre_final_reasoning", comparator="text", predecessors=("evidence_set",),
                    description="last core_agent output, the turn that emits 'Ans:'; negative control"),
        FeatureSpec("formatter_changed_answer", comparator="exact",
                    description="did output_formatter change the answer, by GAIA equivalence? "
                                "Formatter variation is not agent variation"),
        # Declared as an outcome, not a feature: it is the outcome before
        # formatting, so its association is ~1 by construction and ranking it
        # would only restate the outcome (§9). It is still projected, because
        # comparing the two outcome observations is what separates agent
        # variation from formatter variation.
        FeatureSpec("raw_final_answer", comparator=answer_equivalent,
                    role=ObservationRole.OUTCOME,
                    description="the agent's own answer, before the output formatter rewrites it"),
        # Aggregates: whole-trajectory summaries with no position.
        FeatureSpec("tool_set", comparator="set"),
        FeatureSpec("tool_sequence", comparator="sequence"),
        FeatureSpec("tool_call_count", comparator="numeric"),
        FeatureSpec("answer_format_retries", comparator="numeric",
                    description="times check_and_get_final_answer rejected the format and looped back"),
        FeatureSpec("termination", comparator="exact",
                    description="output_formatter / refusal / tool_not_available"),
        FeatureSpec("final_answer", comparator=answer_equivalent, role=ObservationRole.OUTCOME),
    ],
)


class GaiaGraphProjector:
    """Projects this graph's streamed node updates into the schema above."""

    name = "gaia-markazhang"
    version = SCHEMA_VERSION
    schema = SCHEMA

    def project(self, run: Run) -> dict[str, Any]:
        by_node: dict[str, list] = {}
        for event in run.events:
            by_node.setdefault(event.name, []).append(event)

        core = by_node.get(NODE_CORE, [])
        tools = by_node.get(NODE_TOOLS, [])
        checks = by_node.get(NODE_CHECK, [])

        if not core and not tools:
            raise ValueError(
                "no core_agent or tools events: this adapter needs stream capture "
                "(memory_management rewrites the final state's tool messages)"
            )

        evidence = [
            item
            for e in tools if str(e.output) != TRIMMED
            for item in canonical_evidence(e.output)
        ]
        sequence = [e.input for e in tools if e.input]
        raw_answer = _last_answer(checks)
        formatted = _formatted_answer(run)

        return {
            "initial_plan": _content(core[0]) if core else "",
            "evidence_set": sorted(set(evidence)),
            "pre_final_reasoning": _content(core[-1]) if core else "",
            "raw_final_answer": raw_answer,
            "formatter_changed_answer": answer_equivalent(raw_answer, formatted) < 1.0,
            "tool_set": sorted(set(sequence)),
            "tool_sequence": sequence,
            "tool_call_count": len(tools),
            "answer_format_retries": sum(
                1 for e in checks if e.metadata.get("role") != MODEL_ROLE
            ),
            "termination": _termination(run),
            "final_answer": formatted,
        }


def _canonical_url(url: str) -> str:
    """Same document fetched twice should canonicalize to the same string.

    Deliberately conservative: scheme and host are case-normalized and a
    trailing slash is dropped, but the query is kept, because for several
    sources in this slice the query *is* the document identity
    (``youtube.com/watch?v=...``).
    """
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return url.strip()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def canonical_evidence(output: Any) -> list[str]:
    """Evidence items a tool exposed to the agent, without transport metadata.

    ``evidence_set`` answers "did the agent see the same information?". The raw
    response answers a different question -- "did the provider return the same
    bytes?" -- and the two diverge on every call, because the search tool stamps
    a fresh ``request_id`` and ``response_time`` into each response (see
    ``SCHEMA_VERSION``).

    A search-shaped response is projected to one entry per retrieved result,
    keyed by canonical URL and normalized content. Anything else -- code output,
    parsed documents, transcripts -- is passed through as normalized text, since
    for those tools the response *is* the evidence.
    """
    raw = output if isinstance(output, (dict, list)) else _parse_json(output)

    if isinstance(raw, dict) and isinstance(raw.get("results"), list):
        items = []
        for result in raw["results"]:
            if not isinstance(result, dict):
                items.append(_normalize_text(result))
                continue
            body = {
                k: _normalize_text(v)
                for k, v in sorted(result.items())
                if k not in TRANSPORT_KEYS and k not in RANKING_KEYS
            }
            if "url" in result:
                body["url"] = _canonical_url(str(result["url"]))
            items.append(json.dumps(body, sort_keys=True, ensure_ascii=False))
        return items

    if isinstance(raw, dict):
        body = {k: v for k, v in raw.items() if k not in TRANSPORT_KEYS}
        return [json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)]

    return [_normalize_text(output)]


def _parse_json(value: Any) -> Any:
    try:
        return json.loads(value) if isinstance(value, str) else None
    except (TypeError, ValueError):
        return None


def _content(event) -> str:
    if isinstance(event.output, dict):
        return str(event.output.get("content", ""))
    return str(event.output or "")


def _last_answer(checks: list) -> str:
    """The last `Ans:` the check node accepted; empty if it never accepted one."""
    for event in reversed(checks):
        if event.metadata.get("role") == MODEL_ROLE:
            return _content(event)
    return ""


def _termination(run: Run) -> str:
    for event in reversed(run.events):
        if event.name in TERMINAL_NODES:
            return event.name
    return "incomplete"


def _formatted_answer(run: Run) -> str:
    for event in reversed(run.events):
        if event.name == NODE_FORMAT:
            return _content(event)
        if event.name in (NODE_REFUSAL, NODE_NO_TOOL):
            return f"<{event.name}>"
    return ""


# -- wiring ------------------------------------------------------------------


def make_build_state(
    build_system_prompt: Callable[[str | None], str] | None = None,
) -> Callable[[Any], dict]:
    """Initial state for this graph.

    Pass the repository's own ``build_system_prompt`` so the pilot runs the agent
    as its authors configured it; the fallback prompt is only for smoke tests,
    and using it changes what is being measured.
    """

    def build_state(task_input: Any) -> dict:
        question = task_input["question"] if isinstance(task_input, dict) else str(task_input)
        file_name = task_input.get("file_name") or None if isinstance(task_input, dict) else None
        prompt = build_system_prompt(file_name) if build_system_prompt else SYSTEM_PROMPT
        return {
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": question},
            ]
        }

    return build_state


def extract_answer(final_state: Any) -> str:
    """Last assistant message: after output_formatter, that is the formatted answer."""
    messages = (
        final_state.get("messages", [])
        if isinstance(final_state, dict)
        else getattr(final_state, "messages", [])
    )
    for message in reversed(messages or []):
        role = (
            message.get("role") or message.get("type")
            if isinstance(message, dict)
            else getattr(message, "type", None)
        )
        if str(role).lower() in ("ai", "assistant"):
            content = (
                message.get("content") if isinstance(message, dict)
                else getattr(message, "content", None)
            )
            if content:
                return str(content).strip()
    return ""


def outcome(result: dict) -> str:
    return result["answer"] if isinstance(result, dict) else str(result)
