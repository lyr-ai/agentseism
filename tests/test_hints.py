"""The M2 mutation is a string, and it is frozen (amendment P.5).

`hint: "error_only"` was a label with no referent: the registration named the
mutation but no template existed anywhere in the tree. Whoever wrote the
backend would have chosen how much text to remove, which is choosing M2's
effect size at implementation time.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P

GUIDANCE = "Here is general guidance on how to submit correct toolcalls:"


def test_both_templates_hash_to_their_registered_digests():
    for name, text in P.HINTS.items():
        assert hashlib.sha256(text.encode()).hexdigest() == P.HINT_SHA256[name]


def test_verify_hints_passes_against_the_pinned_upstream():
    P.verify_hints()


def test_the_frozen_full_is_the_pinned_upstream_byte_for_byte():
    import os

    import minisweagent
    import yaml
    path = os.path.join(os.path.dirname(minisweagent.__file__),
                        "config/benchmarks/swebench.yaml")
    assert yaml.safe_load(open(path))["model"]["format_error_template"] \
        == P.HINTS["full"]


def test_the_two_differ_only_by_the_guidance_block():
    full, only = P.HINTS["full"], P.HINTS["error_only"]
    assert GUIDANCE in full and GUIDANCE not in only
    # everything before the guidance is identical
    head = full.split(GUIDANCE)[0].rstrip("\n ")
    assert only.startswith(head)
    # and what remains after it is just the branch close
    assert only[len(head):].strip() == "{%- endif %}"


def test_the_finish_reason_branch_is_untouched():
    """M2 removes recovery guidance, not the truncation message."""
    branch = P.HINTS["full"].split("{%- else -%}")[0]
    assert P.HINTS["error_only"].startswith(branch)
    assert "output token limit" in P.HINTS["error_only"]


def test_error_only_still_says_what_went_wrong():
    only = P.HINTS["error_only"]
    assert "Tool call error:" in only and "{{error}}" in only


def test_error_only_says_nothing_about_how_to_recover():
    only = P.HINTS["error_only"].lower()
    for phrase in ("general guidance", "call the bash tool with your command",
                   "your_command_here", "needs to use the 'bash' tool"):
        assert phrase not in only


def test_every_registered_arm_names_a_frozen_hint():
    for arm, spec in P.ARMS.items():
        assert spec["hint"] in P.HINTS, f"{arm} names an unfrozen hint"


def test_the_hint_text_is_inside_the_protocol_hash():
    before = P.protocol_hash()
    P.HINT_SHA256["error_only"] = "0" * 64
    try:
        assert P.protocol_hash() != before
    finally:
        P.HINT_SHA256["error_only"] = hashlib.sha256(
            P.HINTS["error_only"].encode()).hexdigest()
    assert P.protocol_hash() == before


def test_the_order_hash_is_unmoved_by_p5():
    assert P.ORDER_HASH == "cfe8856c9c9167b5"
    assert P.order_hash(P.build_order()) == P.ORDER_HASH


def test_a_tampered_frozen_template_fails_closed(monkeypatch):
    monkeypatch.setitem(P.HINTS, "error_only", P.HINTS["error_only"] + " ")
    with pytest.raises(P.ProtocolMismatch):
        P.verify_hints()


def test_a_reworded_upstream_fails_closed_rather_than_adapting(monkeypatch):
    """A newer mini-swe-agent is a different experiment, not a text to match."""
    monkeypatch.setitem(P.HINTS, "full", P.HINTS["full"].replace(
        "Tool call error:", "Tool-call error:"))
    monkeypatch.setitem(P.HINT_SHA256, "full", hashlib.sha256(
        P.HINTS["full"].encode()).hexdigest())
    with pytest.raises(P.ProtocolMismatch) as e:
        P.verify_hints()
    assert "different experiment" in str(e.value)


def test_the_source_of_full_is_recorded():
    s = P.UPSTREAM_HINT_SOURCE
    assert s["package"] == "mini-swe-agent==2.4.6"
    assert s["key"] == "model.format_error_template"
    assert len(s["file_sha256"]) == 64


def test_the_transform_rule_is_recorded_alongside_the_result():
    """A rule without the bytes would let a different upstream produce a
    different mutation under the same registration."""
    assert "Here is general guidance" in P.HINT_TRANSFORM
    assert "finish_reason" in P.HINT_TRANSFORM
