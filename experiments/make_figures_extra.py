"""Extra figures: UI composite (from docs/screens) and outbreak detection.

Usage:  python experiments/make_figures_extra.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "experiments" / "results"
SCR = ROOT / "docs" / "screens"
PAPER = ROOT / "paper" / "figures"
DOCS = ROOT / "docs" / "figures"
INK, MUTED = "#1d2430", "#6b7280"
COL = {"VF-personal": "#1baf7a", "VF-fixed": "#2a78d6", "Absence": "#eb6834", "Confirmed": "#6b4fbb"}
LABEL = {"VF-personal": "Verified fever (personal)", "VF-fixed": "Verified fever (fixed 38.0 °C)",
         "Absence": "All-cause absence", "Confirmed": "Confirmed-case reports"}
STYLE = {"VF-personal": "-", "VF-fixed": "--", "Absence": "-.", "Confirmed": ":"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7.5, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": MUTED})


def ui_figure():
    panels = [("parent_reading.png", "(a) Signed reading"),
              ("parent_share.png", "(b) Share: code / QR"),
              ("nurse.png", "(c) Nurse one-click validation"),
              ("school.png", "(d) School verifies and accepts")]
    fig = plt.figure(figsize=(7.16, 3.05))
    gs = fig.add_gridspec(2, 3, width_ratios=[0.62, 0.62, 1.9], hspace=0.28, wspace=0.12)
    spots = [gs[:, 0], gs[:, 1], gs[0, 2], gs[1, 2]]
    for (f, title), spot in zip(panels, spots):
        ax = fig.add_subplot(spot)
        ax.imshow(mpimg.imread(SCR / f))
        ax.set_title(title, fontsize=7, loc="left", color=INK)
        ax.axis("off")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.93, bottom=0.01)
    fig.savefig(PAPER / "ui.pdf", dpi=300)
    fig.savefig(DOCS / "ui.png", dpi=200)
    plt.close(fig)


def outbreak_figure():
    r = json.loads((RES / "outbreak_results.json").read_text())
    fig, b = plt.subplots(figsize=(3.5, 1.85))
    grid = np.arange(0, r["detect_window_days"] + 1)
    for k in ("VF-personal", "VF-fixed", "Confirmed", "Absence"):
        d = r["summary"][k]["delays"]
        y = [np.mean([x is not None and x <= g for x in d]) for g in grid]
        b.step(grid, y, where="post", color=COL[k], ls=STYLE[k], lw=1.4, label=LABEL[k])
    b.set_xlabel("Days after the first symptomatic influenza case")
    b.set_ylabel("Outbreaks detected")
    b.set_ylim(0, 0.8); b.set_xlim(0, r["detect_window_days"]); b.set_xticks(range(0, r["detect_window_days"] + 1, 3))
    b.yaxis.grid(True, color="#e6e8ec", lw=0.5)
    b.legend(fontsize=6, frameon=False, loc="upper left", handlelength=2.4)
    fig.tight_layout()
    fig.savefig(PAPER / "outbreak.pdf")
    fig.savefig(DOCS / "outbreak.png", dpi=220)
    plt.close(fig)


if __name__ == "__main__":
    ui_figure()
    outbreak_figure()
    print("extra figures written")


def ui_column_figure():
    """Column-width (single column) version of the UI figure: phones on top, nurse and school below."""
    fig = plt.figure(figsize=(3.4, 4.9))
    gs = fig.add_gridspec(3, 2, height_ratios=[2.35, 0.62, 0.72], hspace=0.22, wspace=0.05)
    spec = [("parent_reading.png", "(a) Signed reading", gs[0, 0]),
            ("parent_share.png", "(b) Share: code / QR", gs[0, 1]),
            ("nurse.png", "(c) Nurse one-click validation", gs[1, :]),
            ("school.png", "(d) School verifies and accepts", gs[2, :])]
    for f, title, spot in spec:
        ax = fig.add_subplot(spot)
        ax.imshow(mpimg.imread(SCR / f))
        ax.set_title(title, fontsize=6.5, loc="left", color=INK, pad=2)
        ax.axis("off")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.01)
    fig.savefig(DOCS / "ui_column.png", dpi=400)
    plt.close(fig)


def ui_column_figure_large():
    """Column-width UI figure with large, readable nurse and school panels (each spans the column)."""
    from PIL import Image
    imgs = {k: Image.open(SCR / f) for k, f in (("a", "parent_reading.png"), ("b", "parent_share.png"),
                                               ("c", "nurse_narrow.png"), ("d", "school_accepted_narrow.png"))}
    W = 3.4
    ha = W / 2 * imgs["a"].height / imgs["a"].width
    hc = W * imgs["c"].height / imgs["c"].width
    hd = W * imgs["d"].height / imgs["d"].width
    title = 0.17
    H = ha + hc + hd + 3 * title + 0.05
    fig = plt.figure(figsize=(W, H))
    y = H
    def place(img, x0, w, h, label):
        nonlocal_y = None
        return img, x0, w, h, label
    rows = [([("a", 0, W / 2, "(a) Signed reading"), ("b", W / 2, W / 2, "(b) Share: code / QR")], ha),
            ([("c", 0, W, "(c) Nurse one-click validation")], hc),
            ([("d", 0, W, "(d) School verifies and accepts")], hd)]
    for items, h in rows:
        y -= title + h
        for key, x0, w, label in items:
            ax = fig.add_axes([x0 / W + 0.005, y / H, w / W - 0.01, h / H])
            ax.imshow(imgs[key]); ax.axis("off")
            fig.text(x0 / W + 0.01, (y + h + 0.03) / H, label, fontsize=8, fontweight="bold", color=INK, va="bottom")
    fig.savefig(DOCS / "ui_column_large.png", dpi=400)
    plt.close(fig)


if __name__ == "__main__":
    ui_column_figure()
    ui_column_figure_large()
