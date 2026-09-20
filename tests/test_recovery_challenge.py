"""Feasibility check for the pilot's deterministic recovery challenge.

Six things must hold before M2 is worth spending money on. Fake model, fake
environment: no network, no container, no real agent.
"""
from __future__ import annotations

import pytest
from minisweagent.agents.default import AgentConfig, DefaultAgent

from experiments.coding.recovery_challenge import CHALLENGE_ERROR, challenging

FULL_HINT = """Tool call error:
<error>{{error}}</error>
Every response needs to use the 'bash' tool at least once to execute commands.
Call the bash tool with your command as the argument."""

BARE_HINT = """Tool call error:
<error>{{error}}</error>"""


class FakeModel:
    """Emits a valid tool call every turn, then submits."""

    def __init__(self, hint: str, turns: int = 6):
        class C:
            format_error_template = hint
        self.config = C()
        self.hint, self.turns, self.seen = hint, turns, []
        self.n = 0

    def query(self, messages, **kw):
        self.seen.append(list(messages))
        self.n += 1
        cmd = "echo submit" if self.n >= self.turns else f"echo step{self.n}"
        return {"role": "assistant", "content": f"THOUGHT: {self.n}",
                "extra": {"actions": [{"command": cmd}]}}

    def format_observation_messages(self, message, outputs, template_vars):
        return [{"role": "tool", "content": str(o)} for o in outputs]

    def format_message(self, role, content, extra=None):
        return {"role": role, "content": content, "extra": extra or {}}

    def get_template_vars(self):
        return {}

    def __getattr__(self, name):
        # Everything else the agent may call on a model is a no-op here: this
        # test is about the injection path, not the model interface.
        return lambda *a, **kw: {}


class FakeEnv:
    def __init__(self):
        self.executed = []

    def execute(self, action, **kw):
        self.executed.append(action)
        if "submit" in action["command"]:
            from minisweagent.exceptions import Submitted
            raise Submitted({"role": "exit", "content": "done",
                             "extra": {"exit_status": "Submitted",
                                       "submission": "patch"}})
        return {"output": "ok", "returncode": 0}

    def get_template_vars(self):
        return {}

    def __getattr__(self, name):
        return lambda *a, **kw: {}


def build(hint: str, **cfg):
    Agent = challenging(DefaultAgent)
    m, e = FakeModel(hint), FakeEnv()
    cfg.setdefault("step_limit", 20)
    a = Agent(m, e, system_template="s", instance_template="{{task}}", **cfg)
    return a, m, e


def run(a):
    try:
        a.run(task="t")
    except Exception as exc:          # Submitted ends the run
        if type(exc).__name__ not in ("Submitted", "LimitsExceeded"):
            raise
    return a


# ── 1. the injection point exists and is the first valid tool call ──
def test_the_challenge_fires_at_the_first_valid_tool_call():
    a, m, e = build(FULL_HINT)
    run(a)
    assert a.challenge_fired
    assert a.challenge_record["injected_at_call"] == 1
    assert a.challenge_record["suppressed_actions"] == [{"command": "echo step1"}]


# ── 2. it applies to every arm ──
@pytest.mark.parametrize("hint,cfg", [
    (FULL_HINT, {}),                       # baseline
    (FULL_HINT, {"step_limit": 40}),       # M1
    (BARE_HINT, {}),                       # M2
])
def test_every_arm_meets_the_same_challenge(hint, cfg):
    a, m, e = build(hint, **cfg)
    run(a)
    assert a.challenge_fired and a.challenge_record["injected_at_call"] == 1


# ── 3. exactly once ──
def test_it_fires_exactly_once_per_run():
    a, m, e = build(FULL_HINT)
    run(a)
    injected = [msg for msg in a.messages
                if (msg.get("extra") or {}).get("injected")]
    assert len(injected) == 1


# ── 4. baseline and M2 are identical except the hint ──
def test_baseline_and_m2_differ_only_in_the_recovery_text():
    a1, m1, e1 = build(FULL_HINT)
    a2, m2, e2 = build(BARE_HINT)
    run(a1); run(a2)
    # Same injection point, same suppressed action, same executed commands.
    assert a1.challenge_record["injected_at_call"] == \
           a2.challenge_record["injected_at_call"]
    assert a1.challenge_record["suppressed_actions"] == \
           a2.challenge_record["suppressed_actions"]
    assert e1.executed == e2.executed
    # The only textual difference is the guidance itself.
    i1 = [m for m in a1.messages if (m.get("extra") or {}).get("injected")][0]
    i2 = [m for m in a2.messages if (m.get("extra") or {}).get("injected")][0]
    assert CHALLENGE_ERROR in i1["content"] and CHALLENGE_ERROR in i2["content"]
    assert "Call the bash tool" in i1["content"]
    assert "Call the bash tool" not in i2["content"]


# ── 5. the suppressed call is never executed ──
def test_the_suppressed_action_never_reaches_the_environment():
    a, m, e = build(FULL_HINT)
    run(a)
    assert {"command": "echo step1"} not in e.executed
    assert a.challenge_record["suppressed_actions"] == [{"command": "echo step1"}]


# ── 6. the artifact keeps all three parts ──
def test_the_record_keeps_original_call_injection_and_recovery():
    a, m, e = build(FULL_HINT)
    run(a)
    assert a.challenge_record["suppressed_actions"]              # original
    injected = [m for m in a.messages if (m.get("extra") or {}).get("injected")]
    assert injected                                              # the event
    idx = a.messages.index(injected[0])
    after = [m for m in a.messages[idx + 1:] if m.get("role") == "assistant"]
    assert after                                                 # the recovery
    assert (after[0].get("extra") or {}).get("actions")


# ── eligibility, not fabrication ──
def test_a_run_with_no_valid_tool_call_is_not_eligible():
    class Silent(FakeModel):
        def query(self, messages, **kw):
            self.n += 1
            if self.n > 4:
                from minisweagent.exceptions import Submitted
                raise Submitted({"role": "exit", "content": "x",
                                 "extra": {"exit_status": "Submitted"}})
            return {"role": "assistant", "content": "no call",
                    "extra": {"actions": []}}

    Agent = challenging(DefaultAgent)
    a = Agent(Silent(FULL_HINT), FakeEnv(), system_template="s",
              instance_template="{{task}}", step_limit=20,
              max_consecutive_format_errors=0)
    run(a)
    assert a.challenge_fired is False
    assert a.challenge_eligible is False
    assert a.challenge_record is None


def test_the_challenge_uses_the_arms_own_template():
    """M2's shorter guidance must actually be what the agent sees."""
    a, m, e = build(BARE_HINT)
    run(a)
    i = [x for x in a.messages if (x.get("extra") or {}).get("injected")][0]
    assert i["content"].strip().endswith("</error>")
