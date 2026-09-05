"""The multi-node GAIA adapter, including the history-rewriting trap."""

import pytest

from agentseism import scan
from agents.gaia import answer_equivalent
from agents.gaia_markazhang import (
    SCHEMA,
    GaiaGraphProjector,
    extract_answer,
    make_build_state,
    outcome,
)
from agents.langgraph_adapter import LangGraphAgent
from agents.stub_gaia_graph import TRIMMED, StubGaiaGraphApp

CASES = [
    {"id": f"g{i}", "input": {"task_id": f"g{i}", "question": f"question {i}", "file_name": ""}}
    for i in range(3)
]


def _agent(app=None, **kwargs):
    return LangGraphAgent(
        app or StubGaiaGraphApp(),
        build_state=make_build_state(),
        extract_answer=extract_answer,
        **kwargs,
    )


def _scan(app=None, trials=6, **kwargs):
    return scan(
        _agent(app),
        CASES,
        trials=trials,
        outcome=outcome,
        comparator=answer_equivalent,
        projector=GaiaGraphProjector(),
        agent_id="stub-gaia-graph",
        **kwargs,
    )


def test_stream_capture_keeps_evidence_that_final_state_loses():
    """memory_management overwrites earlier tool results with 'removed'."""
    app = StubGaiaGraphApp(seed=1, detour_prob=1.0, retry_prob=0.0)
    final_state = app.invoke(make_build_state()(CASES[0]["input"]))
    trimmed = [m for m in final_state["messages"] if m.get("content") == TRIMMED]
    assert trimmed, "the stub must reproduce the trimming behaviour"

    report = _scan(StubGaiaGraphApp(seed=1, detour_prob=1.0, retry_prob=0.0), trials=2)
    evidence = [r.features["evidence_set"].value for r in report.experiment.runs]
    assert all(len(e) == 2 for e in evidence), evidence
    assert all(TRIMMED not in e for e in evidence)


def test_projector_refuses_a_final_state_only_trace():
    """Reading this graph without streaming is an error, not a quiet bad number."""
    agent = _agent(StubGaiaGraphApp(), capture="invoke")
    with pytest.raises(ValueError, match="stream capture"):
        scan(
            agent,
            CASES[:1],
            trials=1,
            outcome=outcome,
            projector=GaiaGraphProjector(),
            on_error="raise",
        )


def test_projection_fills_the_declared_schema():
    report = _scan(trials=4)
    for run in report.experiment.runs:
        assert set(run.features) == {s.name for s in SCHEMA.specs}
        assert run.features["termination"].value == "output_formatter"
        assert run.features["tool_call_count"].value >= 1


def test_raw_answer_and_formatted_answer_are_kept_apart():
    """The formatter rewrites the answer; that must not look like agent variation."""
    report = _scan(trials=4)
    run = report.experiment.runs[0]
    raw = run.features["raw_final_answer"].value
    formatted = run.features["final_answer"].value
    assert raw.startswith("answer")
    assert formatted != raw  # the formatter rewrote "answer-0" as "answer 0"
    # ...but the GAIA comparator calls them the same answer, so the rewrite is
    # recorded as a formatting change, not as agent variation.
    assert answer_equivalent(raw, formatted) == 1.0
    assert run.features["formatter_changed_answer"].value is False


def test_both_answer_observations_are_excluded_from_ranking():
    """raw_final_answer is the outcome before formatting; ranking it says nothing."""
    report = _scan(trials=6)
    ranked = {w.name for w in report.weak_points}
    assert "final_answer" not in ranked
    assert "raw_final_answer" not in ranked
    assert set(report.ranking.excluded) == {"final_answer", "raw_final_answer"}
    assert "raw_final_answer" in report.render()


