"""GAIA slice selection. No network: the loader is exercised elsewhere."""

import json

import pytest

import benchmarks.gaia as gaia

ROWS = [
    {"task_id": "c", "Question": "third?", "Level": 1, "file_name": "", "Final answer": "3"},
    {"task_id": "a", "Question": "first?", "Level": 1, "file_name": "", "Final answer": "1"},
    {"task_id": "b", "Question": "second?", "Level": 1, "file_name": "x.xlsx", "Final answer": "2"},
    {"task_id": "d", "Question": "fourth?", "Level": 1, "file_name": "", "Final answer": "4"},
]


def test_selection_is_deterministic_and_skips_attachments():
    tasks = gaia.select(ROWS, 3)
    assert [t["id"] for t in tasks] == ["a", "c", "d"]
    assert all(not t["input"]["file_name"] for t in tasks)


def test_selection_can_include_attachment_tasks_explicitly():
    tasks = gaia.select(ROWS, 4, require_no_file=False)
    assert [t["id"] for t in tasks] == ["a", "b", "c", "d"]


def test_too_few_matching_tasks_fails_loudly():
    with pytest.raises(ValueError) as err:
        gaia.select(ROWS, 10)
    assert "only 3" in str(err.value)


def test_format_task_carries_reference_answer_as_metadata():
    task = gaia.format_task(ROWS[1])
    assert task["input"]["question"] == "first?"
    assert task["metadata"]["reference_answer"] == "1"
    assert gaia.reference_answers([task]) == {"a": "1"}


def test_spec_records_ids_only_and_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(gaia, "SPEC_DIR", tmp_path)
    tasks = gaia.select(ROWS, 3)
    path = gaia.save_spec(tasks, "pilot")

    saved = json.loads(path.read_text())
    assert saved["task_ids"] == ["a", "c", "d"]
    # No questions, no answers: GAIA is gated, so nothing is vendored here.
    assert "first?" not in path.read_text()
    assert "Final answer" not in path.read_text()

    assert gaia.load_spec("pilot") == ["a", "c", "d"]
    assert [t["id"] for t in gaia.tasks_from_spec(ROWS, "pilot")] == ["a", "c", "d"]


def test_tasks_from_spec_rejects_a_mismatched_row_set(tmp_path, monkeypatch):
    monkeypatch.setattr(gaia, "SPEC_DIR", tmp_path)
    gaia.save_spec(gaia.select(ROWS, 3), "pilot")
    with pytest.raises(ValueError, match="not in the loaded rows"):
        gaia.tasks_from_spec(ROWS[:1], "pilot")


def test_check_access_reports_a_missing_login_distinctly(monkeypatch):
    import huggingface_hub

    def boom():
        raise OSError("no token")

    monkeypatch.setattr(huggingface_hub, "whoami", boom)
    ok, message = gaia.check_access()
    assert not ok
    assert "huggingface-cli login" in message
