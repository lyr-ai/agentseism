"""Does streaming change what the agent receives, or only how it arrives?

Streaming is adopted to get around a transport failure -- Cloudflare returns
HTTP 524 on any non-streaming request that takes longer than about 120 s -- and
"it is only transport" is a claim, not a given. vLLM's reasoning parser and tool
parser run different aggregation code on the streaming path, and litellm
reassembles the chunks itself, so the message the agent ends up consuming could
differ in ways a casual eyeball comparison would miss.

**The comparison needs a baseline.** Two responses to the same prompt can differ
without streaming having anything to do with it: this project exists because
temperature 0 leaves serving-level nondeterminism. So each shape is sent three
times -- non-streaming twice and streaming once -- and the question is not
"is stream identical to non-stream" but:

    does stream-vs-nonstream differ in any field that
    nonstream-vs-nonstream does not already differ in?

If repeated non-streaming calls already disagree on a field, a disagreement
there tells us nothing about streaming. If they agree and streaming disagrees,
that is streaming's doing.

**And the baseline has to be made small, or the test has no power.** Run
unseeded, this endpoint disagrees with itself on `content`, `reasoning`,
`tool_calls` and even `actions` for every shape tried -- which is a real
measurement, and the reason this project exists, but it also means
`observed - baseline` is empty almost regardless of what streaming does. So the
gate runs twice. The unseeded pass is reported as a measurement of how much the
server disagrees with itself. The seeded pass, where `seed` is fixed and repeated
non-streaming calls should agree exactly, is the pass that decides: with the
baseline collapsed, any field streaming changes has nowhere to hide.

Fixing the seed here is not a change to the experiment, whose `seed` stays null
because variation is its object of study. It is an instrument for testing the
transport layer, and it is used only in this file.

Comparison is on canonicalised values, not strings. Tool arguments are parsed as
JSON before comparing, so `{"command":"ls"}` and `{ "command": "ls" }` are equal;
tool call ids are compared for presence and count only, since each response mints
its own.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from minisweagent.exceptions import FormatError

from agents.coding.instrumented_model import InstrumentedLitellmModel

MODEL = "openai/Qwen/Qwen3.6-27B-FP8"
KWARGS = {"drop_params": True, "parallel_tool_calls": True}

MAX_TOKENS = 1500
"""Every shape is capped, and the cap is what makes the comparison possible.

The non-streaming arm is the control, and it physically cannot complete a
generation longer than the ~120 s Cloudflare window -- it would 524 and there
would be nothing to compare streaming against. An uncapped first draft of this
file proved the point the expensive way: the long-reasoning shape ran past the
window, every non-streaming attempt came back 524, the retry loop tried six
times per call, and the validator spent 71 minutes reproducing the bug it exists
to work around.

