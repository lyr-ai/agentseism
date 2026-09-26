"""The gate the flask batch is not collected without.

One question: does a single request that generates for well over 120 seconds
come back as JSON? On RunPod's HTTP endpoint it does not -- Cloudflare returns
HTTP 524 with a 7879-byte HTML page at ~125 s while vLLM finishes the request
normally and records no error. That failure reads as model instability, cost two
Phase A1 batches, and injected extra sampling draws through retries. A horizon
curve cannot absorb that the way terminal identity could.

So this runs before anything else, and a failure here means no data is
collected, not that the client is tuned again.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import httpx

TOOL = {"type": "function", "function": {
    "name": "bash", "description": "Execute a bash command",
    "parameters": {"type": "object", "properties": {
        "command": {"type": "string", "description": "The bash command to execute"}},
        "required": ["command"]}}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True, help="e.g. http://1.2.3.4:40123/v1")
    ap.add_argument("--key", default="not-needed")
    ap.add_argument("--long-tokens", type=int, default=8000)
    args = ap.parse_args()

    headers = {"Authorization": f"Bearer {args.key}", "Content-Type": "application/json"}
    failures = []

    with httpx.Client(timeout=httpx.Timeout(connect=15.0, read=600.0, write=30.0, pool=15.0)) as c:
        # 1 — what is being served, and at what length
        r = c.get(f"{args.base}/models", headers=headers)
        try:
            model = r.json()["data"][0]
            print(f"  model      {model['id']}  max_model_len {model.get('max_model_len')}")
            if model.get("max_model_len") != 131072:
                failures.append(f"max_model_len is {model.get('max_model_len')}, not 131072")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"/v1/models did not return JSON: {r.status_code} {exc}")
            model = {"id": "?"}

        # 2 — tool calling. A wrong parser serves happily and returns no actions,
        #     which the agent experiences as every step being empty.
        t = time.time()
        r = c.post(f"{args.base}/chat/completions", headers=headers, json={
            "model": model["id"], "messages": [{"role": "user", "content": "Run ls."}],
            "tools": [TOOL], "tool_choice": "auto", "temperature": 0, "max_tokens": 200})
        try:
            message = r.json()["choices"][0]["message"]
            calls = message.get("tool_calls") or []
            reasoning = bool(message.get("reasoning") or message.get("reasoning_content"))
            print(f"  tool call  {len(calls)} in {time.time() - t:.1f}s   "
                  f"reasoning field: {reasoning}   content: {message.get('content')!r}")
            if not calls:
                failures.append("no tool_calls returned: the tool parser is wrong")
            if not reasoning:
                failures.append("no separate reasoning field: the reasoning parser is wrong")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"tool-call request did not return JSON: {r.status_code} {exc}")

        # 3 — the one that matters. `ignore_eos` is what makes it a test: asking
        #     politely for a long answer is not enough, the model stopped after
        #     751 tokens in 15 s the first time this ran and exercised nothing.
        #     Forcing the full budget puts the request well past the window at
        #     the ~49 tokens/s measured here.
        t = time.time()
        r = c.post(f"{args.base}/chat/completions", headers=headers, json={
            "model": model["id"],
            "messages": [{"role": "user", "content": "Count from 1 to 20000, one per line."}],
            "temperature": 0, "max_tokens": args.long_tokens, "ignore_eos": True})
        elapsed = time.time() - t
        content_type = r.headers.get("content-type", "")
        try:
            usage = r.json()["usage"]
            print(f"  long gen   {r.status_code} in {elapsed:.1f}s   "
                  f"{usage['completion_tokens']} tokens   {content_type}")
            if elapsed < 120:
                failures.append(
                    f"generation finished in {elapsed:.0f}s, under the 120s window -- "
                    f"this did not test anything; raise --long-tokens and rerun")
        except Exception:
            print(f"  long gen   {r.status_code} in {elapsed:.1f}s   {content_type}   "
                  f"body[:120] {r.text[:120]!r}")
            failures.append(
                f"long generation returned {r.status_code} and not JSON after {elapsed:.0f}s"
                + (" -- this is the Cloudflare 524" if r.status_code == 524 else ""))

    print("\n──── transport gate ────")
    if failures:
        for line in failures:
            print(f"  FAIL  {line}")
        print("\n  No flask data is collected. Fix the endpoint, do not tune the client.")
        sys.exit(1)
    print("  PASS  a request generating past the window returns JSON, tools and")
    print("        reasoning parse, and the context length is the frozen one.")


if __name__ == "__main__":
    main()
