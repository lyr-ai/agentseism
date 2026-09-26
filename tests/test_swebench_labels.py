"""The product's SWE-bench label rule, extracted from the research line.

Pinned here so the product no longer depends on `experiments/`: PASS and FAIL
come only from `resolved`, and every other shape of report is a refusal, never
a failure.
"""

from __future__ import annotations

import os

import pytest

from agents.coding import swebench_evaluator as EV
from agents.coding.swebench_labels import UnlabelledDonor, label_from_report
from agentseism.execution import fingerprint

I = "psf__requests-1142"
OK = {"patch_exists": True, "patch_successfully_applied": True}


@pytest.mark.parametrize("resolved,label", [(True, "PASS"), (False, "FAIL")])
def test_resolved_is_the_only_source_of_a_verdict(resolved, label):
    assert label_from_report({I: OK | {"resolved": resolved}}, I) == label


@pytest.mark.parametrize("report,msg", [
    ({}, "no entry"),
    ({I: OK | {"resolved": True, "infra_failure": True}}, "infra_failure"),
    ({I: {"patch_successfully_applied": True, "resolved": True}}, "no patch"),
    ({I: {"patch_exists": True, "resolved": True}}, "did not apply"),
    ({I: OK}, "no 'resolved'"),
])
def test_everything_else_refuses_rather_than_fails(report, msg):
    with pytest.raises(UnlabelledDonor, match=msg):
        label_from_report(report, I)


def test_the_evaluator_uses_the_product_rule_not_the_research_copy():
    assert EV.label_from_report is label_from_report
    assert EV.UnlabelledDonor is UnlabelledDonor


def test_the_fingerprint_ignores_the_research_vllm_lock(tmp_path, monkeypatch):
    """The research line's GPU lock is not the product's dependency lock."""
    monkeypatch.chdir(tmp_path)
    for d in ("inference", "research/inference"):
        os.makedirs(d)
        (tmp_path / d / "requirements-vllm.lock.txt").write_text("vllm==0\n")
    assert fingerprint()["dependency_lock"] == ""
    (tmp_path / "uv.lock").write_text("x\n")
    assert fingerprint()["dependency_lock"] != ""
