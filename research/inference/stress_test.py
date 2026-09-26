"""Context-length stress test against an OpenAI-compatible endpoint.

Deliberately the same test that was run locally under MLX, so the two sets of
numbers can be put side by side. The local baseline, on an M4 Pro with 24 GB of
unified memory serving DeepSeek-Coder-V2-Lite-Instruct 4-bit:

    ctx      TTFT     decode      available   swap delta
    24       --       36.8 tok/s  3.9 GB      ~0
    7,640    10.3 s   89.8 tok/s  4.5 GB      +1242 MB
    15,240   22.2 s   65.8 tok/s  4.2 GB      +1647 MB

Two things in that table are worth carrying over as expectations rather than
conclusions. TTFT roughly doubled when the context doubled, which is prefill
being linear in prompt length; decode fell far less, since each new token
attends to a cache that is already built. And swap grew by more than a gigabyte
at every step and never came back, which is what ended the local route -- not
the model's competence, which was fine at short context.

The comparison to look for on a GPU is whether prefill stays linear, what
happens to decode as the KV cache grows, and whether prefix caching removes the
re-prefill cost that this agent incurs by resending its whole history each step.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from openai import OpenAI

FILLER = "def process_item(x):\n    return x * 2 + 1\n\n"
"""Repeated to reach a target length. Code rather than prose, because the
tokenizer treats them differently and the workload is a coding agent."""


def build_prompt(client: OpenAI, model: str, target_tokens: int) -> str:
    # ~9 tokens per filler block for common code tokenizers; the exact count is
    # reported by the server, so an approximation here is fine.
    body = FILLER * max(1, target_tokens // 9)
    return f"Here is code:\n{body}\nReply with exactly one word: OK"


def measure(client: OpenAI, model: str, prompt: str, max_tokens: int) -> dict:
    """One request, streamed, so time-to-first-token is separable from decode."""
    start = time.time()
    ttft = None
    tokens = 0
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.0,
        stream=True,
        stream_options={"include_usage": True},
    )
    prompt_tokens = None
    reasoning_tokens = 0
    for chunk in stream:
        if chunk.usage is not None:
            prompt_tokens = chunk.usage.prompt_tokens
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        # A reasoning model emits its chain of thought first, in a separate
        # field. Counting only `content` measures time-to-first-*answer*, not
        # time-to-first-token, and with a small max_tokens the answer may never
        # arrive at all -- the first attempt returned ttft=None because 40 tokens
        # were spent entirely on reasoning.
        thinking = getattr(delta, "reasoning", None) or getattr(
            delta, "reasoning_content", None)
        if thinking:
            reasoning_tokens += 1
        if thinking or delta.content:
            if ttft is None:
                ttft = time.time() - start
            tokens += 1
    total = time.time() - start
    decode = tokens / (total - ttft) if ttft is not None and total > ttft else float("nan")
    return {
        "prompt_tokens": prompt_tokens,
        "output_tokens": tokens,
        "reasoning_tokens": reasoning_tokens,
        "ttft_s": round(ttft, 3) if ttft else None,
        "total_s": round(total, 3),
        "decode_tok_s": round(decode, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--model", default="")
    ap.add_argument("--contexts", default="8000,16000,32000")
    ap.add_argument("--max-tokens", type=int, default=256,
                    help="must clear the reasoning budget: this model spent 63 "
                         "of 91 output tokens thinking on a one-line question")
    ap.add_argument("--repeat", type=int, default=2,
                    help="requests per context; the second one shows whether "
                         "prefix caching served the prefill from cache")
    ap.add_argument("--out", default="stress_results.json")
    ap.add_argument("--api-key", default="",
                    help="falls back to OPENAI_API_KEY, then VLLM_API_KEY -- the "
                         "RunPod vLLM template sets the latter and rejects "
                         "unauthenticated requests")
    args = ap.parse_args()

    key = (args.api_key or os.environ.get("OPENAI_API_KEY")
           or os.environ.get("VLLM_API_KEY") or "not-needed")
    client = OpenAI(base_url=args.base_url, api_key=key)
    model = args.model or client.models.list().data[0].id
    print(f"model: {model}\n")
    print(f"{'ctx':>8}{'rep':>5}{'TTFT':>10}{'decode':>12}{'total':>9}{'think':>8}")

    rows = []
    for target in [int(x) for x in args.contexts.split(",")]:
        prompt = build_prompt(client, model, target)
        for rep in range(args.repeat):
            r = measure(client, model, prompt, args.max_tokens)
            r |= {"target": target, "repeat": rep}
            rows.append(r)
            ttft = f"{r['ttft_s']:.2f}s" if r["ttft_s"] is not None else "none"
            print(f"{r['prompt_tokens'] or target:>8}{rep:>5}{ttft:>10}"
                  f"{r['decode_tok_s']:>11.1f}/s{r['total_s']:>8.1f}s"
                  f"{r['reasoning_tokens']:>7}r")

    Path(args.out).write_text(json.dumps(rows, indent=2))
    print(f"\nwrote {args.out}")
    # Deliberately not comparing repeat==0 rows across contexts. That assumes
    # the first request at each length is cold, which is only true if nothing
    # warmed it earlier -- and in the first session two crashed runs had already
    # sent the shorter prompt, so its "cold" TTFT was 0.23s against a genuinely
    # cold 12.11s at twice the length. The script duly reported prefill as
    # 51x superlinear. Within a context, repeat 0 against repeat 1 is a valid
    # cache comparison; across contexts it is not, unless the cache was cleared.
    for target in sorted({r["target"] for r in rows}):
        pair = [r for r in rows if r["target"] == target]
        if len(pair) > 1 and pair[0]["ttft_s"] and pair[1]["ttft_s"]:
            speedup = pair[0]["ttft_s"] / pair[1]["ttft_s"]
            print(f"ctx {pair[0]['prompt_tokens']}: first {pair[0]['ttft_s']:.2f}s, "
                  f"repeat {pair[1]['ttft_s']:.2f}s  ({speedup:.1f}x)"
                  f"{'  <- prefix cache hit' if speedup > 2 else ''}")
    print("\nA first request is only cold if the prefix was never sent before.")
