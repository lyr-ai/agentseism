"""Decision-level extraction for the OpenRCA scaffold, frozen as openrca/1."""

import pytest

from agents.openrca import (
    SCHEMA,
    named_components,
    parse_prediction,
    project_decisions,
    telemetry_kinds,
)


def _prompt(*instructions):
    return {
        "messages": [{"role": "system", "content": "..."}]
        + [
            {"role": "assistant", "content": f'{{"analysis": "a", "completed": "False", "instruction": "{t}"}}'}
            for t in instructions
        ]
    }


def test_parenthesised_examples_are_not_commitments():
    """The trap that shifted the first run's commit two steps early.

    `(e.g., Tomcat04-OSLinux-CPU...)` names a component to show a format, not to
    investigate it.
    """
    text = "Aggregate each KPI to obtain series (e.g., Tomcat04-OSLinux-CPU_CPUCpuUtil)."
    assert named_components(text) == []


def test_a_real_mention_still_counts():
    assert named_components("Load the trace data and filter for IG01.") == ["IG01"]


def test_commit_step_is_the_first_single_component_instruction():
    p = _prompt(
        "Load metric_container.csv and list KPIs.",
        "Compute the global P95 threshold for each component-KPI.",
        "Analyse the trace data for IG01 within the window.",
    )
    assert project_decisions(p)["commit_step"] == 3
    assert project_decisions(p)["service_focus"] == "IG01"


def test_no_commit_is_reported_as_minus_one():
    p = _prompt("Compute thresholds.", "Filter the window.")
    d = project_decisions(p)
    assert d["commit_step"] == -1
    assert d["service_focus"] == ""


def test_candidate_width_is_the_last_multi_candidate_instruction():
    p = _prompt(
        "Inspect apache02, Tomcat02, Mysql01 and IG01 for anomalies.",
        "Analyse the logs for Tomcat02.",
    )
    d = project_decisions(p)
    assert d["candidate_width"] == 4
    assert d["commit_step"] == 2


def test_committing_without_a_wide_step_reports_width_one():
    p = _prompt("Analyse the logs for Tomcat02.")
    assert project_decisions(p)["candidate_width"] == 1


def test_telemetry_path_collapses_consecutive_repeats():
    p = _prompt(
        "Load the metric files.",
        "Aggregate the metric series.",
        "Analyse the trace data.",
        "Analyse the log data for Tomcat02.",
        "Analyse the log data again.",
    )
    assert project_decisions(p)["telemetry_path"] == ["metric", "trace", "log"]


def test_telemetry_kinds_are_ordered_not_alphabetical():
    assert telemetry_kinds("check the log then the metric") == ["metric", "log"]


def test_prediction_parses_into_three_outcome_fields():
    raw = ('{"1": {"root cause occurrence datetime": "2021-03-06 18:29:00", '
           '"root cause component": "IG01", "root cause reason": "network packet loss"}}')
    assert parse_prediction(raw) == {
        "component": "IG01",
        "reason": "network packet loss",
        "occurrence": "2021-03-06 18:29:00",
    }


def test_unparseable_prediction_is_empty_not_an_error():
    assert parse_prediction("the agent refused")["component"] == ""


def test_schema_version_is_frozen():
    assert SCHEMA.version == "openrca/1"


@pytest.mark.parametrize("name", ["commit_step", "candidate_width", "telemetry_path", "service_focus"])
def test_decision_features_precede_the_outcome_in_the_schema(name):
    """Decision-level features are declared features; the answer fields are outcomes."""
    spec = next(s for s in SCHEMA.specs if s.name == name)
    assert spec.role.name == "FEATURE"


def test_proximal_features_are_excluded_per_outcome_not_globally():
    from agents.openrca import analysable_features

    names = ["commit_step", "candidate_width", "telemetry_path", "service_focus"]
    assert "service_focus" not in analysable_features("component", names)
    assert "service_focus" in analysable_features("reason", names)
    assert "service_focus" in analysable_features("occurrence", names)


def test_proximity_agreement_audits_a_declaration():
    from agents.openrca import proximity_agreement

    runs = [
        {"service_focus": "A", "component": "A"},
        {"service_focus": "B", "component": "B"},
        {"service_focus": "A", "component": "A"},
    ]
    out = proximity_agreement(runs, "service_focus", "component")
    assert out["identical_value_rate"] == 1.0
    assert out["codivergence_rate"] == 1.0
    assert out["declared_proximal"] is True


def test_a_non_proximal_pair_is_reported_as_undeclared():
    from agents.openrca import proximity_agreement

    runs = [{"commit_step": 6, "reason": "x"}, {"commit_step": 8, "reason": "x"}]
    assert proximity_agreement(runs, "commit_step", "reason")["declared_proximal"] is False


# --- early_commit, frozen for the Telecom confirmation --------------------

def test_early_commit_when_the_component_is_named_in_the_trace_request():
    """The discovery-set shape: chosen from metrics, trace gathered to confirm."""
    p = _prompt(
        "Compute the global P95 thresholds.",
        "Load the trace data and filter for IG01 in the window.",
    )
    from agents.openrca import early_commit

    assert early_commit(p) is True


def test_not_early_when_traces_come_first():
    from agents.openrca import early_commit

    p = _prompt(
        "Compute the global P95 thresholds.",
        "Analyse the trace data for the faulty components.",
        "Analyse the logs for Tomcat02.",
    )
    assert early_commit(p) is False


def test_committing_without_ever_consulting_traces_is_early():
    from agents.openrca import early_commit

    p = _prompt("Compute thresholds.", "Analyse the logs for Tomcat02.")
    assert early_commit(p) is True


def test_never_narrowing_is_not_an_early_commitment():
    from agents.openrca import early_commit

    p = _prompt("Compute thresholds.", "Analyse the trace data broadly.")
    assert early_commit(p) is False
