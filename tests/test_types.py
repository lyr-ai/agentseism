import json

from agentseism.features import ExecutionFeature, FeatureSchema, FeatureSpec, ObservationRole
from agentseism.types import Event, Experiment, Run, Task


def test_experiment_roundtrip(tmp_path):
    experiment = Experiment(
        id="e1",
        agent_id="agent",
        tasks=[Task(id="t0", input={"q": "why"})],
        runs=[
            Run(
                id="t0:0",
                task_id="t0",
                input={"q": "why"},
                output={"answer": "a"},
                outcome="a",
                events=[Event(id="t0:0:0", run_id="t0:0", event_type="model_call", name="plan", output="p")],
                features={"plan": ExecutionFeature(name="plan", value="p")},
            )
        ],
        schema=FeatureSchema(
            version="t/1",
            specs=[
                FeatureSpec("plan", comparator="text"),
                FeatureSpec("check", predecessors=("plan",)),
                FeatureSpec("answer", role=ObservationRole.OUTCOME),
            ],
        ),
        config={"trials": 1},
    )
    path = experiment.save(str(tmp_path / "exp.json"))
    loaded = Experiment.load(path)

    assert loaded.id == "e1"
    assert loaded.tasks[0].input == {"q": "why"}
    assert loaded.runs[0].events[0].name == "plan"
    assert loaded.runs[0].features["plan"].value == "p"
    assert loaded.runs_for("t0") == loaded.runs


def test_schema_survives_persistence(tmp_path):
    schema = FeatureSchema(
        version="t/1",
        specs=[
            FeatureSpec("a", comparator=lambda x, y: 1.0),
            FeatureSpec("b", predecessors=("a",)),
            FeatureSpec("out", role=ObservationRole.OUTCOME),
        ],
    )
    path = Experiment(id="e", agent_id="a", schema=schema).save(str(tmp_path / "e.json"))
    loaded = Experiment.load(path)

    assert loaded.schema.version == "t/1"
    assert loaded.schema.positioned_names == ["a", "b"]
    assert loaded.schema.successors("a") == ["b"]
    assert loaded.schema.outcome_names == ["out"]
    # A callable comparator cannot be persisted; it is dropped, not faked.
    assert loaded.schema.spec("a").comparator is None


def test_save_tolerates_non_json_output(tmp_path):
    experiment = Experiment(
        id="e1",
        agent_id="agent",
        runs=[Run(id="r", task_id="t", input=None, output=object(), outcome=None)],
    )
    path = experiment.save(str(tmp_path / "exp.json"))
    assert isinstance(json.loads(open(path).read())["runs"][0]["output"], str)


def test_failed_run_is_not_ok():
    assert not Run(id="r", task_id="t", input=None, output=None, outcome=None, error="boom").ok
