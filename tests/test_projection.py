import pytest

from agentseism import EventProjector, ObservationRole, run_experiment
from agentseism.alignment import align_features
from agentseism.features import MISSING, FeatureSchema, FeatureSpec, schema_from_names
from agentseism.projection import project_run
from agentseism.types import Run


class _Projector:
    name = "fake"
    version = "fake/1"
    schema = FeatureSchema(version="fake/1", specs=[FeatureSpec("a"), FeatureSpec("b")])

    def __init__(self, values):
        self.values = values

    def project(self, run):
        return self.values


def _run():
    return Run(id="r", task_id="t", input=None, output=None, outcome="x")


def test_project_run_wraps_values_as_features():
    features = project_run(_run(), _Projector({"a": 1, "b": 2}))
    assert features["a"].value == 1
    assert features["a"].name == "a"


def test_undeclared_feature_is_a_schema_freeze_violation():
    with pytest.raises(ValueError) as err:
        project_run(_run(), _Projector({"a": 1, "surprise": 2}))
    assert "surprise" in str(err.value)
    assert "fake/1" in str(err.value)


def test_declared_but_absent_feature_aligns_as_missing():
    schema = _Projector.schema
    run = _run()
    run.features = project_run(run, _Projector({"a": 1}))
    columns = {c.name: c for c in align_features([run], schema)}
    assert columns["b"].value("r") is MISSING
    assert columns["b"].coverage == 0.0


def test_event_projector_infers_a_schema_from_recorded_names():
    def agent(x, trace):
        trace.record("transform", "start", output=x)
        trace.record("decision", "decide", output="d")
        return "d"

    experiment = run_experiment(agent, ["q"], trials=2)
    assert experiment.schema.feature_names == ["start", "decide"]
    assert experiment.config["adapter"] == "events"
    assert experiment.config["feature_schema_version"] == experiment.schema.version


def test_event_projector_honours_a_declared_schema_and_roles():
    schema = FeatureSchema(
        version="declared/1",
        specs=[
            FeatureSpec("start"),
            FeatureSpec("check", predecessors=("start",)),
            FeatureSpec("answer", role=ObservationRole.OUTCOME),
        ],
    )

    def agent(x, trace):
        trace.record("transform", "start", output=x)
        trace.record("decision", "check", output="ok")
        trace.record("final_submission", "answer", output="a")
        return "a"

    experiment = run_experiment(agent, ["q"], trials=2, projector=EventProjector(schema))
    assert experiment.schema.version == "declared/1"
    assert experiment.schema.has_precedence
    assert experiment.schema.positioned_names == ["start", "check"]
    assert experiment.schema.outcome_names == ["answer"]


def test_schema_rejects_duplicate_names():
    with pytest.raises(ValueError):
        FeatureSchema(version="x", specs=[FeatureSpec("a"), FeatureSpec("a")])


def test_schema_from_names_marks_outcomes():
    schema = schema_from_names(["a", "final"], outcome=["final"])
    assert schema.feature_names == ["a"]
    assert schema.outcome_names == ["final"]
    assert not schema.has_precedence
