"""The README's figures are generated from the demo's real output. If the demo
or the engine changes, the committed SVGs must be regenerated, or this fails."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "make_readme_figures", ROOT / "docs/figures/make_readme_figures.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def test_the_committed_figures_match_what_the_demo_produces():
    for name, svg in M.build().items():
        assert (ROOT / "docs/figures" / name).read_text() == svg + "\n", (
            f"{name} is stale: run python docs/figures/make_readme_figures.py")


def test_every_relative_link_in_the_readme_resolves():
    import re
    text = (ROOT / "README.md").read_text()
    for target in re.findall(r'(?:\]\(|srcset="|src=")([^)"#]+)', text):
        if target.startswith("http"):
            continue
        assert (ROOT / target).exists(), target
