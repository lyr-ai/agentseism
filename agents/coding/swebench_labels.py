"""SWE-bench's own verdict for one instance, and nothing else.

The rule is one line of the harness's per-instance report:

    resolved == True   ->  PASS
    resolved == False  ->  FAIL

Everything else is a refusal. An infrastructure failure, a missing entry, a
missing patch, a patch that did not apply, or an absent `resolved` field is
not a correctness verdict, and scoring one as `FAIL` would report
infrastructure noise as a regression. They raise `UnlabelledDonor`, which the
evaluator turns into `invalid`.

Extracted unchanged from the research line's `experiments/coding/c2h_checker`
so the product does not import research code. The rule's behaviour is pinned
by `tests/test_swebench_labels.py`.

Offline: reading a report calls no model and starts no container.
"""

from __future__ import annotations


class UnlabelledDonor(RuntimeError):
    """A report the rule cannot label. Scored `invalid`, never a failure, and
    never labelled by hand."""


def label_from_report(report: dict, instance: str) -> str:
    """`resolved` -> PASS / FAIL. Anything else refuses."""
    body = report.get(instance)
    if body is None:
        raise UnlabelledDonor(f"report has no entry for {instance!r}")
    if body.get("infra_failure"):
        raise UnlabelledDonor("infra_failure: not a correctness verdict")
    if not body.get("patch_exists", False):
        raise UnlabelledDonor("no patch: nothing was evaluated")
    if not body.get("patch_successfully_applied", False):
        raise UnlabelledDonor("patch did not apply: not a correctness verdict")
    if "resolved" not in body:
        raise UnlabelledDonor("report has no 'resolved' field")
    return "PASS" if body["resolved"] else "FAIL"
