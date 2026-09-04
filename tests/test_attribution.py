"""Ground-truth localization (DESIGN.md §17, DESIGN-FEATURE-PROJECTION.md §22-§23).

Exactly one execution feature is made consequentially stochastic; no ranker sees
which. These tests are the executable form of the V0 success criterion "our
ranking beats trivial baselines on controlled experiments".
"""

import pytest

from agentseism import divergence_tables, run_experiment
from agentseism.attribution import (
    ORDERED_MODE,
    UNORDERED_MODE,
    BaselineUnavailable,
    available_baselines,
    credit_at_k,
    first_divergence,
    rank_weak_points,
)
from agentseism.features import FeatureSchema, FeatureSpec, ObservationRole
from agents.synthetic import SCHEMA, WEAK_POINTS, make_synthetic_agent, outcome, projector

CASES = ["latency spike", "checkout errors", "slow queries"]


def _tables(weak_point, trials=8, seed=0):
    experiment = run_experiment(
        make_synthetic_agent(weak_point, seed=seed),
        CASES,
        trials=trials,
        outcome=outcome,
        projector=projector(),
        agent_id=f"synthetic:{weak_point}",
    )
    return divergence_tables(experiment, comparator="exact", schema=SCHEMA)


@pytest.mark.parametrize("weak_point", WEAK_POINTS)
def test_attribution_at_1_recovers_injected_feature(weak_point):
    ranked = rank_weak_points(_tables(weak_point), SCHEMA)
    assert ranked[0].name == weak_point, [(w.name, round(w.score, 3)) for w in ranked]
    assert ranked.scoring_mode == ORDERED_MODE


@pytest.mark.parametrize("weak_point", WEAK_POINTS)
def test_decoys_score_far_below_the_injected_feature(weak_point):
    ranked = {w.name: w for w in rank_weak_points(_tables(weak_point), SCHEMA)}
    injected = ranked[weak_point]
    for decoy in ("phrasing", "render"):
        assert ranked[decoy].score < injected.score / 2


def test_negative_control_high_variation_is_not_weakness():
    """The decoys vary more than the real weak point and still score lower."""
    ranked = {w.name: w for w in rank_weak_points(_tables("evidence_selection"), SCHEMA)}
    assert ranked["render"].local_variation > ranked["evidence_selection"].local_variation
    assert ranked["render"].outcome_association < 0.2
    assert ranked["render"].score < ranked["evidence_selection"].score


def test_outcome_observation_is_rejected_by_construction():
    tables = _tables("evidence_selection")
    ranked = rank_weak_points(tables, SCHEMA)
    assert "submitted_answer" not in ranked.names()
    assert ranked.excluded == ["submitted_answer"]
    for baseline in available_baselines(SCHEMA).values():
        assert "submitted_answer" not in baseline(tables, SCHEMA)


def test_first_divergence_baseline_is_fooled_by_an_earlier_decoy():
    tables = _tables("evidence_selection")
    assert first_divergence(tables, SCHEMA)[0] == "phrasing"
    assert rank_weak_points(tables, SCHEMA)[0].name == "evidence_selection"


def test_every_available_baseline_returns_a_full_ranking():
    tables = _tables("hypothesis")
    attributable = {
        c.name
        for columns, _ in tables.values()
        for c in columns
        if SCHEMA.spec(c.name).role is ObservationRole.FEATURE
    }
    for name, baseline in available_baselines(SCHEMA).items():
        ranking = baseline(tables, SCHEMA)
        assert set(ranking) == attributable, name


def test_deterministic_agent_has_no_weak_points():
    def agent(x, trace):
        trace.record("transform", "a", output=x)
        trace.record("decision", "b", output="fixed")
        return "fixed"

    experiment = run_experiment(agent, CASES, trials=4)
    ranked = rank_weak_points(divergence_tables(experiment, comparator="exact"))
    assert all(w.score == 0.0 for w in ranked)


# -- scoring modes and schema contracts --------------------------------------


def test_unordered_schema_scores_without_propagation():
    schema = FeatureSchema(
        version="u/1",
        specs=[FeatureSpec("a"), FeatureSpec("b"), FeatureSpec("out", role=ObservationRole.OUTCOME)],
    )
    assert not schema.ordered

    flip = {"n": 0}

    def agent(x, trace):
        flip["n"] += 1
        answer = "yes" if flip["n"] % 2 else "no"
        trace.record("decision", "a", output=answer)
        trace.record("model_call", "b", output=f"noise {flip['n']}")
        trace.record("final_submission", "out", output=answer)
        return answer

    from agentseism.projection import EventProjector

    experiment = run_experiment(agent, CASES, trials=6, projector=EventProjector(schema))
    ranked = rank_weak_points(
        divergence_tables(experiment, comparator="exact", schema=schema), schema
    )
    assert ranked.scoring_mode == UNORDERED_MODE
    assert all(w.propagation is None for w in ranked)
    assert ranked[0].name == "a"


def test_first_divergence_is_unavailable_without_declared_order():
    schema = FeatureSchema(version="u/1", specs=[FeatureSpec("a"), FeatureSpec("b")])
    assert "first_divergence" not in available_baselines(schema)
    with pytest.raises(BaselineUnavailable):
        first_divergence({}, schema)


def test_correlated_features_are_reported_as_one_family():
    ranked = rank_weak_points(_tables("evidence_selection"), SCHEMA)
    families = ranked.families
    # evidence_selection propagates into hypothesis and decision; they must not
    # be presented as three independent findings.
    assert any(len(members) > 1 for members in families.values())
    representative = next(k for k, v in families.items() if len(v) > 1)
    assert set(families[representative]) <= set(ranked.names())


# -- tie handling -------------------------------------------------------------


def test_credit_at_k_splits_ties():
    scores = {"a": 1.0, "b": 1.0, "c": 0.0}
    assert credit_at_k(scores, "a", 1) == 0.5
    assert credit_at_k(scores, "a", 3) == 1.0
    assert credit_at_k(scores, "c", 1) == 0.0
    assert credit_at_k(scores, "missing", 1) == 0.0


def test_credit_at_k_gives_no_free_win_from_ordering():
    scores = {"a": 0.5, "b": 0.5, "c": 0.5}
    assert credit_at_k(scores, "a", 1) == pytest.approx(1 / 3)
