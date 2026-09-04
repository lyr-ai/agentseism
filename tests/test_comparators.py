from agentseism.metrics import exact, jaccard, numeric, resolve_comparator, structured


def test_exact():
    assert exact("a", "a") == 1.0
    assert exact("a", "b") == 0.0


def test_jaccard_is_bounded_and_symmetric():
    assert jaccard("the cat sat", "the cat sat") == 1.0
    assert jaccard("the cat", "a dog") == 0.0
    assert 0 < jaccard("the cat sat", "the cat ran") < 1
    assert jaccard("a b", "b a") == jaccard("b a", "a b")


def test_numeric_distance():
    assert numeric(10, 10) == 1.0
    assert numeric(0, 100) == 0.0
    assert 0 < numeric(90, 100) < 1


def test_structured_compares_fields():
    a = {"decision": "escalate", "score": 0.9}
    b = {"decision": "escalate", "score": 0.9}
    c = {"decision": "ignore", "score": 0.1}
    assert structured(a, b) == 1.0
    assert structured(a, c) < 0.5
    assert structured([1, 2, 3], [1, 2]) < 1.0


def test_structured_does_not_confuse_bool_and_int():
    assert structured({"x": True}, {"x": 1}) == 0.0


def test_resolve_comparator():
    assert resolve_comparator(None) is structured
    assert resolve_comparator("exact") is exact
    assert resolve_comparator(lambda a, b: 1.0)("x", "y") == 1.0
    try:
        resolve_comparator("nope")
    except ValueError as err:
        assert "nope" in str(err)
    else:
        raise AssertionError("expected ValueError")
