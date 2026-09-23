"""The evaluator report is the evidence; the boolean is derived from it.

`evaluator_resolved` says only true or false. The per-instance report carries
`resolved`, `patch_successfully_applied`, `infra_failure` and `tests_status` --
everything that separates a genuine FAIL from an undecided one. A run that kept
the boolean and lost the report would hold a verdict nobody could audit.

Scope: preservation only. No verdict logic changes here.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot, pilot_protocol as P
from agentseism import real_backend as RB

CELL = {"order_index": 3, "task": "pytest-dev__pytest-10051", "arm": "M1",
        "replicate": 1}
REPORT = {"pytest-dev__pytest-10051": {
    "patch_exists": True, "patch_successfully_applied": True,
    "infra_failure": False, "resolved": False,
    "tests_status": {"FAIL_TO_PASS": {"success": [], "failure": ["t::a"]},
                     "PASS_TO_PASS": {"success": ["t::b"], "failure": []}}}}


def cfg(tmp_path):
    return RB.BackendConfig(image_digests={}, work_dir=tmp_path / "backend",
                            run_dir=tmp_path, model_base_url="u",
                            model_name="m", model_revision="r")


def source_report(tmp_path) -> Path:
    p = tmp_path / "harness" / "report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(REPORT, indent=2) + "\n")
    return p


# 1. normal preservation, byte for byte
def test_the_report_is_preserved_verbatim(tmp_path):
    src = source_report(tmp_path)
    rel, sha = RB.preserve_report(CELL, src, cfg(tmp_path))
    dest = tmp_path / rel
    assert dest.read_bytes() == src.read_bytes(), "not byte-identical"
    assert sha == hashlib.sha256(src.read_bytes()).hexdigest()
    assert Path(str(dest) + ".sha256").read_text().split()[0] == sha


def test_the_name_matches_the_cell_artifact_one_to_one(tmp_path):
    rel, _ = RB.preserve_report(CELL, source_report(tmp_path), cfg(tmp_path))
    assert Path(rel).name == "run_03_pytest-dev__pytest-10051_M1_r1.report.json"
    # the artifact `freeze()` writes for the same cell
    assert Path(rel).stem.replace(".report", "") == \
        f"run_{CELL['order_index']:02d}_{CELL['task']}_{CELL['arm']}_r{CELL['replicate']}"


def test_the_recorded_path_is_relative_to_the_run_directory(tmp_path):
    rel, _ = RB.preserve_report(CELL, source_report(tmp_path), cfg(tmp_path))
    assert not Path(rel).is_absolute()
    assert (tmp_path / rel).is_file(), "the relative path must resolve from the run dir"


def _artifact(tmp_path, rel, sha, **over):
    out = tmp_path
    d = {"order_index": CELL["order_index"], "evaluator_report": rel,
         "evaluator_report_sha256": sha}
    d.update(over)
    return out, d


# 2. a tampered report
def test_a_modified_report_is_not_a_completed_cell(tmp_path):
    rel, sha = RB.preserve_report(CELL, source_report(tmp_path), cfg(tmp_path))
    out, d = _artifact(tmp_path, rel, sha)
    assert pilot.verify_evaluator_evidence(out, d) is True
    (tmp_path / rel).write_text(json.dumps(
        {**REPORT, "pytest-dev__pytest-10051":
            {**REPORT["pytest-dev__pytest-10051"], "resolved": True}}))
    assert pilot.verify_evaluator_evidence(out, d) is False


def test_a_truncated_report_is_not_a_completed_cell(tmp_path):
    rel, sha = RB.preserve_report(CELL, source_report(tmp_path), cfg(tmp_path))
    out, d = _artifact(tmp_path, rel, sha)
    (tmp_path / rel).write_bytes((tmp_path / rel).read_bytes()[:-20])
    assert pilot.verify_evaluator_evidence(out, d) is False


# 3. a tampered digest
def test_a_modified_digest_is_not_a_completed_cell(tmp_path):
    rel, sha = RB.preserve_report(CELL, source_report(tmp_path), cfg(tmp_path))
    out, d = _artifact(tmp_path, rel, sha)
    Path(str(tmp_path / rel) + ".sha256").write_text("0" * 64 + "\n")
    assert pilot.verify_evaluator_evidence(out, d) is False


def test_a_digest_edited_to_match_a_changed_report_still_fails(tmp_path):
    """Both must agree with the artifact's own recorded digest, so editing the
    pair together does not launder the change."""
    rel, sha = RB.preserve_report(CELL, source_report(tmp_path), cfg(tmp_path))
    out, d = _artifact(tmp_path, rel, sha)
    body = b'{"tampered": true}\n'
    (tmp_path / rel).write_bytes(body)
    Path(str(tmp_path / rel) + ".sha256").write_text(
        hashlib.sha256(body).hexdigest() + "\n")
    assert pilot.verify_evaluator_evidence(out, d) is False


# 4. a missing report
def test_a_missing_report_is_not_a_completed_cell(tmp_path):
    rel, sha = RB.preserve_report(CELL, source_report(tmp_path), cfg(tmp_path))
    out, d = _artifact(tmp_path, rel, sha)
    (tmp_path / rel).unlink()
    assert pilot.verify_evaluator_evidence(out, d) is False


def test_a_missing_digest_is_not_a_completed_cell(tmp_path):
    rel, sha = RB.preserve_report(CELL, source_report(tmp_path), cfg(tmp_path))
    out, d = _artifact(tmp_path, rel, sha)
    Path(str(tmp_path / rel) + ".sha256").unlink()
    assert pilot.verify_evaluator_evidence(out, d) is False


# 5. a cell whose evaluator never ran
def test_a_cell_without_an_evaluator_run_fabricates_nothing(tmp_path):
    out, d = _artifact(tmp_path, "", "")
    assert pilot.verify_evaluator_evidence(out, d) is True


def test_a_half_recorded_pair_is_refused(tmp_path):
    out, d = _artifact(tmp_path, "evaluator_reports/x.report.json", "")
    assert pilot.verify_evaluator_evidence(out, d) is False
    out, d = _artifact(tmp_path, "", "a" * 64)
    assert pilot.verify_evaluator_evidence(out, d) is False


def test_the_schema_refuses_evidence_on_a_run_that_never_graded():
    r = {"agent_termination_code": P.COMPLETED,
         "infrastructure_status": RB.INFRA_TIMEOUT_1200S,
         "evaluator_resolved": None, "challenge_status": "FIRED",
         "challenge_record": None, "recovered": None,
         "hint_sha256": P.HINT_SHA256["full"], "step_limit": 250,
         "image_digest": "i@sha256:" + "a" * 64,
         "registered_model_id": "m", "transport_model": "openai/m",
         "api_base": "u", "transport_attempts": 1,
         "model_revision": "r", "evaluator_report_path": "",
         "evaluator_report": "evaluator_reports/x.report.json",
         "evaluator_report_sha256": "a" * 64,
         "n_calls": 1, "elapsed_seconds": 1.0}
    r["outcome_state"] = RB.outcome_state(r["infrastructure_status"], None)
    r["enters_pilot_outcome"] = RB.ENTERS_PILOT_OUTCOME[r["outcome_state"]]
    r["termination"] = RB.registered_termination(
        P.COMPLETED, r["infrastructure_status"], None)
    with pytest.raises(ValueError) as e:
        RB.validate_result(r)
    assert "nothing is fabricated" in str(e.value)


# 6. survives retrieval and re-verification
def test_the_evidence_reverifies_after_a_copy(tmp_path):
    """A retrieval bundle is a copy; the digests must still hold on the far
    side, which is where an artifact-only bundle would be found wanting."""
    import shutil
    rel, sha = RB.preserve_report(CELL, source_report(tmp_path), cfg(tmp_path))
    far = tmp_path / "retrieved"
    shutil.copytree(tmp_path / "evaluator_reports", far / "evaluator_reports")
    out, d = _artifact(far, rel, sha)
    assert pilot.verify_evaluator_evidence(far, d) is True
    assert (far / rel).read_bytes() == (tmp_path / rel).read_bytes()


def test_completed_cells_rejects_a_cell_with_broken_evidence(tmp_path):
    """The resume path, end to end: a cell whose report no longer verifies is
    re-run rather than counted."""
    out = tmp_path
    (out / "runs").mkdir(parents=True)
    rel, sha = RB.preserve_report(CELL, source_report(tmp_path), cfg(tmp_path))
    art = out / "runs" / "run_03_pytest-dev__pytest-10051_M1_r1.json"
    body = json.dumps({"order_index": 3, "evaluator_report": rel,
                       "evaluator_report_sha256": sha},
                      indent=2, sort_keys=True)
    art.write_text(body)
    Path(str(art) + ".sha256").write_text(
        hashlib.sha256(body.encode()).hexdigest() + "\n")
    assert 3 in pilot.completed_cells(out)
    (out / rel).write_text("{}")
    assert 3 not in pilot.completed_cells(out), "a broken report was counted"
