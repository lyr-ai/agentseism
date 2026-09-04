from agents.gaia import (
    answer_equivalent,
    build_state,
    extract_answer,
    is_correct,
    normalize_answer,
    outcome,
)


def test_formatting_differences_are_the_same_answer():
    assert answer_equivalent("1,000", "1000") == 1.0
    assert answer_equivalent("$5", "5") == 1.0
    assert answer_equivalent("42%", "42") == 1.0
    assert answer_equivalent("3.0", "3") == 1.0
    assert answer_equivalent("the Paris", "Paris") == 1.0
    assert answer_equivalent(" Paris. ", "paris") == 1.0


def test_different_answers_are_not_equivalent():
    assert answer_equivalent("Paris", "Berlin") == 0.0
    assert answer_equivalent("5", "6") == 0.0
    assert answer_equivalent("a, b", "a, b, c") == 0.0


def test_list_answers_get_element_wise_partial_credit():
    assert answer_equivalent("a, b, c", "a, b, d") == 2 / 3
    assert answer_equivalent("a; b", "a, b") == 1.0


def test_normalize_answer_shapes():
    assert normalize_answer("1,000") == [1000.0]
    assert normalize_answer("the cat, 2") == ["cat", 2.0]
    assert normalize_answer(None) == [""]


def test_comparator_is_not_a_grader():
    """Two runs that are identically wrong are behaviorally consistent."""
    assert answer_equivalent("Berlin", "Berlin") == 1.0
    assert is_correct("Berlin", "Paris") is False


def test_extract_answer_prefers_the_submitted_answer():
    state = {
        "final_agent_answer": {"task_id": "t", "agent_answer": " Paris "},
        "messages": [{"role": "assistant", "content": "thinking out loud"}],
    }
    assert extract_answer(state) == "Paris"


def test_extract_answer_falls_back_to_last_message():
    state = {"final_agent_answer": None, "messages": [{"role": "assistant", "content": "Paris"}]}
    assert extract_answer(state) == "Paris"
    assert extract_answer({"messages": []}) == ""


def test_build_state_carries_question_and_prompt():
    state = build_state({"task_id": "t", "question": "why?", "file_name": ""})
    assert state["final_agent_answer"] is None
    assert state["messages"][0]["role"] == "system"
    assert state["messages"][1]["content"] == "why?"


def test_outcome_selects_the_answer():
    assert outcome({"answer": "Paris", "trajectory": {}}) == "Paris"
