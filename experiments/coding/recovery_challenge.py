"""A deterministic malformed-call challenge, for the pilot's M2 arm.

M2 asks whether removing the recovery guidance costs recovery. Waiting for a
malformed call to happen by itself does not work at this scale: 5 of 32
reference runs saw one, so an 18-run pilot expects about two eligible
observations and can estimate nothing. The event is therefore **part of the
scenario**, identical in every arm, and registered before any run.

    every arm × task × replicate meets the same malformed-call event, at the
    same point; baseline keeps the recovery guidance, M2 removes it.

The point of injecting in *all* arms is that baseline and M2 then differ on one
axis. Injecting only into M2 would differ on two — the hint and the event — and
nothing could be attributed.

What this measures, and how it must be written up:

> agent behaviour under one controlled malformed-call challenge

**not** the rate of malformed calls in production. That distinction belongs in
the paper's own sentences, not in a footnote.

Implementation is one override. The original action is recorded and **never
executed**, and the agent then travels its ordinary `FormatError` path, so the
recovery being measured is the real one rather than a simulation of it.
"""

from __future__ import annotations

from jinja2 import StrictUndefined, Template
from minisweagent.exceptions import FormatError

CHALLENGE_ERROR = ("No tool calls found in the response. Every response MUST "
                   "include at least one tool call.")


def challenging(base):
    """Wrap an agent class so it meets exactly one injected malformed call."""

    class ChallengedAgent(base):
        def __init__(self, *a, **kw):
            self.challenge_fired = False
            self.challenge_record: dict | None = None
            super().__init__(*a, **kw)

        def step(self) -> list[dict]:
            message = self.query()
            actions = (message.get("extra") or {}).get("actions") or []
            if actions and not self.challenge_fired:
                self.challenge_fired = True
                # Recorded, not executed. The environment never sees it.
                self.challenge_record = {
                    "injected_at_call": self.n_calls,
                    "suppressed_actions": actions,
                }
                message.setdefault("extra", {})["recovery_challenge"] = \
                    self.challenge_record
                raise FormatError({
                    "role": "user",
                    "content": Template(
                        self.model.config.format_error_template,
                        undefined=StrictUndefined).render(
                            error=CHALLENGE_ERROR, actions=[],
                            has_tool_calls=False),
                    "extra": {"interrupt_type": "FormatError",
                              "injected": True},
                })
            return self.execute_actions(message)

        @property
        def challenge_eligible(self) -> bool:
            """False when the run never produced a first valid tool call.

            Such a run is `NOT_ELIGIBLE`, never a fabricated event and never a
            recovery failure.
            """
            return self.challenge_fired

    ChallengedAgent.__name__ = f"Challenged{base.__name__}"
    return ChallengedAgent
