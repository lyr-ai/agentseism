"""Provider addressing and the retry policy (amendment P.8).

Host 3 reached the container and then failed on `LLM Provider NOT provided`,
having spent a GPU and 31 GB of weights to find out. Every check here is free.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P
from agentseism import real_backend as RB

MODEL = "Qwen/Qwen3.6-27B-FP8"


def cfg(**over):
    kw = dict(image_digests={}, work_dir=Path("."),
              model_base_url="http://127.0.0.1:8000/v1",
              model_name=MODEL, model_revision="e89b16eb")
    kw.update(over)
    return RB.BackendConfig(**kw)


# ── the address ──
def test_the_registered_id_gets_the_provider_prefix():
    assert P.transport_model(MODEL) == "openai/Qwen/Qwen3.6-27B-FP8"


def test_the_registered_id_itself_is_unchanged():
    """The server serves the bare id and `--model` still says so."""
    import yaml
    cfgy = yaml.safe_load(Path("inference/configs/model_h2.yaml").read_text())
    assert cfgy["model"]["id"] == MODEL
    assert not cfgy["model"]["id"].startswith("openai/")


def test_prefixing_twice_is_refused():
    with pytest.raises(ValueError) as e:
        P.transport_model("openai/" + MODEL)
    assert "already carries the provider prefix" in str(e.value)


def test_an_empty_id_is_refused():
    with pytest.raises(ValueError):
        P.transport_model("")


# ── the regression that host 3 cost a GPU to find ──
def test_a_bare_model_id_reaching_the_transport_is_caught_before_renting():
    """The whole point: this is now reachable without an instance."""
    out = RB._check_transport(cfg())
    assert out["transport_model"].startswith("openai/")
    assert out["registered_model_id"] == MODEL
    assert out["requests_sent"] == 0


@pytest.mark.parametrize("prefixed", [
    "openai/" + MODEL, "hosted_vllm/" + MODEL, "huggingface/" + MODEL])
def test_an_already_prefixed_config_is_refused(prefixed):
    with pytest.raises(RB.BackendUnavailable) as e:
        RB._check_transport(cfg(model_name=prefixed))
    assert "already carries a provider prefix" in str(e.value)


def test_a_missing_endpoint_is_refused():
    with pytest.raises(RB.BackendUnavailable) as e:
        RB._check_transport(cfg(model_base_url="127.0.0.1:8000"))
    assert "is not an endpoint" in str(e.value)


def test_a_missing_api_key_field_is_refused():
    with pytest.raises(RB.BackendUnavailable) as e:
        RB._check_transport(cfg(api_key=""))
    assert "even a dummy" in str(e.value)


def test_an_empty_model_id_is_refused():
    with pytest.raises(RB.BackendUnavailable):
        RB._check_transport(cfg(model_name=""))


def test_the_check_sends_nothing(monkeypatch):
    import litellm
    monkeypatch.setattr(litellm, "completion",
                        lambda *a, **k: pytest.fail("a request was sent"))
    assert RB._check_transport(cfg())["requests_sent"] == 0


# ── the retry policy ──
def test_every_knob_is_pinned_to_zero():
    for knob, value in P.RETRY_KNOBS.items():
        assert value in (0, None), f"{knob} is {value!r}"
    assert P.RETRY_KNOBS["num_retries"] == 0
    assert P.RETRY_KNOBS["max_retries"] == 0
    assert P.TRANSPORT_ATTEMPTS == 1


def test_a_non_zero_knob_fails_constructibility(monkeypatch):
    monkeypatch.setitem(P.RETRY_KNOBS, "num_retries", 3)
    with pytest.raises(RB.BackendUnavailable) as e:
        RB._check_transport(cfg())
    assert "registered as 3, not 0" in str(e.value)


def test_litellm_still_exposes_the_knobs_we_pin():
    """If a later version drops one, the policy cannot be applied and this
    fails rather than the knob silently doing nothing."""
    import litellm
    params = set(inspect.signature(litellm.completion).parameters)
    for knob, value in P.RETRY_KNOBS.items():
        if value is None:
            continue
        assert knob in params or "kwargs" in params, knob


def test_the_knobs_reach_the_model_config(monkeypatch):
    """Behavioural: what run_cell hands to the model carries the policy."""
    seen = {}

    class FakeModel:
        pass

    def fake_get_model(name, config=None):
        seen["name"] = name
        seen["cfg"] = config
        return FakeModel()

    import minisweagent.models as M
    monkeypatch.setattr(M, "get_model", fake_get_model)
    monkeypatch.setattr(RB, "_problem_statement", lambda t, c: "task")
    import minisweagent.environments as E
    monkeypatch.setattr(E, "get_environment", lambda c, **k: object())

    class Boom(RuntimeError):
        pass

    def fake_agent(*a, **k):
        raise Boom("stop after construction")
    import minisweagent.agents.default as D
    monkeypatch.setattr(D, "DefaultAgent", type("A", (), {
        "__init__": fake_agent, "step": lambda s: None}))
    with pytest.raises(Exception):
        RB._agent_result({"task": "t", "step_limit": 250, "hint": "full"},
                         cfg(), P.HINTS["full"], "img@sha256:" + "a" * 64)
    assert seen["name"] == "openai/" + MODEL
    kw = seen["cfg"]["model_kwargs"]
    assert kw["num_retries"] == 0 and kw["max_retries"] == 0
    assert kw["api_base"] == "http://127.0.0.1:8000/v1"
    assert kw["api_key"] == "not-needed"


# ── the artifact keeps the three facts apart ──
def test_the_result_records_id_address_and_endpoint_separately():
    assert "registered_model_id" in RB.REQUIRED_RESULT_FIELDS
    assert "transport_model" in RB.REQUIRED_RESULT_FIELDS
    assert "api_base" in RB.REQUIRED_RESULT_FIELDS
    assert "transport_attempts" in RB.REQUIRED_RESULT_FIELDS


def test_the_policy_is_inside_the_protocol_hash():
    before = P.protocol_hash()
    P.RETRY_KNOBS["num_retries"] = 5
    try:
        assert P.protocol_hash() != before
    finally:
        P.RETRY_KNOBS["num_retries"] = 0
    assert P.protocol_hash() == before


def test_the_order_hash_is_unmoved_by_p8():
    assert P.ORDER_HASH == "cfe8856c9c9167b5"
    assert P.order_hash(P.build_order()) == P.ORDER_HASH


def test_constructibility_refuses_if_the_retry_variable_is_unread(monkeypatch):
    """If a later mini-swe-agent stops reading it, the policy is inert and
    that must fail rather than pass quietly."""
    monkeypatch.setitem(P.RETRY_ENV, "MSWEA_NO_SUCH_VARIABLE", "1")
    monkeypatch.delitem(P.RETRY_ENV, "MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT")
    with pytest.raises(RB.BackendUnavailable) as e:
        RB._check_transport(cfg())
    assert "would be set and have no effect" in str(e.value)


def test_constructibility_refuses_more_than_one_attempt(monkeypatch):
    monkeypatch.setitem(P.RETRY_ENV, "MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", "3")
    with pytest.raises(RB.BackendUnavailable) as e:
        RB._check_transport(cfg())
    assert "not '1'" in str(e.value)


def test_the_dry_run_report_carries_the_env_policy():
    out = RB._check_transport(cfg())
    assert out["retry_env"] == {"MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT": "1"}
    assert out["requests_sent"] == 0
