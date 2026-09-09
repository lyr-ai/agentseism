"""A model wrapper that owns its own retry loop, and records every attempt.

The reason this exists is a number that could not be explained: one agent step
waited 2840 seconds while the configuration said `timeout: 180` and
`num_retries: 5`, a budget of at most ~900 seconds. The honest reading of that
is not "the proxy was slow" but "we do not know which layer the timeout is in".
litellm, the OpenAI SDK and httpx each carry their own connect, read, pool and
total timeouts and their own retry and backoff policies, and a step recorded as
one 2840-second gap could equally be one request that hung for 47 minutes or a
dozen hidden retries stacked end to end. Those are different failures with
different fixes.

So the retry loop moves here, where it can be instrumented. `num_retries` is set
to 0 underneath: litellm is asked to make exactly one attempt and to raise, and
every repetition is this class's own, numbered and timed.

The second reason is scientific rather than operational. A request that the
server generated and the client never received, then re-sent, is **a fresh
sample, not a replay**: this project's own premise is that temperature 0 leaves
serving-level nondeterminism, so a retried step drew from the model twice and
kept the second draw. Steps where that happened are therefore marked, and the
mark travels with the trajectory:

    transport_attempts   how many attempts the step took
    transport_retried    True if more than one
    transport_events     per attempt: index, seconds, outcome, exception type

A batch with almost no retries can treat this as a nuisance covariate. A batch
with many cannot claim its steps came from the same process as unretried ones,
and the marks are what makes the difference visible instead of assumed.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import litellm
from minisweagent.models.litellm_model import LitellmModel


class InstrumentedLitellmModel(LitellmModel):
    """`LitellmModel` with an explicit, recorded retry loop.

    Extra config keys::

        attempt_timeout    seconds for one attempt (default 180)
        max_attempts       total attempts including the first (default 6)
        retry_backoff      seconds added per retry, linearly (default 5)
        stream             receive the response as it is generated (default False)
        read_timeout       seconds of silence that mean the stream is dead (default 90)

    `stream` is the fix for the failure this class was built to see. RunPod's
    HTTP endpoint sits behind Cloudflare, which returns **HTTP 524 with an HTML
    error page after about 120 seconds** if the origin has sent nothing yet. A
    non-streaming completion sends nothing until the last token, so any single
    model call that takes longer than that is killed in transit while vLLM
    finishes it normally and records no error. Measured directly: a request with
    a tiny prompt and `max_tokens: 8000` returned 524 in 125.1 s, and the same
    prompt capped at 200 tokens returned JSON in 4.7 s.

    Streaming sends the first chunk immediately, so the window never opens. It
    does not cap generation, change the prompt, the sampler or the agent, and it
    is adopted only after field-level equivalence against non-streaming responses
    (`experiments/coding/stream_equivalence.py`) -- because the reasoning and
    tool-call parsers run different aggregation code on the streaming path, and
    "it is only transport" is a claim that has to be checked rather than assumed.
    """

    def __init__(self, **kwargs):
        self._attempt_timeout = kwargs.pop("attempt_timeout", 180)
        self._read_timeout = kwargs.pop("read_timeout", 90)
        self._max_attempts = kwargs.pop("max_attempts", 6)
        self._retry_backoff = kwargs.pop("retry_backoff", 5)
        self._stream = kwargs.pop("stream", False)
        super().__init__(**kwargs)
        # Exactly one attempt per call underneath. Any retry above is ours, and
        # is counted; a hidden one would make the count a lie.
        # A scalar `timeout` does not bound a streamed response. litellm applies
        # it to issuing the request; consuming the chunks is a separate sequence
        # of socket reads, and a stream that dies mid-generation leaves the
        # client blocked inside `next()`, where a wall-clock check between chunks
        # never gets control. Measured on the first Phase B attempt: single
        # attempts ran 1157 s, 3463 s and 3559 s against `attempt_timeout` 180,
        # each ending in "The read operation timed out" from a lower layer.
        #
        # An httpx.Timeout with an explicit `read` component is the bound that
        # actually applies: it means "no bytes for this long", which during
        # active generation -- chunks arrive several times a second -- can only
        # happen if the stream is broken. Prefill on a 60k-token prompt is
        # seconds, so 90 leaves it untouched.
        # Held here rather than in `config.model_kwargs`, and passed per call.
        # The config is serialised into every saved trajectory with pydantic's
        # json mode, which cannot encode an httpx.Timeout: putting it there made
        # all 24 continuations of a batch die on `PydanticSerializationError`
        # before their first step. Only json-safe values belong in the config.
        self._timeout = httpx.Timeout(
            connect=15.0, read=float(self._read_timeout), write=30.0, pool=15.0
        )
        self.config.model_kwargs = dict(self.config.model_kwargs) | {"num_retries": 0}
        self._events: list[dict[str, Any]] = []

    def _streamed(self, messages: list[dict], **kwargs):
        """One streaming attempt, reassembled into an ordinary response object.

        `stream_chunk_builder` is litellm's own reassembly, so the message the
        agent sees is built by the same library that builds the non-streaming
        one. `include_usage` is requested because the usage block arrives in a
        final chunk that is otherwise dropped, and the trajectory records token
        counts.
        """
        deadline = time.time() + self._attempt_timeout
        chunks = []
        stream = super()._query(messages, stream=True, stream_options={"include_usage": True},
                                timeout=self._timeout, **kwargs)
        for chunk in stream:
            chunks.append(chunk)
            # Second bound, for a stream that keeps trickling but never ends.
            # The read timeout above cannot see that case: bytes are arriving.
            if time.time() > deadline:
                getattr(stream, "close", lambda: None)()
                raise litellm.Timeout(
                    f"attempt exceeded {self._attempt_timeout}s while streaming",
                    model=self.config.model_name, llm_provider="openai",
                )
        return litellm.stream_chunk_builder(chunks, messages=messages)

    def _query(self, messages: list[dict], **kwargs):
        self._events = []
        last: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            start = time.time()
            try:
                response = (self._streamed(messages, **kwargs) if self._stream
                            else super()._query(messages, timeout=self._timeout, **kwargs))
            except Exception as exc:  # noqa: BLE001
                self._events.append({
                    "attempt": attempt,
                    "seconds": round(time.time() - start, 1),
                    "outcome": "exception",
                    "exception": type(exc).__name__,
                    "detail": str(exc)[:200],
                })
                # A prompt that does not fit, or a rejected key, will not fit or
                # be accepted on the next try either. Retrying those turns a
                # clear error into a long silence.
                if isinstance(exc, tuple(self.abort_exceptions)):
                    raise
                last = exc
                if attempt < self._max_attempts:
                    time.sleep(self._retry_backoff * attempt)
                continue
            self._events.append({
                "attempt": attempt,
                "seconds": round(time.time() - start, 1),
                "outcome": "ok",
            })
            return response
        assert last is not None
        raise last

    def query(self, messages: list[dict], **kwargs) -> dict:
        message = super().query(messages, **kwargs)
        events = list(self._events)
        message.setdefault("extra", {}).update({
            "transport_stream": self._stream,
            "transport_attempts": len(events),
            "transport_retried": len(events) > 1,
            "transport_events": events,
        })
        return message
