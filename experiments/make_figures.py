"""Build all figures from the saved experiment results and the Graphviz sources.

Usage:  python experiments/make_figures.py
Writes PDFs to paper/figures/ (for LaTeX) and PNGs to docs/figures/ (for the README).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "experiments" / "results"
PAPER = ROOT / "paper" / "figures"
DOCS = ROOT / "docs" / "figures"

# Validated categorical palette (slots 1-3); hatching adds a non-color channel for print.
METHODS = [("fixed38", "Fixed 38.0 °C", "#2a78d6", ""),
           ("fixed37.5", "Fixed 37.5 °C", "#eb6834", "////"),
           ("personal", "Personal baseline", "#1baf7a", "\\\\\\\\")]
INK, MUTED = "#1d2430", "#6b7280"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7.5, "axes.edgecolor": MUTED,
                     "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
                     "axes.spines.top": False, "axes.spines.right": False, "hatch.linewidth": 0.5})


def results_figure():
    s = json.loads((RES / "synthetic_results.json").read_text())["summary"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(3.5, 1.75), gridspec_kw={"width_ratios": [1.9, 1.15]})
    groups = ["low", "mid", "high"]
    width = 0.26
    for k, (m, label, col, hatch) in enumerate(METHODS):
        vals = [s["by_baseline"][m][g]["sensitivity"][0] for g in groups]
        xs = [g + (k - 1) * (width + 0.02) for g in range(3)]
        a.bar(xs, vals, width, color=col, hatch=hatch, edgecolor="white", linewidth=0.4, label=label)
        if m in ("fixed38", "personal"):
            a.text(xs[0], vals[0] + 0.015, f"{vals[0]:.2f}", ha="center", va="bottom", fontsize=6, color=INK)
    a.set_xticks(range(3), ["Low", "Middle", "High"])
    a.set_xlabel("Student's normal temperature (tertile)")
    a.set_ylabel("Fever-day sensitivity")
    a.set_ylim(0.5, 1.05)
    a.yaxis.grid(True, color="#e6e8ec", lw=0.5); a.set_axisbelow(True)
    a.set_title("(a) Detection", fontsize=7.5, loc="left")

    vals = [s["overall"][m]["false_cert_per_1000"][0] for m, *_ in METHODS]
    for k, (m, label, col, hatch) in enumerate(METHODS):
        b.bar(k, vals[k], 0.7, color=col, hatch=hatch, edgecolor="white", linewidth=0.4)
        b.text(k, vals[k] + 0.3, f"{vals[k]:.1f}", ha="center", va="bottom", fontsize=6, color=INK)
    b.set_ylim(0, max(vals) * 1.22)
    b.set_xticks(range(3), ["Fixed\n38.0", "Fixed\n37.5", "Pers."], fontsize=6.5)
    b.set_ylabel("False certificates\nper 1000 student-days", fontsize=7)
    b.yaxis.grid(True, color="#e6e8ec", lw=0.5); b.set_axisbelow(True)
    b.set_title("(b) False alarms", fontsize=7.5)
    fig.legend(*a.get_legend_handles_labels(), loc="upper center", ncol=3, frameon=False, fontsize=6.5,
               bbox_to_anchor=(0.5, 1.02), handlelength=1.4, columnspacing=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.9), w_pad=0.8)
    fig.savefig(PAPER / "results.pdf")
    fig.savefig(DOCS / "results.png", dpi=220)
    plt.close(fig)


def diagrams():
    for name in ("architecture", "flow"):
        src = ROOT / "docs" / "diagrams" / f"{name}.dot"
        subprocess.run(["dot", "-Tpdf", str(src), "-o", str(PAPER / f"{name}.pdf")], check=True)
        subprocess.run(["dot", "-Tpng", "-Gdpi=200", str(src), "-o", str(DOCS / f"{name}.png")], check=True)
        subprocess.run(["dot", "-Tsvg", str(src), "-o", str(DOCS / f"{name}.svg")], check=True)


if __name__ == "__main__":
    PAPER.mkdir(parents=True, exist_ok=True); DOCS.mkdir(parents=True, exist_ok=True)
    if shutil.which("dot"):
        diagrams()
    else:
        print("Graphviz 'dot' not found: skipping diagrams")
    results_figure()
    print("figures written")
