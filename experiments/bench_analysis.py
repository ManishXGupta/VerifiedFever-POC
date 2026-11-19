"""Bench agreement analysis (Bland-Altman) for the thermometer bench test.

Protocol (no human participants, so no IRB needed):
  1. Fill a stirred, temperature-controlled water bath (or calibrator) and hold it at each
     set point: 36.0, 37.0, 37.5, 38.0, 39.0, 40.0 C.
  2. Place the reference probe (calibrated, ideally +/-0.05 C or better) and the portable
     thermometer probe side by side. Wait for stability (2 min).
  3. Take at least 5 paired readings per set point (>=30 pairs in total). Record both values.
  4. Save to experiments/bench_data.csv using bench_template.csv as the format.

Usage:  python experiments/bench_analysis.py experiments/bench_data.csv
Output: experiments/results/bench_results.json and bench_bland_altman.pdf
No numbers are reported in the paper until this real bench data exists.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "results"


def analyze(rows: list[dict]) -> dict:
    ref = np.array([float(r["reference_c"]) for r in rows])
    dev = np.array([float(r["device_c"]) for r in rows])
    diff = dev - ref
    bias, sd = float(diff.mean()), float(diff.std(ddof=1))
    near_cut = np.abs(ref - 38.0) <= 0.25
    return {
        "n_pairs": len(rows), "bias_c": round(bias, 3), "sd_c": round(sd, 3),
        "loa_lower_c": round(bias - 1.96 * sd, 3), "loa_upper_c": round(bias + 1.96 * sd, 3),
        "mae_c": round(float(np.abs(diff).mean()), 3),
        "pct_within_0_2": round(float((np.abs(diff) <= 0.2).mean() * 100), 1),
        "pct_within_0_3": round(float((np.abs(diff) <= 0.3).mean() * 100), 1),
        "classification_agreement_at_38": round(float(((dev >= 38.0) == (ref >= 38.0)).mean() * 100), 1),
        "n_pairs_near_cutoff": int(near_cut.sum()),
    }


def plot(rows: list[dict], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ref = np.array([float(r["reference_c"]) for r in rows]); dev = np.array([float(r["device_c"]) for r in rows])
    mean, diff = (ref + dev) / 2, dev - ref
    b, s = diff.mean(), diff.std(ddof=1)
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    ax.scatter(mean, diff, s=10, color="#2a6fb0")
    for y, ls in ((b, "-"), (b + 1.96 * s, "--"), (b - 1.96 * s, "--")):
        ax.axhline(y, color="#444", ls=ls, lw=0.8)
    ax.set_xlabel("Mean of device and reference (°C)"); ax.set_ylabel("Device − reference (°C)")
    fig.tight_layout(); fig.savefig(path)


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    with open(sys.argv[1]) as f:
        rows = list(csv.DictReader(f))
    res = analyze(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bench_results.json").write_text(json.dumps(res, indent=2))
    plot(rows, OUT / "bench_bland_altman.pdf")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
