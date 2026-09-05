"""Amplification is only estimable with within-task contrast.

Both traps these tests pin were found on real pilot data, not constructed:
a feature that varies on every informative pair is not identifiable however
many runs are added, and a null that shuffles across tasks reports such a
feature as significant because it is measuring task identity.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "gaia_pilot", ROOT / "experiments" / "natural_variation" / "gaia_pilot.py"
)
gp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gp)


class _Pair:
    def __init__(self, outcome, features):
        self.outcome = outcome
        self.features = features


def _tables(spec):
    """{task: (columns, pairs)} from {task: [(outcome, {feature: divergence})]}."""
    return {t: ([], [_Pair(o, f) for o, f in rows]) for t, rows in spec.items()}


def test_feature_varying_on_every_pair_is_not_identifiable():
    tables = _tables({
        "t1": [(1, {"always": 1.0}), (0, {"always": 1.0}), (1, {"always": 1.0})],
    })
    out = gp.feature_survival(tables)
    assert out["always"]["contrast_pairs"] == 0
    assert out["always"]["identifiable"] is False


def test_contrast_makes_it_identifiable():
    tables = _tables({
        "t1": [(1, {"f": 1.0}), (0, {"f": 0.0}), (1, {"f": 1.0}), (0, {"f": 0.0})],
    })
    out = gp.feature_survival(tables)
    assert out["f"]["contrast_pairs"] == 2
    assert out["f"]["identifiable"] is True
    assert out["f"]["survival"] == pytest.approx(1.0)
    assert out["f"]["held_still_rate"] == pytest.approx(0.0)
    # Risk difference between the arms, not against the marginal rate: the
    # marginal here is 0.5, which would have halved a perfect effect.
    assert out["f"]["amplification"] == pytest.approx(1.0)


def test_enough_is_bounded_by_the_smaller_side():
    """Many varying pairs against a handful of contrast pairs is a small estimate."""
    rows = [(1, {"f": 1.0})] * 40 + [(0, {"f": 0.0})] * 3
    out = gp.feature_survival(_tables({"t1": rows}), min_pairs=20)
    assert out["f"]["pairs_with_variation"] == 40
    assert out["f"]["contrast_pairs"] == 3
    assert out["f"]["enough"] is False


def test_contrast_counted_only_where_the_outcome_varies():
    """A task whose outcome never moves offers nothing to condition against."""
    tables = _tables({
        "stable": [(0, {"f": 0.0}), (0, {"f": 1.0})],
        "varying": [(1, {"f": 1.0}), (0, {"f": 1.0})],
    })
    out = gp.feature_survival(tables)
    assert out["f"]["contrast_pairs"] == 0
    assert out["f"]["identifiable"] is False


def test_within_task_permutation_returns_one_without_contrast():
    tables = _tables({
        "t1": [(1, {"always": 1.0}), (0, {"always": 1.0}), (1, {"always": 1.0})],
    })
    p = gp.within_task_permutation(tables, trials=500)
    assert p["always"] == pytest.approx(1.0)


def test_cross_task_structure_does_not_become_significance():
    """The trap: the feature varies only in the task whose outcome varies.

    Pooling pairs across tasks makes this look like a strong association. Holding
    the task fixed shows there is nothing to see -- inside each task, the feature
    does not distinguish the pairs at all.
    """
    tables = _tables({
        "varies": [(1, {"f": 1.0}), (1, {"f": 1.0}), (1, {"f": 1.0})],
        "stable_a": [(0, {"f": 0.0}), (0, {"f": 0.0}), (0, {"f": 0.0})],
        "stable_b": [(0, {"f": 0.0}), (0, {"f": 0.0}), (0, {"f": 0.0})],
    })
    out = gp.feature_survival(tables)
    # Under the risk difference the illusion cannot even be computed: the
    # feature never holds still inside the task whose outcome moves, so the
    # second arm is empty and there is nothing to subtract.
    assert out["f"]["contrast_pairs"] == 0
    assert out["f"]["identifiable"] is False
    assert out["f"]["amplification"] is None
    assert out["f"]["survival"] == pytest.approx(1.0), "survival alone still looks total"
    assert gp.within_task_permutation(tables, trials=500)["f"] == pytest.approx(1.0)
