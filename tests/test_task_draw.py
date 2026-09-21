"""The registered task draw (amendment P.3).

The rule may only look at three things: the ascending id order, the registered
exclusion, and whether an image pulls. Nothing here may depend on how long a
pull took, how hard a task looks, or which instance anyone would prefer.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P
from agentseism.task_draw import image_for, main


def ids(*specs):
    """`ids(("astropy", 3), ("django", 2))` -> ascending ids for those repos."""
    out = []
    for repo, n in specs:
        out += [f"{repo}__{repo}-{1000 + i}" for i in range(n)]
    return sorted(out)


ALL_PULL = lambda _: True          # noqa: E731


# ── the rule ──
def test_a_repository_that_fills_the_head_of_the_list_does_not_fill_the_draw():
    """Version 1's defect: sorted ascending, one repository holds enough of the
    head to take all three slots."""
    candidates = ids(("astropy", 20), ("django", 5), ("matplotlib", 5))
    drawn, rows = P.select_tasks(candidates, ALL_PULL)
    assert len(drawn) == 3
    assert [P.repository_of(i) for i in drawn] == \
           ["astropy__astropy", "django__django", "matplotlib__matplotlib"]


def test_the_drawn_repositories_are_distinct():
    candidates = ids(("astropy", 9), ("django", 9), ("sympy", 9))
    drawn, _ = P.select_tasks(candidates, ALL_PULL)
    assert len({P.repository_of(i) for i in drawn}) == len(drawn) == 3


def test_it_keeps_scanning_past_a_whole_repository():
    candidates = ids(("astropy", 40), ("django", 1), ("sympy", 1))
    drawn, rows = P.select_tasks(candidates, ALL_PULL)
    skipped = [i for i, r in rows if r == "duplicate_repository"]
    assert len(skipped) == 39, "every later astropy instance is examined"
    assert drawn[0].startswith("astropy")


def test_every_duplicate_is_recorded_not_merely_passed_over():
    candidates = ids(("astropy", 5), ("django", 5), ("sympy", 5))
    drawn, rows = P.select_tasks(candidates, ALL_PULL)
    seen = dict()
    for i, r in rows:
        seen.setdefault(r, []).append(i)
    # 3 selected, and every candidate examined before the third is accounted for.
    assert len(seen["selected"]) == 3
    assert len(seen["duplicate_repository"]) == len(rows) - 3
    assert set(seen["selected"]) | set(seen["duplicate_repository"]) == \
           {i for i, _ in rows}


def test_the_registered_exclusion_is_recorded_with_its_own_reason():
    candidates = sorted(["pytest-dev__pytest-10051"] + ids(("astropy", 1),
                                                           ("django", 1),
                                                           ("sympy", 1)))
    drawn, rows = P.select_tasks(candidates, ALL_PULL)
    assert ("pytest-dev__pytest-10051", "excluded_registered") in rows
    assert "pytest-dev__pytest-10051" not in drawn


def test_a_failed_pull_is_recorded_and_the_scan_continues_in_order():
    candidates = ids(("astropy", 3), ("django", 3), ("sympy", 1))
    dead = {candidates[0], candidates[3]}
    drawn, rows = P.select_tasks(candidates, lambda i: i not in dead)
    assert [i for i, r in rows if r == "pull_failed"] == sorted(dead)
    # The next id of the same repository is taken, not a later repository.
    assert P.repository_of(drawn[0]) == "astropy__astropy"
    assert drawn[0] == candidates[1]


def test_too_few_repositories_fails_closed():
    candidates = ids(("astropy", 30), ("django", 4))
    with pytest.raises(P.ProtocolMismatch) as e:
        P.select_tasks(candidates, ALL_PULL)
    assert "not relaxed" in str(e.value)


def test_an_exhausted_scan_never_falls_back_to_a_second_task_from_one_repository():
    candidates = ids(("astropy", 50))
    with pytest.raises(P.ProtocolMismatch):
        P.select_tasks(candidates, ALL_PULL)


def test_the_repository_check_before_the_pull_cannot_change_the_draw():
    """The ordering is an efficiency decision, so it has to be provably inert."""
    def pull_first(candidates, pull, wanted=3):
        drawn, repos = [], set()
        for iid in candidates:
            if len(drawn) == wanted:
                break
            if iid in P.EXCLUDED_INSTANCES or not pull(iid):
                continue
            r = P.repository_of(iid)
            if r in repos:
                continue
            drawn.append(iid); repos.add(r)
        return drawn

    candidates = sorted(ids(("astropy", 12), ("django", 8), ("sympy", 4))
                        + ["pytest-dev__pytest-10051"])
    for dead in ({}, {candidates[0]}, set(candidates[:3]), set(candidates[::3])):
        pull = lambda i, d=dead: i not in d     # noqa: E731
        assert P.select_tasks(candidates, pull)[0] == pull_first(candidates, pull)


def test_nothing_but_order_exclusion_repository_and_pull_can_move_the_draw():
    """Shuffling how slow or how 'hard' a candidate is changes nothing: the
    rule is never given either fact."""
    candidates = ids(("astropy", 6), ("django", 6), ("sympy", 6))
    baseline, _ = P.select_tasks(candidates, ALL_PULL)
    calls: list[str] = []

    def slow_and_hard(i):
        calls.append(i)
        return True

    again, _ = P.select_tasks(candidates, slow_and_hard)
    assert again == baseline
    # and the rule asked about candidates strictly in ascending order
    assert calls == sorted(calls)


# ── repository parsing ──
@pytest.mark.parametrize("iid,repo", [
    ("astropy__astropy-12907", "astropy__astropy"),
    ("pytest-dev__pytest-10051", "pytest-dev__pytest"),
    ("scikit-learn__scikit-learn-10297", "scikit-learn__scikit-learn"),
])
def test_repository_of(iid, repo):
    assert P.repository_of(iid) == repo


def test_an_unparseable_id_raises_rather_than_counting_as_its_own_repository():
    with pytest.raises(ValueError):
        P.repository_of("not-an-instance")


# ── the hashes ──
def test_the_selection_rule_is_inside_the_protocol_hash():
    before = P.protocol_hash()
    P.TASK_SELECTION["wanted"] = 4
    try:
        assert P.protocol_hash() != before
    finally:
        P.TASK_SELECTION["wanted"] = P.TASK_COUNT
    assert P.protocol_hash() == before


def test_the_order_hash_binds_positions_not_ids():
    """P.3 changes which tasks are drawn, so this is the test that says the
    18-cell plan is untouched by that."""
    assert P.ORDER_HASH == "cfe8856c9c9167b5"
    assert P.order_hash(P.build_order()) == P.ORDER_HASH
    for names in (["task_1", "task_2", "task_3"],
                  ["astropy__astropy-12907", "django__django-10914",
                   "matplotlib__matplotlib-13989"],
                  ["zzz", "yyy", "xxx"]):
        assert P.order_hash(P.build_order(names)) == P.ORDER_HASH


# ── the driver ──
def test_image_names_match_the_registry_form():
    assert image_for("pytest-dev__pytest-10051") == \
        "docker.io/swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-10051:latest"
    # only the first `__` is the separator
    assert image_for("a__b__c-1").endswith("a_1776_b__c-1:latest")


def test_the_driver_records_every_examined_candidate(tmp_path, monkeypatch):
    import agentseism.task_draw as td
    candidates = sorted(ids(("astropy", 4), ("django", 2), ("sympy", 1))
                        + ["pytest-dev__pytest-10051"])
    (tmp_path / "u.txt").write_text("\n".join(candidates) + "\n")
    dead = {candidates[0]}
    monkeypatch.setattr(td, "docker_pull", lambda i, m: i not in dead)

    rc = main(["--universe", str(tmp_path / "u.txt"),
               "--tsv", str(tmp_path / "d.tsv"),
               "--drawn", str(tmp_path / "drawn.txt")])
    assert rc == 0
    drawn = (tmp_path / "drawn.txt").read_text().split()
    assert len({P.repository_of(i) for i in drawn}) == 3
    body = (tmp_path / "d.tsv").read_text().splitlines()
    reasons = [l.split("\t")[3] for l in body[1:]]
    assert reasons.count("selected") == 3
    assert reasons.count("pull_failed") == 1
    assert "duplicate_repository" in reasons
    assert "excluded_registered" in reasons


def test_the_driver_fails_closed_and_still_writes_the_record(tmp_path, monkeypatch):
    import agentseism.task_draw as td
    candidates = ids(("astropy", 6), ("django", 2))
    (tmp_path / "u.txt").write_text("\n".join(candidates) + "\n")
    monkeypatch.setattr(td, "docker_pull", lambda i, m: True)
    rc = main(["--universe", str(tmp_path / "u.txt"),
               "--tsv", str(tmp_path / "d.tsv"),
               "--drawn", str(tmp_path / "drawn.txt")])
    assert rc == 1
    assert (tmp_path / "drawn.txt").read_text() == ""
    body = (tmp_path / "d.tsv").read_text()
    assert "draw_failed" in body
    # The reasons survive the failure: without them the record cannot say why
    # three repositories were not found.
    rows = [l.split("\t") for l in body.splitlines()[1:] if not l.startswith("#")]
    assert len(rows) == len(candidates), "every candidate examined is recorded"
    assert [r[3] for r in rows].count("duplicate_repository") == 6
    assert [r[3] for r in rows].count("selected") == 2


def test_the_driver_issues_one_pull_per_candidate_it_asks_about(tmp_path, monkeypatch):
    import agentseism.task_draw as td
    candidates = ids(("astropy", 3), ("django", 1), ("sympy", 1))
    (tmp_path / "u.txt").write_text("\n".join(candidates) + "\n")
    seen: list[str] = []

    def once(i, m):
        assert i not in seen, f"{i} pulled twice"
        seen.append(i)
        return True

    monkeypatch.setattr(td, "docker_pull", once)
    assert main(["--universe", str(tmp_path / "u.txt"),
                 "--tsv", str(tmp_path / "d.tsv"),
                 "--drawn", str(tmp_path / "drawn.txt")]) == 0
    # the two later astropy instances are skipped on the id alone, never pulled
    assert seen == [candidates[0], candidates[3], candidates[4]]


def test_dry_run_touches_nothing(tmp_path, monkeypatch):
    import agentseism.task_draw as td
    (tmp_path / "u.txt").write_text("\n".join(ids(("a", 2), ("b", 1), ("c", 1))) + "\n")
    monkeypatch.setattr(td, "docker_pull",
                        lambda *a: pytest.fail("dry run must not pull"))
    assert main(["--universe", str(tmp_path / "u.txt"),
                 "--tsv", str(tmp_path / "d.tsv"),
                 "--drawn", str(tmp_path / "drawn.txt"), "--dry-run"]) == 0
    assert not (tmp_path / "d.tsv").exists()
    assert not (tmp_path / "drawn.txt").exists()
