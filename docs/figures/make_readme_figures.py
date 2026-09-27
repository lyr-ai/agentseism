"""Generate the README figures from the demo's actual output.

    python docs/figures/make_readme_figures.py

Every number, count and status on these cards comes from running the three
`seism demo` scenarios through the real decision engine. Nothing is typed in
by hand, so the figures cannot drift from what the command prints.
`tests/test_readme_figures.py` fails if the committed SVGs are stale.

Writes light and dark variants; the README picks one with <picture>.
"""

from __future__ import annotations

import sys
import tempfile
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from agentseism import demo  # noqa: E402

SANS = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, "
        "sans-serif")
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

THEMES = {
    "light": dict(bg="#ffffff", card="#ffffff", border="#d0d7de", text="#1f2328",
                  muted="#59636e", faint="#eaeef2", green="#1a7f37",
                  green_bg="#dafbe1", red="#cf222e", red_bg="#ffebe9",
                  amber="#9a6700", amber_bg="#fff8c5", accent="#57606a"),
    "dark": dict(bg="#0d1117", card="#0d1117", border="#30363d", text="#e6edf3",
                 muted="#9198a1", faint="#21262d", green="#3fb950",
                 green_bg="#12261e", red="#f85149", red_bg="#2d1215",
                 amber="#d29922", amber_bg="#2b2111", accent="#9198a1"),
}

STATUS = {  # verdict -> (label, colour key)
    "PASS": ("✓ PASS", "green"),
    "REGRESSION": ("✕ REGRESSION", "red"),
    "INSUFFICIENT_EVIDENCE": ("? NEED EVIDENCE", "amber"),
    "INSUFFICIENT EVIDENCE": ("? NEED EVIDENCE", "amber"),
}


def results() -> list[dict]:
    with tempfile.TemporaryDirectory() as t:
        return [demo.run_scenario(i, s, Path(t))
                for i, s in enumerate(demo.SCENARIOS, 1)]


def pct(x: float) -> str:
    return f"{x:.0%}"


def t(x, y, s, *, size=14, fill, weight=400, font=SANS, anchor="start") -> str:
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">'
            f'{escape(s)}</text>')


def pill(x, y, status: str, c: dict, *, size=13) -> str:
    label, key = STATUS[status]
    w = int(len(label) * size * 0.66) + 22
    return (f'<rect x="{x}" y="{y - size - 4}" width="{w}" height="{size + 13}" '
            f'rx="{(size + 13) // 2}" fill="{c[key + "_bg"]}" '
            f'stroke="{c[key]}" stroke-width="1"/>'
            + t(x + w / 2, y + 1, label, size=size, fill=c[key], weight=600,
                anchor="middle"))


def cells(x, y, done: int, total: int, colour: str, c: dict) -> str:
    out = []
    for i in range(total):
        filled = i < done
        out.append(f'<rect x="{x + i * 20}" y="{y}" width="16" height="16" rx="3" '
                   f'fill="{colour if filled else c["faint"]}" '
                   f'stroke="{colour if filled else c["border"]}" stroke-width="1"/>')
    return "".join(out)


def hero(r: dict, c: dict) -> str:
    """The collapse scenario as a PR check card."""
    d, cap = r["detail"], r["capability"]
    task = cap["fired"][0]
    name = Path(task).stem
    b, k = (int(v) for v in cap["detail"][task]["baseline"].split("/"))
    a, _ = (int(v) for v in cap["detail"][task]["candidate"].split("/"))
    drop = round((d["candidate"] - d["baseline"]) * 100)
    cap_state = "REGRESSION" if cap["fired"] else "PASS"
    W, H = 760, 372
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" role="img" aria-label="AgentSeism PR check: '
         f'broad reliability {r["broad"]}, capability regression {cap_state} '
         f'on {name} {b}/{k} to {a}/{k}">',
         f'<rect width="{W}" height="{H}" fill="{c["bg"]}"/>',
         f'<rect x="12" y="12" width="{W - 24}" height="{H - 24}" rx="12" '
         f'fill="{c["card"]}" stroke="{c["border"]}"/>',
         t(40, 56, "AgentSeism CI", size=20, fill=c["text"], weight=700),
         t(40, 78, "pull request check · 7 tasks × 8 runs per side", size=13,
           fill=c["muted"]),
         pill(W - 190, 60, r["verdict"]["verdict"], c, size=15),
         f'<line x1="40" y1="98" x2="{W - 40}" y2="98" stroke="{c["border"]}"/>',
         t(40, 134, "Overall task success", size=15, fill=c["muted"]),
         t(290, 134, f'{pct(d["baseline"])}  →  {pct(d["candidate"])}', size=20,
           fill=c["text"], weight=600, font=MONO),
         t(W - 40, 134, f"{drop:+d} pts", size=15, fill=c["muted"], font=MONO,
           anchor="end"),
         t(40, 176, "Broad reliability", size=15, fill=c["text"]),
         pill(290, 176, r["broad"], c),
         t(40, 214, "Capability regression", size=15, fill=c["text"]),
         pill(290, 214, cap_state, c),
         f'<rect x="40" y="236" width="{W - 80}" height="62" rx="8" '
         f'fill="{c["red_bg"]}" stroke="{c["border"]}"/>',
         t(58, 262, name, size=15, fill=c["text"], weight=600, font=MONO),
         t(58, 285, "baseline → PR", size=12, fill=c["muted"]),
         cells(290, 249, b, k, c["green"], c),
         t(456, 262, f"{b}/{k}", size=14, fill=c["text"], font=MONO),
         cells(290, 270, a, k, c["red"], c),
         t(456, 283, f"{a}/{k}", size=14, fill=c["red"], weight=600, font=MONO),
         t(40, 330, "The average alone was not conclusive. One capability "
                    "completely broke.", size=15, fill=c["text"], weight=600),
         t(W - 40, 352, "from `seism demo`: synthetic scenario, real decision "
                        "engine", size=11, fill=c["muted"], anchor="end"),
         "</svg>"]
    return "\n".join(s)


