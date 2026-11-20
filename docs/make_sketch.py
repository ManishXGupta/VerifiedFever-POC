"""Hand-drawn style sketch for the paper's first page: today's note-only visit vs. the agentic flow.

Writes docs/figures/sketch_journey.png. Uses matplotlib's xkcd mode with the Comic Relief font.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle

OUT = Path(__file__).resolve().parent / "figures" / "sketch_journey.png"
for f in Path("/usr/share/fonts/truetype/google-fonts/ofl/comicrelief").glob("*.ttf"):
    font_manager.fontManager.addfont(str(f))

INK, RED, BLUE, GREEN, GREY = "#222222", "#d9472b", "#2a78d6", "#1baf7a", "#8a8a8a"


def thermo(ax, x, y, c=RED, signed=False):
    ax.add_patch(FancyBboxPatch((x - 0.07, y - 0.05), 0.14, 0.55, boxstyle="round,pad=0.02", fc="white", ec=INK, lw=1.4))
    ax.add_patch(Rectangle((x - 0.03, y - 0.05), 0.06, 0.32, fc=c, ec="none"))
    ax.add_patch(Circle((x, y - 0.12), 0.12, fc=c, ec=INK, lw=1.4))
    if signed:
        ax.text(x + 0.2, y + 0.42, "signed!", fontsize=7, color=BLUE, rotation=12)


def car(ax, x, y):
    ax.add_patch(Polygon([(x - 0.35, y), (x - 0.35, y + 0.18), (x - 0.18, y + 0.18), (x - 0.08, y + 0.34),
                          (x + 0.18, y + 0.34), (x + 0.28, y + 0.18), (x + 0.35, y + 0.18), (x + 0.35, y)],
                         closed=True, fc="#f3d9a4", ec=INK, lw=1.4))
    for dx in (-0.2, 0.2):
        ax.add_patch(Circle((x + dx, y), 0.08, fc=INK, ec=INK))


def note(ax, x, y, label="Dr. note"):
    ax.add_patch(Polygon([(x - 0.22, y - 0.25), (x + 0.22, y - 0.25), (x + 0.22, y + 0.2), (x + 0.12, y + 0.3),
                          (x - 0.22, y + 0.3)], closed=True, fc="white", ec=INK, lw=1.4))
    for k in range(3):
        ax.plot([x - 0.15, x + 0.13], [y + 0.12 - 0.11 * k] * 2, color=GREY, lw=1)
    ax.text(x, y - 0.58, label, ha="center", fontsize=7)


def school(ax, x, y, ok=None):
    ax.add_patch(Polygon([(x - 0.3, y - 0.2), (x + 0.3, y - 0.2), (x + 0.3, y + 0.15), (x, y + 0.38), (x - 0.3, y + 0.15)],
                         closed=True, fc="#f6e7d3", ec=INK, lw=1.4))
    ax.add_patch(Rectangle((x - 0.07, y - 0.2), 0.14, 0.2, fc="white", ec=INK, lw=1.2))
    ax.plot([x, x], [y + 0.38, y + 0.6], color=INK, lw=1.2)
    ax.add_patch(Polygon([(x, y + 0.6), (x + 0.16, y + 0.54), (x, y + 0.48)], closed=True, fc=RED, ec=INK, lw=1))
    if ok == "check":
        check(ax, x + 0.3, y + 0.25, 0.2)
    elif ok:
        ax.text(x + 0.33, y + 0.3, ok, fontsize=11, color=RED, fontweight="bold")


def robot(ax, x, y):
    ax.add_patch(FancyBboxPatch((x - 0.28, y - 0.2), 0.56, 0.42, boxstyle="round,pad=0.03", fc="#dce9fa", ec=INK, lw=1.4))
    for dx in (-0.11, 0.11):
        ax.add_patch(Circle((x + dx, y + 0.06), 0.05, fc=INK))
    ax.plot([x - 0.1, x, x + 0.1], [y - 0.09, y - 0.13, y - 0.09], color=INK, lw=1.2)
    ax.plot([x, x], [y + 0.25, y + 0.38], color=INK, lw=1.2)
    ax.add_patch(Circle((x, y + 0.41), 0.04, fc=RED, ec=INK))
    # shield
    sx, sy = x + 0.36, y + 0.2
    ax.add_patch(Polygon([(sx - 0.1, sy + 0.1), (sx + 0.1, sy + 0.1), (sx + 0.1, sy - 0.03), (sx, sy - 0.14),
                          (sx - 0.1, sy - 0.03)], closed=True, fc=GREEN, ec=INK, lw=1.1))


def nurse(ax, x, y):
    ax.add_patch(Circle((x, y + 0.2), 0.12, fc="white", ec=INK, lw=1.4))
    ax.plot([x, x], [y + 0.08, y - 0.2], color=INK, lw=1.4)
    ax.plot([x - 0.15, x, x + 0.15], [y - 0.02, y + 0.03, y - 0.02], color=INK, lw=1.4)
    ax.plot([x - 0.1, x, x + 0.1], [y - 0.38, y - 0.2, y - 0.38], color=INK, lw=1.4)
    ax.text(x - 0.05, y + 0.31, "+", color=RED, fontsize=9, fontweight="bold")
    check(ax, x + 0.17, y + 0.1, 0.1)
    ax.text(x + 0.3, y + 0.1, "click", fontsize=7, color=GREEN)


def check(ax, x, y, s=0.12, c=GREEN):
    ax.plot([x, x + 0.35 * s, x + s], [y + 0.45 * s, y, y + 0.9 * s], color=c, lw=2.2)


def arrow(ax, x0, x1, y, c=INK):
    ax.annotate("", xy=(x1, y), xytext=(x0, y), arrowprops=dict(arrowstyle="->", lw=1.4, color=c))


def main():
    with plt.xkcd(scale=0.8, length=120, randomness=2):
        plt.rcParams["font.family"] = "Comic Relief"
        plt.rcParams["path.effects"] = []
        fig = plt.figure(figsize=(3.4, 2.6), dpi=300)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 4.2); ax.set_ylim(0, 3.2); ax.axis("off")

        # --- Today ---
        T = 2.15  # icon baseline of the top lane
        ax.text(0.12, 3.0, "Today: a mild fever...", fontsize=9.5, fontweight="bold", color=RED)
        ax.text(4.1, 3.0, "~2 h + $304, for paperwork", fontsize=6.5, color=INK, ha="right")
        thermo(ax, 0.45, T)
        arrow(ax, 0.68, 0.95, T + 0.15)
        car(ax, 1.35, T - 0.05)
        arrow(ax, 1.75, 2.05, T + 0.15)
        note(ax, 2.35, T + 0.1, label="")
        arrow(ax, 2.65, 2.95, T + 0.15)
        school(ax, 3.4, T, ok="?")
        for xx, lab in ((0.45, "home"), (1.35, "clinic trip"), (2.35, "Dr. note"), (3.4, "school")):
            ax.text(xx, T - 0.48, lab, ha="center", fontsize=6.8)

        ax.plot([0.1, 4.1], [1.5, 1.5], color=GREY, lw=1, ls="--")

        # --- With agents ---
        B = 0.62
        ax.text(0.12, 1.3, "With guardrailed agents", fontsize=9.5, fontweight="bold", color=BLUE)
        ax.text(4.1, 1.3, "no visit, minutes", fontsize=6.5, color=INK, ha="right")
        thermo(ax, 0.45, B, signed=True)
        arrow(ax, 0.68, 0.98, B + 0.15, BLUE)
        robot(ax, 1.33, B + 0.13)
        arrow(ax, 1.85, 2.12, B + 0.15, BLUE)
        nurse(ax, 2.38, B + 0.13)
        arrow(ax, 2.85, 3.05, B + 0.15, BLUE)
        school(ax, 3.45, B, ok="check")
        for xx, lab in ((0.45, "home"), (1.33, "agents check"), (2.38, "nurse"), (3.45, "school accepts")):
            ax.text(xx, B - 0.48, lab, ha="center", fontsize=6.8)
        fig.savefig(OUT, dpi=300, facecolor="white")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
