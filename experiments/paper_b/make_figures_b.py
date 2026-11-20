"""Figures for Paper B (writes docs/paper_b/*.png)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import ilinet_data  # noqa: E402
import ilinet_replay as R  # noqa: E402

RES = ROOT / "experiments" / "results" / "paper_b"
FIG = ROOT / "docs" / "paper_b"
BLUE, ORANGE, GREEN, GREY, DARK = "#2a78d6", "#eb6834", "#1baf7a", "#9aa0a6", "#3c4043"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": "#888", "axes.labelcolor": "#222",
                     "xtick.color": "#444", "ytick.color": "#444", "legend.frameon": False})


def fig_individual():
    r = json.loads((RES / "individual_results.json").read_text())["summary"]
    rules = ["fixed 38.0", "fixed 37.8", "personal (one rule)", "personal (age-aware)"]
    cols = [GREY, DARK, BLUE, ORANGE]
    bands = [("child", "Children"), ("adult", "Adults"), ("older", "Older adults")]
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.8), gridspec_kw={"width_ratios": [1.4, 1]})
    x = np.arange(3); w = 0.2
    for i, (rule, c) in enumerate(zip(rules, cols)):
        v = [r[b][rule]["sens"] for b, _ in bands]
        axes[0].bar(x + (i - 1.5) * w, v, w * 0.92, color=c, label=rule)
        fp = [r[b][rule]["fp_per_1000"] for b, _ in bands]
        axes[1].bar(x + (i - 1.5) * w, fp, w * 0.92, color=c)
    for b_i, (b, _) in enumerate(bands):
        axes[0].text(b_i + 1.5 * w, r[b]["personal (age-aware)"]["sens"] + 0.02,
                     f"{r[b]['personal (age-aware)']['sens']:.2f}", ha="center", fontsize=7.5, color=ORANGE)
        axes[0].text(b_i - 1.5 * w, r[b]["fixed 38.0"]["sens"] + 0.02, f"{r[b]['fixed 38.0']['sens']:.2f}",
                     ha="center", fontsize=7.5, color="#555")
    axes[0].set_xticks(x, [n for _, n in bands]); axes[0].set_ylim(0, 1.05)
    axes[0].set_ylabel("Illness-day sensitivity"); axes[0].set_title("(a) Detection", fontsize=9, loc="left")
    axes[1].set_xticks(x, [n for _, n in bands]); axes[1].set_ylabel("Per 1000 person-days")
    axes[1].set_title("(b) False flags", fontsize=9, loc="left")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center", ncol=4, fontsize=7.8, bbox_to_anchor=(0.5, 0.995))
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(FIG / "individual.png", dpi=300); plt.close(fig)


def fig_ilinet_example(loc="US National", season="2014/2015"):
    res = json.loads((RES / "ilinet_results.json").read_text())
    main = res["configs"]["main"]
    S = ilinet_data.load()
    s = next(x for x in S if x["location"] == loc and x["season"] == season)
    row = next(x for x in main["rows"] if x["location"] == loc and x["season"] == season)
    rng = np.random.default_rng(99)
    c = R.run_season(s, res["A"], 10000, 2, rng, ("personal",))["personal"]
    D = len(c)
    alert = R.first_day(R.cusum_fixed_ref(c), main["h"]["personal"])
    fig, ax = plt.subplots(2, 1, figsize=(6.6, 3.6), sharex=True, gridspec_kw={"height_ratios": [1, 1.2]})
    wk = np.arange(len(s["wili"])) * 7
    ax[0].bar(wk + 3, s["wili"], width=6, color="#c9d6e8")
    ax[0].set_ylabel("ILINet wILI (%)")
    ax[0].set_title(f"(a) Reported influenza-like illness, {loc}, {season}", fontsize=9, loc="left")
    ax[1].plot(np.arange(D), c, color=BLUE, lw=1.2)
    ax[1].set_ylabel("Registry fevers per day")
    ax[1].set_title("(b) Simulated registry of 10,000 people (one realisation)", fontsize=9, loc="left")
    o = row["onset_day"]
    marks = [(o, "CDC onset week begins", "#555", ":"), (alert, "registry alert", ORANGE, "-"),
             (row["ilinet_first_week_published"], "first week above\nbaseline published", GREY, "--"),
             (row["ilinet_declared_published"], "onset declared\n(published)", DARK, "--")]
    for a in ax:
        for d, lab, col, ls in marks:
            if d is not None:
                a.axvline(d, color=col, ls=ls, lw=1.2)
    from matplotlib.lines import Line2D
    hs = [Line2D([0], [0], color=col, ls=ls, lw=1.4) for d, lab, col, ls in marks]
    ax[0].legend(hs, [f"{lab.replace(chr(10), ' ')} (day {d})" for d, lab, col, ls in marks], fontsize=7, loc="upper right",
                 frameon=True, facecolor="white", edgecolor="none", framealpha=0.95)
    ticks = list(range(0, D, 28))
    ax[1].set_xticks(ticks, [f"wk {s['weeks'][t // 7]}" for t in ticks])
    ax[1].set_xlim(0, min(D, 7 * 26))
    fig.tight_layout(); fig.savefig(FIG / "ilinet_example.png", dpi=300); plt.close(fig)
    return row, alert


def fig_lead():
    res = json.loads((RES / "ilinet_results.json").read_text())
    rows = [r for r in res["configs"]["main"]["rows"] if r.get("onset_day") is not None]
    rel = lambda k: [r[k] - r["onset_day"] for r in rows if r[k] is not None]  # noqa: E731
    series = [("Registry, daily, personal rule", rel("alert_personal"), ORANGE),
              ("Registry, daily, fixed 38.0 C", rel("alert_fixed"), BLUE),
              ("Registry, weekly totals", rel("alert_weekly"), GREY),
              ("ILINet first week above baseline, published", [12] * len(rows), DARK),
              ("ILINet onset declared, published", [26] * len(rows), DARK)]
    fig, ax = plt.subplots(figsize=(7.0, 2.9))
    rng = np.random.default_rng(1)
    for i, (lab, v, c) in enumerate(series[::-1]):
        y = i + rng.uniform(-0.18, 0.18, len(v))
        if len(set(v)) > 1:
            ax.scatter(v, y, s=9, color=c, alpha=0.55, lw=0)
            ax.plot([np.median(v)] * 2, [i - 0.3, i + 0.3], color="#111", lw=2)
            ax.text(np.median(v), i + 0.36, f"median {np.median(v):+.0f} d", fontsize=7.2, ha="center",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
        else:
            ax.plot([v[0]] * 2, [i - 0.3, i + 0.3], color=c, lw=2.5)
            ax.text(v[0] + 1.5, i, f"{v[0]:+d} d", fontsize=7.2, va="center")
    ax.axvline(0, color="#999", ls=":", lw=1)
    ax.set_yticks(range(len(series)), [s[0] for s in series[::-1]], fontsize=8)
    ax.set_xlabel("Days from the start of the CDC onset week (negative = earlier)")
    fig.tight_layout(); fig.savefig(FIG / "ilinet_lead.png", dpi=300); plt.close(fig)


def fig_town():
    r = json.loads((RES / "town_results.json").read_text())
    s = r["summary"]
    names = [("reg", "Registry, count + drift", ORANGE), ("reg_nodrift", "Registry, count only", BLUE),
             ("reg_fixed", "Registry, fixed 38.0 C", GREY), ("syn", "Clinic visits", DARK), ("lab", "Lab-confirmed", "#9db6d6")]
    fig, ax = plt.subplots(1, 3, figsize=(7.0, 2.3), sharey=True)
    y = np.arange(len(names))[::-1]
    cols = [c for _, _, c in names]
    det = [s[k]["detected"] for k, _, _ in names]
    dly = [s[k]["median_delay_days"] or 0 for k, _, _ in names]
    loc = [s[k]["localized_exact_setting"] if k.startswith("reg") else None for k, _, _ in names]
    panels = ((ax[0], det, "(a) Detected within 21 days", "{:.0%}", 1.0),
              (ax[1], dly, "(b) Median delay, days", "{:.0f}", max(dly) * 1.25),
              (ax[2], loc, "(c) Names exact setting", "{:.0%}", 1.0))
    for a, v, t, fmt, xmax in panels:
        for yi, val, c in zip(y, v, cols):
            if val is None:
                a.text(0.02, yi, "no setting", va="center", fontsize=7, color="#666")
                continue
            a.barh(yi, val, color=c, height=0.65)
            a.text(val + xmax * 0.02, yi, fmt.format(val), va="center", fontsize=7.5)
        a.set_xlim(0, xmax); a.set_title(t, fontsize=8.5, loc="left")
        a.tick_params(axis="x", labelsize=7)
    ax[0].set_yticks(y, [n for _, n, _ in names], fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "town.png", dpi=300); plt.close(fig)


if __name__ == "__main__":
    FIG.mkdir(parents=True, exist_ok=True)
    fig_individual()
    print(fig_ilinet_example())
    fig_lead()
    if (RES / "town_results.json").exists():
        fig_town()
    print("ok")
