"""Mechanical per-step features for PASS/FAIL alignment.

Deliberately not a summary. Every field is a rule over recorded artefacts --
the command string, the probe's state hashes, the observation text -- with no
step that asks a model what a trajectory was "trying to do". With four failures
in the sample, a free-form comparison would produce a persuasive story about
noise, and the point of fixing the features in code is that the same rules apply
to all twenty runs whether they passed or failed.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

EMPTY = hashlib.sha256(b"").hexdigest()

TEST_RE = re.compile(r"\bpytest\b|\bpython -m pytest\b|\btox\b|\bnosetests\b")
# The repository's own suite, as opposed to a scratch reproducer the agent wrote.
SUITE_RE = re.compile(r"\b(testing|tests?)/")
READ_RE = re.compile(r"^\s*(cat|sed|grep|find|ls|head|tail|rg|awk|wc)\b")
EDIT_RE = re.compile(r"^\s*(sed -i|cat >|python3? *<<|patch\b|git apply)")
REVERT_RE = re.compile(r"git (checkout|restore|stash|reset)")

FAILED_RE = re.compile(r"\b(\d+) failed\b|\bFAILED\b|\bERROR\b|\bAssertionError\b")
PASSED_RE = re.compile(r"\b(\d+) passed\b")


def observations(trajectory: dict) -> dict[int, str]:
    """Observation text by env step, using the one-action-per-message layout."""
    out, step = {}, 0
    for message in trajectory["messages"]:
        if message.get("role") == "assistant" and (message.get("extra", {}).get("actions")):
            step += 1
        elif message.get("role") in ("tool", "user") and step:
            out.setdefault(step, str(message.get("content") or ""))
    return out


def features(probe: list[dict], trajectory: dict, prefix_steps: int = 0) -> list[dict]:
    obs = observations(trajectory)
    seen: set[str] = set()
    previous_state = None
    rows = []
    edits = tests = suite_tests = reverts = failing_tests = 0
    last_change = 0
    for index, row in enumerate(probe, start=1):
        command = row.get("command", "") or ""
        state = row.get("tracked_diff_hash") or ""
        text = obs.get(index + prefix_steps, "")

        is_test = bool(TEST_RE.search(command))
        is_suite = is_test and bool(SUITE_RE.search(command))
        is_edit = bool(EDIT_RE.search(command)) or row.get("source_changed")
        is_revert = bool(REVERT_RE.search(command)) or (
            row.get("source_changed") and state == EMPTY)
        # Returning to a state after leaving it, not merely sitting in it. The
        # first version counted every step that held an unchanged state as a
        # revisit, which made "revisit" a synonym for "did not edit".
        revisit = (bool(state) and state != EMPTY and state in seen
                   and state != previous_state)
        test_failed = is_test and bool(FAILED_RE.search(text))

        edits += bool(is_edit)
        tests += bool(is_test)
        suite_tests += bool(is_suite)
        reverts += bool(is_revert)
        failing_tests += bool(test_failed)
        if row.get("source_changed"):
            last_change = index
        if state and state != EMPTY:
            seen.add(state)
        previous_state = state

        rows.append({
            "step": index,
            "is_read": bool(READ_RE.search(command)),
            "is_edit": bool(is_edit),
            "source_changed": bool(row.get("source_changed")),
            "is_test": is_test,
            "is_suite_test": is_suite,
            "is_revert": bool(is_revert),
            "test_failed": test_failed,
            "state_revisit": revisit,
            "at_empty": state == EMPTY,
            "diff_bytes": row.get("tracked_diff_bytes", 0),
            "distinct_states": len(seen),
            "steps_since_source_change": index - last_change,
            "cum_edits": edits,
            "cum_tests": tests,
            "cum_suite_tests": suite_tests,
            "cum_reverts": reverts,
            "cum_failing_tests": failing_tests,
        })
    return rows


def load(runs_dir: str, batch: str, name: str, prefix_steps: int = 0) -> list[dict]:
    base = Path(runs_dir) / batch / name
    probe = [json.loads(l) for l in open(f"{base}.probe.jsonl")]
    trajectory = json.loads(Path(f"{base}.json").read_text())
    return features(probe, trajectory, prefix_steps)
