"""The parts of the fork machinery that can be wrong without Docker saying so.

Everything here is a failure mode with a cost. Choosing donors on their outcomes
instead of their step index would select the pair that ended most differently
and then report that they ended differently. Slicing a message prefix mid-turn
would resume an agent that has to speak twice in a row. Seeding a forked agent
by reimplementing the loop would let the forked and unforked conditions drift
apart in ways nothing checks.
"""

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EMPTY = hashlib.sha256(b"").hexdigest()


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


replay = _load("replay_mod", "experiments/coding/replay.py")
validation = _load("fork_validation_mod", "experiments/coding/fork_validation.py")


def rows(*states):
    return [
        {"step": i + 1, "command": f"c{i}", "tracked_diff_hash": s, "workspace_diff_hash": f"w{i}"}
        for i, s in enumerate(states)
    ]


class TestForkPoint:
    def test_ignores_the_empty_state(self):
        """Every run starts on `sha256("")`. Meeting there is not meeting."""
        probes = {"0": rows(EMPTY, EMPTY, "a"), "1": rows(EMPTY, EMPTY, "b")}
        with pytest.raises(SystemExit):
            validation.shared_state(probes)

    def test_prefers_the_state_more_runs_reach(self):
        probes = {
            "0": rows(EMPTY, "shared", "x"),
            "1": rows(EMPTY, "pair", "shared"),
            "2": rows(EMPTY, "pair", "shared"),
        }
        state, carriers = validation.shared_state(probes)
        assert state == "shared"
        assert set(carriers) == {"0", "1", "2"}

    def test_breaks_ties_on_the_latest_arrival(self):
        """Among states all runs reach, take the one everyone has got to first."""
        probes = {"0": rows(EMPTY, "early", "late"), "1": rows(EMPTY, "early", "late")}
        state, _ = validation.shared_state(probes)
        assert state == "early"

    def test_first_arrival_not_last(self):
        """A run that returns to a state is credited with reaching it once.

        Runs revert: two of the three pytest runs ran `git checkout` and came
        back to the empty state. Recording the last visit would date the meeting
        by a return trip.
        """
        probes = {"0": rows(EMPTY, "s", "other", "s"), "1": rows(EMPTY, "s", "z")}
        _, carriers = validation.shared_state(probes)
        assert carriers["0"] == 2


class TestMessagePrefix:
    def messages(self, n):
        out = [{"role": "system", "content": ""}, {"role": "user", "content": ""}]
        for i in range(n):
            out.append({"role": "assistant", "content": "",
                        "extra": {"actions": [{"command": f"c{i}"}]}})
            out.append({"role": "tool", "content": f"o{i}"})
        return out

    def test_prefix_ends_on_an_observation(self):
        prefix = replay.message_prefix(self.messages(5), 3)
        assert prefix[-1]["role"] == "tool"
        assert prefix[-1]["content"] == "o2"
        assert len(prefix) == 8

    def test_rejects_a_multi_action_message(self):
        """One action per message is arithmetic, not a convention to assume."""
        messages = self.messages(2)
        messages[2]["extra"]["actions"].append({"command": "second"})
        with pytest.raises(ValueError):
            replay.message_prefix(messages, 1)

    def test_rejects_a_step_past_the_end(self):
        with pytest.raises(ValueError):
            replay.message_prefix(self.messages(2), 3)


class TestForkedSeeding:
    """`forking` replaces the seed, and nothing else."""

    def make(self, prefix):
        from agents.coding.fork import forking

        class Fake:
            def __init__(self, **kwargs):
                self.messages = []

            def add_messages(self, *messages):
                self.messages.extend(messages)
                return list(messages)

            def run(self, task="", **kwargs):
                self.messages = []
                self.add_messages({"role": "system"}, {"role": "user"})
                self.add_messages({"role": "assistant"})
                return self.messages

        return forking(Fake)(prefix_messages=prefix)

    def test_prefix_replaces_the_seed_and_the_loop_continues(self):
        prefix = [{"role": "system"}, {"role": "user"}, {"role": "assistant"}, {"role": "tool"}]
        agent = self.make(prefix)
        result = agent.run()
        assert result[:4] == prefix
        assert result[4] == {"role": "assistant"}

    def test_no_prefix_is_the_unforked_agent(self):
        agent = self.make(None)
        assert agent.run() == [{"role": "system"}, {"role": "user"}, {"role": "assistant"}]

    def test_a_second_run_reseeds(self):
        prefix = [{"role": "system"}, {"role": "tool"}]
        agent = self.make(prefix)
        agent.run()
        assert agent.run()[:2] == prefix
