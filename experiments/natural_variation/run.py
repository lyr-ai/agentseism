"""Natural run-to-run variation (DESIGN.md §10, Week 1).

No perturbation: same agent, same tasks, same configuration, N executions.
Produces the per-task consistency distribution behind Figure 1.

    python experiments/natural_variation/run.py

The agent below is the synthetic stand-in so the pipeline is runnable today.
Week 1 replaces it with a public multi-step LLM agent; nothing else here
changes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from agentseism import scan  # noqa: E402
from agents.synthetic import make_synthetic_agent, outcome  # noqa: E402

CASES = [f"incident-{i}" for i in range(20)]
TRIALS = 10


def main() -> None:
    report = scan(
        make_synthetic_agent("evidence_selection"),
        CASES,
        trials=TRIALS,
        outcome=outcome,
        comparator="exact",
        agent_id="synthetic",
        save_to=str(ROOT / "results" / "natural_variation_experiment.json"),
    )
    print(report.render())

    distribution = [
        {
            "task_id": t.task_id,
            "consistency": t.consistency,
            "variation": t.variation,
            "modes": [m.share for m in t.modes],
        }
        for t in report.tasks
    ]
    out = ROOT / "results" / "natural_variation.json"
    out.write_text(
        json.dumps(
            {
                "agent": report.agent_id,
                "tasks": len(report.tasks),
                "trials": TRIALS,
                "mean_consistency": report.consistency,
                "median_consistency": report.median_consistency,
                "distribution": distribution,
            },
            indent=2,
        )
    )
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