def cases(rs: list[dict], c: dict) -> str:
    """The three demo scenarios side by side."""
    W, H, gap = 900, 216, 16
    cw = (W - 24 - 2 * gap) / 3
    titles = ["NORMAL NOISE", "CAPABILITY COLLAPSE", "NOT ENOUGH EVIDENCE"]
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" role="img" aria-label="Three demo scenarios: '
         + ", ".join(f'{ttl.lower()} {r["verdict"]["verdict"]}'
                     for ttl, r in zip(titles, rs)) + '">',
         f'<rect width="{W}" height="{H}" fill="{c["bg"]}"/>']
    for i, (ttl, r, sc) in enumerate(zip(titles, rs, demo.SCENARIOS)):
        x = 12 + i * (cw + gap)
        v = r["verdict"]["verdict"]
        key = STATUS[v][1]
        d, cap = r["detail"], r["capability"]
        if cap["fired"]:
            task = cap["fired"][0]
            dd = cap["detail"][task]
            note = f'{Path(task).stem} {dd["baseline"]} → {dd["candidate"]}'
        elif v == "PASS":
            note = "↕ ordinary run-to-run wobble"
        else:
            note = f"{len(sc.baseline)} tasks × {sc.trials} runs per side"
        s += [f'<rect x="{x}" y="12" width="{cw}" height="{H - 24}" rx="10" '
              f'fill="{c["card"]}" stroke="{c["border"]}"/>',
              f'<rect x="{x}" y="12" width="{cw}" height="5" rx="2" fill="{c[key]}"/>',
              t(x + 20, 50, ttl, size=12, fill=c["muted"], weight=600),
              t(x + 20, 96, f'{pct(d["baseline"])} → {pct(d["candidate"])}',
                size=26, fill=c["text"], weight=600, font=MONO),
              t(x + 20, 122, "task success, baseline → PR", size=12,
                fill=c["muted"]),
              pill(x + 20, 162, v, c, size=13),
              t(x + 20, 188, note, size=13, fill=c["text"], font=MONO)]
    s.append("</svg>")
    return "\n".join(s)


def social(r: dict, c: dict) -> str:
    """GitHub's social preview (1280x640): what a shared link unfurls to.
    Large type, few words, the collapse scenario."""
    d, cap = r["detail"], r["capability"]
    task = cap["fired"][0]
    name = Path(task).stem
    b, k = (int(v) for v in cap["detail"][task]["baseline"].split("/"))
    a, _ = (int(v) for v in cap["detail"][task]["candidate"].split("/"))
    W, H = 1280, 640
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">',
         f'<rect width="{W}" height="{H}" fill="{c["bg"]}"/>',
         t(80, 150, "AgentSeism", size=84, fill=c["text"], weight=700),
         t(84, 215, "CI for stochastic AI agents", size=40, fill=c["muted"]),
         f'<rect x="80" y="280" width="{W - 160}" height="250" rx="18" '
         f'fill="{c["card"]}" stroke="{c["border"]}" stroke-width="2"/>',
         t(130, 350, "Overall", size=30, fill=c["muted"]),
         t(330, 350, f'{pct(d["baseline"])} → {pct(d["candidate"])}', size=40,
           fill=c["text"], weight=600, font=MONO),
         t(130, 410, "Broad", size=30, fill=c["muted"]),
         t(330, 410, STATUS[r["broad"]][0], size=34, fill=c[STATUS[r["broad"]][1]],
           weight=700),
         t(130, 480, name, size=34, fill=c["text"], weight=600, font=MONO),
         t(330, 480, f"{b}/{k} → {a}/{k}", size=40, fill=c["red"], weight=700,
           font=MONO),
         t(W - 130, 480, "✕ REGRESSION", size=46, fill=c["red"], weight=800,
           anchor="end"),
         t(W - 80, 600, "demo scenario · github.com/lyr-ai/agentseism", size=22,
           fill=c["muted"], anchor="end"),
         "</svg>"]
    return "\n".join(s)


def build() -> dict[str, str]:
    rs = results()
    out = {}
    for theme, c in THEMES.items():
        out[f"hero-{theme}.svg"] = hero(rs[1], c)
        out[f"cases-{theme}.svg"] = cases(rs, c)
    out["social-preview.svg"] = social(rs[1], THEMES["dark"])
    return out


if __name__ == "__main__":
    for name, svg in build().items():
        (HERE / name).write_text(svg + "\n")
        print("wrote", HERE / name)
