"""Moved out of tests/test_contract.py when the research line moved under
research/: it regenerates the old docs/demo reports from research data."""

from pathlib import Path


def test_the_demo_reports_are_reproducible_from_frozen_data():
    """The two shipped demos regenerate byte-identically, so the README cannot
    drift from the artifacts it claims to be computed from."""
    import subprocess
    before = {p: p.read_text() for p in
              [Path("docs/demo/pr-report-pass-with-change.md"),
               Path("docs/demo/pr-report-incomparable.md")]}
    r = subprocess.run([".venv-eval/bin/python",
                        "experiments/coding/make_demo_reports.py"],
                       capture_output=True, text=True,
                       env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    for p, text in before.items():
        assert p.read_text() == text
