"""Is `evidence_set` unidentifiable because of GAIA, or because of how we key it?

Secondary sensitivity analysis over the Week 1 pilot runs. It does **not** change
`gaia-mz/2`: the schema stays content-keyed and the numbers below are not a new
primary metric. It exists to separate two explanations that the pilot cannot
distinguish on its own.

    evidence_content   canonical URL + normalized snippet   (what gaia-mz/2 uses)
    evidence_source    canonical URL only
    evidence_domain    host only

`evidence_content` had contrast 2 out of 23 informative pairs, so its
amplification is not estimable. Two very different things produce that:

1. the agent really does retrieve differently on every repeat, in which case the
   benchmark cannot support feature-level attribution and the answer is a
   different agent;
2. the *representation* is so fine that a repeated behavior never produces a
   repeated observation -- one changed snippet on the same page counts as
   changed evidence -- in which case the answer is a better abstraction, and
   moving to a more complex agent would hit the same wall with free-text
   features.

Coarsening is not free, which is why the domain rung is here. Contrast can
always be manufactured by abstracting until everything looks alike, and a
representation that is repeatable but carries no outcome signal is worthless in
the opposite direction. What we want is the resolution that is repeatable enough
to estimate while still specific enough to separate behaviors.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from agents.gaia import answer_equivalent  # noqa: E402
from agents.gaia_markazhang import TRIMMED, canonical_evidence  # noqa: E402
from agentseism import divergence_tables  # noqa: E402
from agentseism.metrics.comparators import set_similarity  # noqa: E402
from agentseism.types import Experiment  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "gaia_pilot", Path(__file__).with_name("gaia_pilot.py")
)
gp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gp)

ARTIFACT = ROOT / "results" / "gaia_pilot_agentseism_entry_app_experiment.json"


def representations(run) -> dict[str, list[str]]:
    """The same tool output read at three resolutions."""
    content, source, domain = [], [], []
    for event in run.events:
        if event.name != "tools" or str(event.output) == TRIMMED:
            continue
        for item in canonical_evidence(event.output):
            content.append(item)
            try:
                url = json.loads(item).get("url", "")
            except (TypeError, ValueError):
                continue
            if url:
                source.append(url)
                domain.append(urlsplit(url).netloc)
    return {
        "evidence_content": sorted(set(content)),
        "evidence_source": sorted(set(source)),
        "evidence_domain": sorted(set(domain)),
    }


class _Pair:
    def __init__(self, outcome, features):
        self.outcome = outcome
        self.features = features


def main() -> None:
    exp = Experiment.load(str(ARTIFACT))
    derived = {run.id: representations(run) for run in exp.runs if run.events}
    names = ["evidence_content", "evidence_source", "evidence_domain"]

    # Reuse the real outcome divergences; only the evidence feature is re-keyed.
    real = divergence_tables(exp, comparator=answer_equivalent, schema=exp.schema)
    tables, sims = {}, {n: [] for n in names}
    for task, (_columns, pairs) in real.items():
        rebuilt = []
        for pair in pairs:
            a, b = derived.get(pair.run_a), derived.get(pair.run_b)
            if a is None or b is None:
                continue
            feats = {}
            for name in names:
                s = set_similarity(a[name], b[name])
                sims[name].append(s)
                feats[name] = 1.0 - s
            rebuilt.append(_Pair(pair.outcome, feats))
        if rebuilt:
            tables[task] = ([], rebuilt)

    survival = gp.feature_survival(tables)
    base = survival.pop("_base_rate")
    total = survival.pop("_pairs")
    informative = survival.pop("_informative_pairs")
    pvals = gp.within_task_permutation(tables, trials=20000)

    print(f"{total} pairs, {informative} in outcome-varying tasks, "
          f"base rate P(dY>0) = {base:.3f}\n")
    header = (f"{'representation':<20}{'mean sim':>10}{'varies':>8}"
              f"{'contrast':>10}{'S_f':>8}{'A_f':>8}{'p_within':>10}  verdict")
    print(header)
    print("-" * len(header))
    for name in names:
        v = survival.get(name)
        if v is None:
            print(f"{name:<20}{'-':>10}{'never varies':>28}")
            continue
        verdict = (
            "NOT IDENTIFIABLE" if not v["identifiable"]
            else ("identifiable" if v["enough"] else "identifiable, underpowered")
        )
        mean_sim = sum(sims[name]) / len(sims[name])
        print(f"{name:<20}{mean_sim:>10.3f}{v['pairs_with_variation']:>8}"
              f"{v['contrast_pairs']:>10}{v['survival']:>8.3f}"
              f"{v['amplification']:>+8.3f}{pvals.get(name, float('nan')):>10.3f}"
              f"  {verdict}")

    print("\nRead the ladder in both directions: contrast rising down the table is")
    print("the representation becoming repeatable; A_f falling to zero is it")
    print("becoming uninformative. Neither end is a good feature.")

    # Why no resolution produces contrast, per task.
    print(f"\n{'task':<11}{'outcome':>9}{'mean sim':>10}{'pairs sim==1':>14}")
    varying_means, stable_means = [], []
    for task, (_columns, pairs) in sorted(real.items()):
        sims = [
            set_similarity(
                derived[p.run_a]["evidence_source"], derived[p.run_b]["evidence_source"]
            )
            for p in pairs
            if p.run_a in derived and p.run_b in derived
        ]
        if not sims:
            continue
        mean = sum(sims) / len(sims)
        varies = any(p.outcome > 0 for p in pairs)
        (varying_means if varies else stable_means).append(mean)
        print(f"{task[:8]:<11}{'VARIES' if varies else 'stable':>9}{mean:>10.3f}"
              f"{sum(1 for s in sims if s == 1.0):>14}")
    if varying_means and stable_means:
        v = sum(varying_means) / len(varying_means)
        s = sum(stable_means) / len(stable_means)
        print(f"\nmean retrieval similarity, outcome-varying tasks: {v:.3f}")
        print(f"                           outcome-stable  tasks: {s:.3f}")
        print("\nThe two conditions attribution needs are disjoint here: every task")
        print("whose evidence repeats has a stable outcome, and every task whose")
        print("outcome moves retrieves something different almost every run. No")
        print("resolution of the same observation can create a contrast pair out")
        print("of that -- it is a property of the slice, not of the encoding.")


if __name__ == "__main__":
    main()
