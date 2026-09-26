"""Invariant 3: events resolve by identity, never by arithmetic position.

The bug these pin cost an afternoon and could have cost a batch. Message
positions were computed as `prefix + 2 * (step - 1)`, which holds only while
every message either is an action or is the observation of one. Format errors,
retries and system turns break that, and the version that crashed was the lucky
case: an *even* number of interleaved non-step messages realigns the arithmetic
onto the wrong turn, producing an archive that looks correct and forks from the
wrong place.

So the tests insert one non-step message and then two, and assert the same agent
step still resolves to the same action.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("replay_mod", ROOT / "experiments/coding/replay.py")
replay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replay)


def action(command):
    return {"role": "assistant", "content": "", "extra": {"actions": [{"command": command}]}}


def observation(text="ok"):
    return {"role": "tool", "content": text}


def noise(kind):
    """A message that does not advance the environment step."""
    return {"role": "assistant", "content": "", "extra": {"interrupt_type": kind}} \
        if kind == "FormatError" else {"role": "user", "content": "retry please"}


def trajectory(n, inject_after=None, count=0):
    """system, instance, then n action/observation pairs, with noise injected."""
    messages = [{"role": "system"}, {"role": "user"}]
    for k in range(1, n + 1):
        messages.append(action(f"cmd{k}"))
        messages.append(observation())
        if inject_after == k:
            for _ in range(count):
                messages.append(noise("FormatError"))
                messages.append(observation("format error"))
    return messages


class TestActingIndices:
    def test_clean_trajectory(self):
        acting = replay.acting_indices(trajectory(5))
        assert len(acting) == 5
        commands = [trajectory(5)[i]["extra"]["actions"][0]["command"] for i in acting]
        assert commands == ["cmd1", "cmd2", "cmd3", "cmd4", "cmd5"]

    @pytest.mark.parametrize("injected", [1, 2, 3])
    def test_non_step_messages_do_not_shift_the_mapping(self, injected):
        """One inserted pair breaks nothing; two would realign the arithmetic.

        The two-pair case is the dangerous one: `prefix + 2*(step-1)` lands back
        on an assistant message, so the old code would have accepted a wrong turn
        without complaint.
        """
        messages = trajectory(6, inject_after=2, count=injected)
        acting = replay.acting_indices(messages)
        resolved = [messages[i]["extra"]["actions"][0]["command"] for i in acting]
        assert resolved == ["cmd1", "cmd2", "cmd3", "cmd4", "cmd5", "cmd6"]

    def test_arithmetic_would_have_been_wrong(self):
        """Pin the failure the walk prevents, so the reason stays visible."""
        messages = trajectory(6, inject_after=2, count=2)
        acting = replay.acting_indices(messages)
        arithmetic = 2 + 2 * (4 - 1)          # the old formula, for step 4
        assert acting[3] != arithmetic
        assert messages[acting[3]]["extra"]["actions"][0]["command"] == "cmd4"

    def test_start_offset_skips_a_donor_prefix(self):
        messages = trajectory(5)
        acting = replay.acting_indices(messages, start=6)
        assert [messages[i]["extra"]["actions"][0]["command"] for i in acting] == \
            ["cmd3", "cmd4", "cmd5"]


class TestMessagePrefix:
    def test_ends_on_an_observation(self):
        prefix = replay.message_prefix(trajectory(5), 3)
        assert prefix[-1]["role"] == "tool"
        assert prefix[-2]["extra"]["actions"][0]["command"] == "cmd3"

    def test_survives_injected_noise(self):
        messages = trajectory(6, inject_after=2, count=2)
        prefix = replay.message_prefix(messages, 4)
        assert prefix[-1]["role"] == "tool"
        actions = [m["extra"]["actions"][0]["command"] for m in prefix
                   if m.get("role") == "assistant" and m.get("extra", {}).get("actions")]
        assert actions == ["cmd1", "cmd2", "cmd3", "cmd4"]

    def test_rejects_a_step_past_the_end(self):
        with pytest.raises(ValueError):
            replay.message_prefix(trajectory(3), 4)
