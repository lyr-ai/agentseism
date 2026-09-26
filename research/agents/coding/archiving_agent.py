"""Agent-side half of the fork archive: the message log, at a coherent point.

The environment archives the repository; the agent archives the context. They
have to agree on where "here" is, and they do not number steps the same way. One
assistant message may carry several actions -- the task prompt invites it -- so
an agent step can advance the environment's step counter more than once, and the
observation messages for those actions are appended only after the last of them
has run. A message log sampled between two actions of the same message ends on
an assistant turn whose results do not exist yet, and an agent resumed from it
would be asked to speak twice in a row.

So the log is written once per agent step, into the directory of the *last*
environment step that step produced, and marked `coherent_fork_point`. A step
directory without `messages.json` records a repository state that is real but
not resumable, and the fork tooling refuses it rather than guessing.

Nothing here is a feature. `coding/1` is unchanged.
"""

from __future__ import annotations

import json

from minisweagent.agents.default import DefaultAgent
from minisweagent.agents.interactive import InteractiveAgent


def archiving(base: type) -> type:
    """Wrap an agent class so each step's message prefix lands in the archive."""

    class _Archiving(base):  # type: ignore[valid-type,misc]
        def step(self) -> list[dict]:
            out = super().step()
            # Deliberately not in a `finally`. A step that raised executed no
            # action, or ended the run; writing a longer prefix into the
            # previous step's directory would make the archive claim a fork
            # point that the repository state does not match.
            self._archive_messages()
            return out

        def _archive_messages(self) -> None:
            archive = getattr(self.env, "_probe_archive", "")
            if not archive:
                return
            directory = self.env.step_dir()
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "messages.json").write_text(
                json.dumps(
                    {
                        "env_step": self.env.step_index,
                        "n_messages": len(self.messages),
                        "n_calls": self.n_calls,
                        "coherent_fork_point": True,
                        "messages": self.messages,
                    },
                    indent=1,
                )
            )

    _Archiving.__name__ = f"Archiving{base.__name__}"
    _Archiving.__qualname__ = _Archiving.__name__
    return _Archiving


ArchivingDefaultAgent = archiving(DefaultAgent)
ArchivingInteractiveAgent = archiving(InteractiveAgent)
