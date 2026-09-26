"""Gates on the frozen C2 plan.

The counts are asserted rather than documented because a README saying 72 does
not stop a loop from producing 96, and because horizon 20 was removed late —
exactly the kind of change that leaves a stale path behind.
"""

import importlib.util
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "c2_protocol", ROOT / "experiments/coding/c2_protocol.py")
c2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c2)


class TestPlanShape:
    def test_exact_counts(self):
        specs = c2.expand()
        by_arm = Counter(s["arm"] for s in specs)
        assert by_arm["FAIL"] == 4 * 3 * 4 == 48
        assert by_arm["PASS"] == 4 * 3 * 2 == 24
        assert len(specs) == 72

    def test_horizons_are_the_registered_ones(self):
        assert c2.HORIZONS == [16, 24, 28]
        assert 20 not in c2.HORIZONS
        assert {s["horizon"] for s in c2.expand()} == {16, 24, 28}

    def test_every_cell_is_filled(self):
        cells = Counter((s["arm"], s["source_run_id"], s["horizon"]) for s in c2.expand())
        assert set(cells.values()) == {4, 2}
        for arm, runs in (("FAIL", c2.FAIL_RUNS), ("PASS", c2.PASS_RUNS)):
            for run in runs:
                for h in c2.HORIZONS:
                    assert cells[(arm, run, h)] == c2.REPLICATES[arm]

    def test_run_ids_are_unique_and_deterministic(self):
        first = [s["run_id"] for s in c2.expand()]
        assert len(set(first)) == len(first)
        assert first == [s["run_id"] for s in c2.expand()]

    def test_archive_step_translates_the_donor_prefix(self):
        """A replayed continuation numbers its archive from its own step 1."""
        specs = {s["run_id"]: s for s in c2.expand()}
        assert specs["c2__FAIL__r4__h16__k0"]["archive_step"] == 16
        assert specs["c2__FAIL__A_3__h16__k0"]["archive_step"] == 8    # fork at 8
        assert specs["c2__FAIL__B_0__h16__k0"]["archive_step"] == 6    # fork at 10

    def test_budget_is_equal_across_arms_at_a_horizon(self):
        for h in c2.HORIZONS:
            budgets = {s["step_limit"] for s in c2.expand() if s["horizon"] == h}
            assert budgets == {250 - h}

    def test_sampling_is_not_seeded(self):
        assert c2.SAMPLING["seed"] is None

    def test_protocol_hash_is_stable(self):
        assert c2.protocol_hash() == c2.protocol_hash()
        assert len(c2.protocol_hash()) == 16