def test_answer_format_retries_are_counted():
    report = _scan(StubGaiaGraphApp(seed=3, retry_prob=1.0), trials=3)
    assert all(r.features["answer_format_retries"].value == 1 for r in report.experiment.runs)

    clean = _scan(StubGaiaGraphApp(seed=3, retry_prob=0.0), trials=3)
    assert all(r.features["answer_format_retries"].value == 0 for r in clean.experiment.runs)


def test_refusal_is_recorded_as_a_distinct_termination():
    report = _scan(StubGaiaGraphApp(seed=5, refusal_prob=1.0), trials=3)
    assert all(
        r.features["termination"].value == "return_llm_refusal"
        for r in report.experiment.runs
    )


def test_schema_splits_positioned_features_from_aggregates():
    assert SCHEMA.positioned_names == ["initial_plan", "evidence_set", "pre_final_reasoning"]
    assert set(SCHEMA.aggregate_names) == {
        "formatter_changed_answer", "tool_set", "tool_sequence", "tool_call_count",
        "answer_format_retries", "termination",
    }
    assert set(SCHEMA.outcome_names) == {"final_answer", "raw_final_answer"}


def test_scan_localizes_the_consequential_choice():
    report = _scan(trials=8)
    assert report.consistency < 1.0
    assert report.ranking.positioned[0].name == "evidence_set"
    assert report.ranking.aggregates[0].name in ("tool_set", "tool_sequence")


# --- gaia-mz/2: evidence semantics, not response serialization -------------

def _search_response(results, **transport):
    body = {"query": "q", "follow_up_questions": None, "results": results}
    body.update({"request_id": "req-0", "response_time": 0.5, **transport})
    return body


def _result(url, content, **noise):
    body = {"url": url, "title": "T", "content": content, "id": "res-0", "score": 0.5}
    body.update(noise)
    return body


def _canon(response):
    from agents.gaia_markazhang import canonical_evidence

    return set(canonical_evidence(response))


def test_transport_metadata_does_not_create_evidence_divergence():
    """The gaia-mz/1 defect: a fresh request_id per call made equality impossible."""
    docs = [_result("https://a.test/x", "hello")]
    first = _search_response(docs, request_id="uuid-1", response_time=0.7)
    second = _search_response(
        [_result("https://a.test/x", "hello", id="res-9")],
        request_id="uuid-2",
        response_time=9.9,
    )
    assert first != second, "the raw responses genuinely differ"
    assert _canon(first) == _canon(second)


def test_provider_ranking_is_not_evidence():
    same_docs_reranked = _search_response([_result("https://a.test/x", "hello", score=0.99)])
    assert _canon(_search_response([_result("https://a.test/x", "hello")])) == _canon(
        same_docs_reranked
    )


def test_different_documents_still_diverge():
    a = _canon(_search_response([_result("https://a.test/x", "hello")]))
    b = _canon(_search_response([_result("https://b.test/y", "different")]))
    assert a != b
    assert not (a & b)


def test_partial_overlap_is_partial():
    a = _canon(_search_response([_result("https://a.test/x", "1"), _result("https://a.test/y", "2")]))
    b = _canon(_search_response([_result("https://a.test/x", "1"), _result("https://a.test/z", "3")]))
    assert 0 < len(a & b) < len(a | b)


def test_url_canonicalization_keeps_query_but_not_case_or_trailing_slash():
    a = _canon(_search_response([_result("https://WWW.YouTube.com/watch?v=abc", "c")]))
    b = _canon(_search_response([_result("https://www.youtube.com/watch?v=abc", "c")]))
    assert a == b
    other = _canon(_search_response([_result("https://www.youtube.com/watch?v=different", "c")]))
    assert a != other, "the query string is document identity here, not noise"


def test_non_search_tool_output_passes_through():
    from agents.gaia_markazhang import canonical_evidence

    assert canonical_evidence("stdout: 42") == ["stdout: 42"]
    assert canonical_evidence("  spaced   out  ") == ["spaced out"]


def test_schema_version_records_the_change():
    assert SCHEMA.version == "gaia-mz/2"
