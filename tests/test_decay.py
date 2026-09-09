"""The decay estimator, on cases where the right answer is known by construction.

Every test here corresponds to a mistake that was actually made. The state
measure reported perfect agreement over a stretch where nobody had edited
anything; a shared empty diff counted as agreement, which is the same defect the
30-run analysis had already corrected once; and the naive survival ratio rose
from 0.75 to 0.86 when a continuation that had already diverged ran out of steps.
"""

import hashlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("decay_mod", ROOT / "experiments/coding/decay.py")
decay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(decay)

EMPTY = hashlib.sha256(b"").hexdigest()
S = "forkstate"


def row(command="ls", state=S):
    return {"command": command, "tracked_diff_hash": state}


def run(name, rows):
    return {"name": name, "rows": rows}


class TestStateInformativeness:
    def test_undefined_while_the_donor_still_holds_the_fork_state(self):
        """Both sides sitting on S means neither has edited, not that they agree."""
        assert decay.compare("state", row(state=S), row(state=S), S, raw=False) == decay.NA

    def test_undefined_when_the_donor_holds_an_empty_diff(self):
        """Agreement on having no changes is where every run begins.

        The same exclusion the 30-run analysis needed, which was not carried
        into the horizon measure until it produced a plateau of 1.00.
        """
        assert decay.compare("state", row(state=EMPTY), row(state=EMPTY), S, raw=False) == decay.NA

    def test_raw_mode_still_reports_them(self):
        """The uncorrected measure is kept, so the size of the correction shows."""
        assert decay.compare("state", row(state=S), row(state=S), S, raw=True) == decay.MATCH

    def test_informativeness_is_decided_by_the_donor_alone(self):
        """A continuation still on S, against a donor that has moved, is a miss.

        Letting the continuation's own state make the comparison undefined would
        make the denominator depend on what is being measured.
        """
        assert decay.compare("state", row(state="edited"), row(state=S), S, raw=False) == decay.MISS

    def test_a_real_shared_state_counts(self):
        assert decay.compare("state", row(state="edited"), row(state="edited"), S,
                             raw=False) == decay.MATCH


class TestGranularity:
    def test_signature_ignores_arguments_and_command_does_not(self):
        a, b = row("sed -n '1,5p' f"), row("sed -n '90,99p' g")
        assert decay.compare("signature", a, b, S, raw=False) == decay.MATCH
        assert decay.compare("command", a, b, S, raw=False) == decay.MISS


class TestSurvival:
    def test_censoring_a_dead_run_does_not_raise_survival(self):
        """The exact failure the sanity check caught on real data.

        Two continuations, one diverging at h=1 and then ending. A ratio of
        survivors to those still present rises from 0.5 to 1.0 when the dead one
        drops out; conditioning on the risk set does not.
        """
        after = [row("a"), row("b"), row("c")]
        series = [run("dead", [row("x")]), run("alive", [row("a"), row("b"), row("c")])]
        points = decay.arm_curves(after, series, S)["command"]
        survivals = [p["survival"] for p in points]
        assert survivals == sorted(survivals, reverse=True)
        assert survivals[0] == 0.5

    def test_survival_is_monotone_and_pointwise_is_not(self):
        """Diverge, come back, diverge again -- the topology of the 30-run study."""
        after = [row("a"), row("b"), row("c"), row("d")]
        series = [run("wobble", [row("a"), row("X"), row("c"), row("Y")])]
        points = decay.arm_curves(after, series, S)["command"]
        assert [p["pointwise"] for p in points] == [1.0, 0.0, 1.0, 0.0]
        assert [p["survival"] for p in points] == [1.0, 0.0, 0.0, 0.0]

    def test_survival_is_undefined_until_something_is_judged(self):
        """No plateau of 1.00 built out of comparisons that were never made."""
        after = [row("a", S), row("b", S)]
        series = [run("c", [row("a", S), row("b", S)])]
        points = decay.arm_curves(after, series, S)["state"]
        assert [p["survival"] for p in points] == [None, None]
        assert [p["n_informative"] for p in points] == [0, 0]
