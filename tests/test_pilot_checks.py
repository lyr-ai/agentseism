"""The pilot's own sanity machinery.

These cover the two things that must be verified before any real number is
trusted: that `evidence_set` holds tool output, and that `answer_format_retries`
counts what it claims to.
"""

import importlib.util
from pathlib import Path

from agentseism import scan
from agents.gaia import answer_equivalent
from agents.gaia_markazhang import GaiaGraphProjector, extract_answer, make_build_state, outcome
from agents.langgraph_adapter import LangGraphAgent
from agents.stub_gaia_graph import StubGaiaGraphApp

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    {"id": f"g{i}", "input": {"task_id": f"g{i}", "question": f"question {i}", "file_name": ""}}
    for i in range(3)
]


def _pilot():
    spec = importlib.util.spec_from_file_location(
        "gaia_pilot", ROOT / "experiments" / "natural_variation" / "gaia_pilot.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(app=None, trials=6):
    return scan(
        LangGraphAgent(
            app or StubGaiaGraphApp(),
            build_state=make_build_state(),
            extract_answer=extract_answer,
        ),
        CASES,
        trials=trials,
        outcome=outcome,
        comparator=answer_equivalent,
        projector=GaiaGraphProjector(),
    )


def test_projected_evidence_matches_the_raw_tool_events():
    """Sanity check 1, automated: evidence is tool output, not a wrapper repr."""
    report = _report(StubGaiaGraphApp(seed=7, detour_prob=1.0))
    for run in report.experiment.runs:
        raw = {str(e.output) for e in run.events if e.name == "tools"}
        raw.discard("removed")
        assert set(run.features["evidence_set"].value) == raw
        assert all(not v.startswith("{") for v in run.features["evidence_set"].value)


def test_retry_count_matches_the_raw_check_events():
    """Sanity check 2, automated: retries are rejections, not all check visits."""
    report = _report(StubGaiaGraphApp(seed=11, retry_prob=1.0))
    for run in report.experiment.runs:
        rejections = [
            e for e in run.events
            if e.name == "check_and_get_final_answer" and e.metadata.get("role") != "model"
        ]
        assert run.features["answer_format_retries"].value == len(rejections)
        assert len(rejections) == 1


def test_diagnostics_detect_a_formatter_that_introduces_variation():
    pilot = _pilot()
    report = _report(StubGaiaGraphApp(seed=13, branch_prob=0.0, detour_prob=0.0,
                                      retry_prob=0.0, formatter_error_prob=0.5))
    d = pilot.diagnostics(report)
    # The agent itself is deterministic here; only the formatter varies.
    assert d["raw_answer_consistency"] == 1.0
    assert d["formatted_answer_consistency"] < 1.0
    assert d["formatter_changed_rate"] > 0


def test_diagnostics_report_a_formatter_that_changes_nothing():
    pilot = _pilot()
    d = pilot.diagnostics(_report())
    assert d["formatter_changed_rate"] == 0.0
    assert d["raw_answer_consistency"] == d["formatted_answer_consistency"]


def test_inspect_prints_raw_next_to_projected(capsys):
    pilot = _pilot()
    pilot.inspect_runs(_report(trials=2), limit=1)
    printed = capsys.readouterr().out
    assert "RAW TRACE vs PROJECTION" in printed
    assert "raw `tools` events" in printed
    assert "projected evidence_set" in printed
    assert "projected answer_format_retries" in printed
