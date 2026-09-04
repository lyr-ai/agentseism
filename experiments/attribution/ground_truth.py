"""Ground-truth attribution experiment (DESIGN.md §17, §18).

Injects a known weak point into a synthetic agent, hides the label from every
ranker, and reports Attribution@1 / Attribution@3 for AgentSeism against the
trivial baselines.

    python experiments/attribution/ground_truth.py

This is the harness for Week 5. Running it on the synthetic agent proves the
harness works; the paper number comes from running it against real agents with
injected interventions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from agentseism import divergence_tables, run_experiment  # noqa: E402
from agentseism.localization import (  # noqa: E402
    available_baselines,
    credit_at_k,
    rank_weak_points,
)
from agents.synthetic import (  # noqa: E402
    SCHEMA,
    WEAK_POINTS,
    make_synthetic_agent,
    outcome,
    projector,
)

CASES = ["latency spike", "checkout errors", "slow queries", "auth failures"]
SEEDS = range(10)
TRIALS = 8


def scores(tables, seed: int) -> dict[str, dict[str, float]]:
    """Scores per method. Ties are kept as ties and resolved by credit_at_k.

    ``seed`` varies the random baseline per trial; a fixed seed would make it
    the same permutation 40 times, which is not a random baseline.
    """
    ranked = {"agentseism": {w.name: w.score for w in rank_weak_points(tables, SCHEMA)}}
    for name, scorer in available_baselines(SCHEMA, scorers=True).items():
        ranked[name] = scorer(tables, SCHEMA, seed=seed)
    return ranked


def main() -> None:
    methods = ["agentseism", *available_baselines(SCHEMA, scorers=True)]
    hits = {m: {"at1": 0.0, "at3": 0.0} for m in methods}
    n = 0

    for weak_point in WEAK_POINTS:
        for seed in SEEDS:
            experiment = run_experiment(
                make_synthetic_agent(weak_point, seed=seed),
                CASES,
                trials=TRIALS,
                outcome=outcome,
                projector=projector(),
                agent_id=f"synthetic:{weak_point}",
            )
            tables = divergence_tables(experiment, comparator="exact")
            n += 1
            for method, method_scores in scores(tables, seed=n).items():
                hits[method]["at1"] += credit_at_k(method_scores, weak_point, 1)
                hits[method]["at3"] += credit_at_k(method_scores, weak_point, 3)

    rows = {
        m: {"at1": hits[m]["at1"] / n, "at3": hits[m]["at3"] / n} for m in methods
    }

    print(f"\nTable 1 — Ground-truth attribution ({n} injected weak points)")
    print("Ties resolved as expected credit under a random tie-break, for every method.\n")
    print(f"{'Method':<20}{'Attribution@1':>16}{'Attribution@3':>16}")
    print("-" * 52)
    for method in methods:
        print(f"{method:<20}{rows[method]['at1']:>16.2f}{rows[method]['at3']:>16.2f}")
    print()

    out = ROOT / "results" / "attribution_ground_truth.json"
    out.write_text(
        json.dumps(
            {
                "agent": "synthetic",
                "weak_points": list(WEAK_POINTS),
                "seeds": list(SEEDS),
                "cases": len(CASES),
                "trials": TRIALS,
                "feature_schema_version": SCHEMA.version,
                "scoring_mode": "V x A x P (ordered schema)",
                "results": rows,
            },
            indent=2,
        )
    )
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