1500 tokens is roughly 35 s at the rate measured here, comfortably inside the
window, and long enough that the streaming path aggregates hundreds of chunks.
The limitation is real and stated: this gate cannot check equivalence for
generations longer than the window, because no control exists there.
"""

SHAPES = {
    "plain text": [
        {"role": "user", "content": "In exactly two sentences, say what a git rebase does."}
    ],
    "reasoning + one tool call": [
        {"role": "user", "content": "Use the bash tool to list the files in /testbed."}
    ],
    "parallel tool calls": [
        {"role": "user", "content": "Using the bash tool, run two independent commands in one "
                                    "response: print the working directory, and list /tmp."}
    ],
    "long reasoning": [
        {"role": "user", "content": "Think carefully step by step, then answer: how many distinct "
                                    "ways can 8 rooks be placed on a chessboard so that none "
                                    "attacks another? Show your reasoning."}
    ],
}


def ask(model, messages: list[dict]) -> tuple[dict, bool]:
    """One call, returning the message even when the agent would reject it.

    `LitellmModel.query` raises `FormatError` when a response carries no tool
    call, which the plain-text shape does on purpose. The response still exists
    and is still worth comparing -- and whether a shape produces a usable action
    at all is itself a field the agent consumes, so it is recorded rather than
    allowed to abort the comparison.
    """
    try:
        return model.query(messages), False
    except FormatError as exc:
        return (exc.messages[0] if getattr(exc, "messages", None) else {}), True


def canonical(message: dict) -> dict:
    """The fields the agent actually consumes, in a form where equal means equal."""
    response = message.get("extra", {}).get("response") or {}
    choice = (response.get("choices") or [{}])[0]
    inner = choice.get("message") or {}

    calls = []
    for call in inner.get("tool_calls") or []:
        function = call.get("function") or {}
        arguments = function.get("arguments")
        try:
            arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
        except (TypeError, ValueError):
            pass  # unparseable arguments are a difference worth seeing verbatim
        calls.append({"type": call.get("type"), "name": function.get("name"),
                      "arguments": arguments, "has_id": bool(call.get("id"))})

    usage = response.get("usage") or {}
    return {
        "finish_reason": choice.get("finish_reason"),
        "content": inner.get("content") or "",
        "reasoning": inner.get("reasoning") or inner.get("reasoning_content") or "",
        "tool_calls": calls,
        "n_tool_calls": len(calls),
        # What the agent will execute. If anything here differs, nothing else
        # matters -- but `tool_call_id` is minted per response
        # (`actions.append({"command": ..., "tool_call_id": tool_call.id})`), so
        # comparing it makes two byte-identical responses look different. An
        # earlier draft did compare it and reported the tool-call shapes as
        # unprovable; the difference was the id and nothing else.
        "actions": [{k: v for k, v in a.items() if k != "tool_call_id"}
                    for a in (message.get("extra", {}).get("actions") or [])],
        "action_ids_present": all(a.get("tool_call_id")
                                  for a in (message.get("extra", {}).get("actions") or [])),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
    }


def snapshot(model, messages: list[dict]) -> dict:
    message, format_error = ask(model, messages)
    return canonical(message) | {"format_error": format_error}


def differing(a: dict, b: dict) -> set[str]:
    return {k for k in a if a[k] != b.get(k)}


def compare(seed: int | None) -> list[tuple[str, set, set]]:
    kwargs = dict(KWARGS) | {"max_tokens": MAX_TOKENS} | ({"seed": seed} if seed is not None else {})
    # Two attempts, not six. A 524 here is a fact about the control arm, not
    # something to grind through: the validator should report it and move on.
    limits = {"max_attempts": 2, "attempt_timeout": 150}
    plain = InstrumentedLitellmModel(model_name=MODEL, model_kwargs=dict(kwargs), stream=False, **limits)
    streamed = InstrumentedLitellmModel(model_name=MODEL, model_kwargs=dict(kwargs), stream=True, **limits)

    verdicts = []
    for label, messages in SHAPES.items():
        a = snapshot(plain, messages)
        b = snapshot(plain, messages)
        c = snapshot(streamed, messages)
        baseline = differing(a, b)          # nondeterminism, streaming uninvolved
        observed = differing(a, c)          # nondeterminism + streaming
        attributable = observed - baseline  # what only streaming explains
        verdicts.append((label, baseline, attributable))
        print(f"\n── {label}")
        print(f"   non-stream vs non-stream differs in: {sorted(baseline) or 'nothing'}")
        print(f"   non-stream vs stream     differs in: {sorted(observed) or 'nothing'}")
        print(f"   attributable to streaming:           {sorted(attributable) or 'nothing'}")
        for field in sorted(attributable):
            print(f"     {field}:\n       non-stream {str(a.get(field))[:220]}")
            print(f"       stream     {str(c.get(field))[:220]}")
    return verdicts


def main() -> None:
    if not os.getenv("OPENAI_API_BASE"):
        raise SystemExit("set OPENAI_API_BASE and OPENAI_API_KEY")

    print("══════ unseeded: how much does the server disagree with itself? ══════")
    unseeded = compare(None)

    print("\n\n══════ seeded: the gate ══════")
    seeded = compare(20260908)

    print("\n──── result ────")
    noisy = [label for label, baseline, _ in seeded if baseline]
    failed = [label for label, _, attributable in seeded if attributable]
    for label, baseline, attributable in seeded:
        mark = "FAIL" if attributable else ("weak" if baseline else "pass")
        note = f" — seeded baseline still differs in {sorted(baseline)}" if baseline else ""
        print(f"  {mark}  {label}{note}")
    print("\n  unseeded baseline, for the record:")
    for label, baseline, _ in unseeded:
        print(f"    {label:<26} {sorted(baseline) or 'nothing'}")

    if failed:
        print(f"\nFAIL — streaming changes {failed}; it is not a transport-only correction")
        raise SystemExit(1)
    if noisy:
        print(f"\nWEAK — seeding did not make {noisy} reproducible, so on those shapes the "
              f"comparison had no power and streaming is unproven rather than proven")
        raise SystemExit(2)
    print("\nPASS — with the baseline collapsed by a fixed seed, every field the agent "
          "consumes is byte-identical under streaming")


if __name__ == "__main__":
    main()
