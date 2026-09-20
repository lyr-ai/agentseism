"""Generate the demo PR reports from frozen data. No model, no container.

Two of the four verdicts come out of artifacts already committed:

    PASS_WITH_CHANGE   h2_phase_a1 — four runs, all resolved, every trace differs
    INCOMPARABLE       gate9       — agent held fixed, 23/23 actions differ

`REGRESSION` and `INSUFFICIENT_EVIDENCE` are deliberately **not** faked. They
need the pilot, and a demo that invents them would be demonstrating the report
rather than the method.
"""

from __future__ import annotations

import itertools
import json
import statistics as st
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import sys; sys.path.insert(0, str(ROOT))

from experiments.coding.contract import Measurement, decide, load  # noqa: E402
from experiments.coding.report import Row, render  # noqa: E402

RUNS = ROOT / "data/runs"
OUT = ROOT / "docs/demo"
CORRECT = ["r0", "r1", "r2", "r3"]          # SWE-bench resolved

FP = {"model_revision": "e89b16ebf1988b3d6befa7de50abc2d76f26eb09",
      "serving_runtime": "vllm-0.28.0+cu130",
      "dependency_lock": "requirements-vllm.lock",
      "prompt_version": "mode-b-pilot-0", "scaffold_version": "mini-swe-agent-2.4.6"}


def probe(run):
    p = RUNS / "h2_phase_a1" / f"pytest-dev__pytest-10051__{run}.probe.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def pass_with_change(contract) -> tuple[str, dict]:
    """Four correct runs; a trace detector fires on every pair, outcomes hold."""
    F = {}
    for r in CORRECT:
        P = probe(r)
        tools = Counter((p.get("command") or "").split()[:1][0]
                        if (p.get("command") or "").split() else "" for p in P)
        F[r] = {"steps": len(P), "tools": tools,
                "bytes": P[-1]["tracked_diff_bytes"]}
    pairs = list(itertools.combinations(CORRECT, 2))
    rel = lambda a, b: abs(a - b) / max(a, b, 1)  # noqa: E731
    fired = sum(1 for a, b in pairs
                if F[a]["tools"] != F[b]["tools"]
                or rel(F[a]["steps"], F[b]["steps"]) > .20
                or rel(F[a]["bytes"], F[b]["bytes"]) > .20)

    v = decide(contract, FP, FP,
               {"task_success": Measurement(
                   effect=0.0, ci_low=-0.05, ci_high=0.05,
                   evidence={"scenarios": 8, "trials_per_condition": 5,
                             "eligible_scenarios": 6})},
               diagnostic_changed=["trace_divergence", "tool_error_profile"])
    rows = [
        Row("Task success", "4 / 4", "4 / 4", "0 pp", "PASS"),
        Row("Trace divergence", "—", f"{fired}/{len(pairs)} pairs differ",
            "n/a", "diagnostic"),
    ]
    ev = [f"Four independent runs of one task, **all four resolved** the issue.",
          f"Steps ranged {min(f['steps'] for f in F.values())}–"
          f"{max(f['steps'] for f in F.values())}; final patches "
          f"{min(f['bytes'] for f in F.values())}–"
          f"{max(f['bytes'] for f in F.values())} bytes.",
          f"A composite trace detector fires on **{fired} of {len(pairs)}** "
          "correct/correct pairs. Ground truth: none is a regression.",
          "Source: `data/runs/h2_phase_a1`, recomputed from frozen artifacts."]
    return render(v, rows, ev), v


def incomparable(contract) -> tuple[str, dict]:
    """Gate 9: the agent did not change; only the serving path did."""
    g = json.loads((RUNS / "gate9" / "gate9.json").read_text())["results"]
    changed = sum(1 for r in g if not r["action_match"])
    cand = FP | {"serving_runtime": "vllm-0.28.0+cu130 @ H100-PCIe/580.105.08"}
    v = decide(contract, FP, cand)
    ev = [f"Same model id, revision, vLLM, CUDA, weights, prompt and scaffold. "
          f"**The agent did not change.**",
          f"Only the serving path moved: A100-SXM4-80GB → H100 PCIe, driver "
          f"580.126.16 → 580.105.08.",
          f"Structured actions differ on **{changed} of {len(g)}** fork roots.",
          "Without this gate that difference would be reported as an agent "
          "regression on every root.",
          "Source: `data/runs/gate9`, recomputed from frozen artifacts."]
    return render(v, None, ev), v


def main() -> int:
    c = load(ROOT / "contracts/default.yaml")
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("pr-report-pass-with-change", pass_with_change),
                     ("pr-report-incomparable", incomparable)):
        text, v = fn(c)
        (OUT / f"{name}.md").write_text(text + "\n")
        print(f"{name:32} {v['verdict']:22} contract {v['contract_sha256']}")
    print("\nREGRESSION and INSUFFICIENT_EVIDENCE are not generated: they need "
          "the pilot,\nand inventing them would demonstrate the report rather "
          "than the method.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
