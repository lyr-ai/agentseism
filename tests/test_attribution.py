"""Ground-truth attribution (DESIGN.md §17).

Exactly one execution point is made consequentially stochastic; the ranker never
sees which. These tests are the executable form of the V0 success criterion
"our ranking beats trivial baselines on controlled experiments".
"""

import pytest

from agentseism import divergence_tables, run_experiment
from agentseism.attribution import BASELINES, rank_weak_points
from agents.synthetic import WEAK_POINTS, make_synthetic_agent, outcome

CASES = ["latency spike", "checkout errors", "slow queries"]


def _tables(weak_point, trials=8, seed=0):
    agent = make_synthetic_agent(weak_point, seed=seed)
    experiment = run_experiment(
        agent, CASES, trials=trials, outcome=outcome, agent_id=f"synthetic:{weak_point}"
    )
    return divergence_tables(experiment, comparator="exact")


@pytest.mark.parametrize("weak_point", WEAK_POINTS)
def test_attribution_at_1_recovers_injected_point(weak_point):
    ranked = rank_weak_points(_tables(weak_point))
    assert ranked[0].key == weak_point, [(w.key, round(w.score, 3)) for w in ranked]


@pytest.mark.parametrize("weak_point", WEAK_POINTS)
def test_decoys_score_far_below_the_injected_point(weak_point):
    ranked = {w.key: w for w in rank_weak_points(_tables(weak_point))}
    injected = ranked[weak_point]
    for decoy in ("phrasing", "render"):
        assert ranked[decoy].score < injected.score / 2


def test_high_local_variation_is_not_weakness():
    """The decoys vary more than the real weak point and still score lower."""
    ranked = {w.key: w for w in rank_weak_points(_tables("evidence_selection"))}
    assert ranked["render"].local_variation > ranked["evidence_selection"].local_variation
    assert ranked["render"].outcome_association < 0.2
    assert ranked["render"].score < ranked["evidence_selection"].score


def test_first_divergence_baseline_is_fooled_by_an_earlier_decoy():
    tables = _tables("evidence_selection")
    assert BASELINES["first_divergence"](tables)[0] == "phrasing"
    assert rank_weak_points(tables)[0].key == "evidence_selection"


def test_largest_diff_baseline_is_fooled_by_a_noisy_point():
    tables = _tables("evidence_selection")
    assert BASELINES["largest_diff"](tables)[0] in ("phrasing", "render")


def test_every_baseline_returns_a_full_ranking():
    tables = _tables("hypothesis")
    keys = {slot.key for slots, _ in tables.values() for slot in slots}
    for name, baseline in BASELINES.items():
        ranking = baseline(tables)
        assert set(ranking) == keys, name
        assert len(ranking) == len(keys), name


def test_deterministic_agent_has_no_weak_points():
    def agent(x, trace):
        trace.record("transform", "a", output=x)
        trace.record("decision", "b", output="fixed")
        return "fixed"

    experiment = run_experiment(agent, CASES, trials=4)
    ranked = rank_weak_points(divergence_tables(experiment, comparator="exact"))
    assert all(w.score == 0.0 for w in ranked)
