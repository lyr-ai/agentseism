"""GAIA adapter: state construction, outcome selection, answer equivalence.

GAIA asks for an exact-format answer -- a number, as few words as possible, or a
comma-separated list -- so two runs can produce the *same* answer written
differently. The comparator below normalises those formatting differences away.

Note what it is not: this is an **equivalence relation between two runs**, not a
grader. Two runs that are identically wrong are behaviorally consistent, and
AgentSeism reports them as such (DESIGN.md §5). Correctness against the GAIA
reference answer is recorded separately, as optional metadata.

The normalisation rules follow GAIA's stated answer format. Before any number
from this adapter goes into the paper, check it against the official GAIA
scorer -- a comparator that is subtly stricter or looser moves every consistency
number reported with it.
"""

from __future__ import annotations

import re
import string
from typing import Any

_ARTICLES = {"a", "an", "the"}
_PUNCTUATION = str.maketrans("", "", string.punctuation)

SYSTEM_PROMPT = (
    "You are a general AI assistant. I will ask you a question. Report your "
    "thoughts, and finish your answer by calling the submit_final_answer tool. "
    "YOUR FINAL ANSWER should be a number OR as few words as possible OR a "
    "comma separated list of numbers and/or strings. If you are asked for a "
    "number, don't use comma to write your number neither use units such as $ "
    "or percent sign unless specified otherwise. If you are asked for a string, "
    "don't use articles, neither abbreviations (e.g. for cities), and write the "
    "digits in plain text unless specified otherwise. If you are asked for a "
    "comma separated list, apply the above rules depending of whether the "
    "element to be put in the list is a number or a string."
)


def build_state(task_input: dict) -> dict:
    """Initial LangGraph state for one GAIA question."""
    question = task_input["question"] if isinstance(task_input, dict) else str(task_input)
    return {
        "question": task_input,
        "final_agent_answer": None,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
    }


def extract_answer(final_state: Any) -> str:
    """The submitted final answer, or the last model message if none was submitted."""
    submitted = (
        final_state.get("final_agent_answer")
        if isinstance(final_state, dict)
        else getattr(final_state, "final_agent_answer", None)
    )
    if isinstance(submitted, dict):
        return str(submitted.get("agent_answer", "")).strip()
    if submitted:
        return str(submitted).strip()

    messages = (
        final_state.get("messages", [])
        if isinstance(final_state, dict)
        else getattr(final_state, "messages", [])
    )
    for message in reversed(messages or []):
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        if content:
            return str(content).strip()
    return ""


def outcome(result: dict) -> str:
    """The behavior under study: the final answer, not the prose around it."""
    return result["answer"] if isinstance(result, dict) else str(result)


# -- answer equivalence -----------------------------------------------------


def _normalize_number(value: str) -> float | None:
    cleaned = value.replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_string(value: str) -> str:
    text = value.strip().lower().translate(_PUNCTUATION)
    words = [w for w in text.split() if w not in _ARTICLES]
    return " ".join(words)


_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(\D|$))")


def normalize_answer(value: Any) -> list[str | float]:
    """Normalise an answer into a comparable list of elements.

    The comma is ambiguous in GAIA answers: it separates list items, but agents
    also write it inside numbers despite the instruction not to. Thousands
    separators are stripped first, so "1,000" is one number and "a, b" is two
    items.
    """
    text = "" if value is None else str(value).strip()
    text = _THOUSANDS.sub("", text)
    parts = [p for p in re.split(r"[;,]", text)] if text else [""]
    normalized: list[str | float] = []
    for part in parts:
        number = _normalize_number(part)
        normalized.append(number if number is not None else _normalize_string(part))
    return normalized


def answer_equivalent(a: Any, b: Any) -> float:
    """1.0 if two answers are the same answer, modulo GAIA formatting rules.

    List answers get element-wise partial credit: two runs agreeing on two of
    three list items are more consistent than two runs agreeing on none, and
    collapsing that to 0.0 would hide real structure in the variation.
    """
    na, nb = normalize_answer(a), normalize_answer(b)
    if len(na) != len(nb):
        return 0.0
    if not na:
        return 1.0
    matches = sum(1.0 for x, y in zip(na, nb) if _element_equal(x, y))
    return matches / len(na)


def _element_equal(x: Any, y: Any) -> bool:
    if isinstance(x, float) and isinstance(y, float):
        return abs(x - y) < 1e-9
    return x == y


def is_correct(answer: Any, reference: Any) -> bool:
    """Optional external signal, recorded but never used for weak-point scoring."""
    return answer_equivalent(answer, reference) == 1.0
