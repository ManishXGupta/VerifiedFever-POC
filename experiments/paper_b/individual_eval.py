"""E1. Individual fever detection by age band, with the exact registry rule.

Per seed: 1000 people per age band, 120 days. Rules compared on the same readings:
  fixed 38.0        one cutoff for everyone
  fixed 37.8        the lower long-term-care cutoff applied to everyone
  personal (one)    personal baseline with the child/adult cutoffs for everyone
  personal (age)    personal baseline with age-specific cutoffs (registry default)
Metrics: fever-day sensitivity (reading days inside a true fever episode) and false flags per
1000 person-days outside episodes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).parent))
from proactivehealth import anomaly  # noqa: E402
import pop_model as pm  # noqa: E402

OUT = ROOT / "experiments" / "results" / "paper_b"
N_PER, D, SEEDS = 1000, 120, 5


def run(seed: int):
    rng = np.random.default_rng(1000 + seed)
    res = {}
    for b in pm.BANDS:
        mix = {x: float(x == b) for x in pm.BANDS}
        band, mu, rr = pm.population(N_PER, rng, mix)
        p = np.full(D, 0.004)
        temp, took, truth, _ = pm.simulate(rng, band, mu, np.ones(N_PER), p)
        rules = {"fixed 38.0": took & (temp >= 38.0), "fixed 37.8": took & (temp >= 37.8)}
        pa = np.zeros_like(took); po = np.zeros_like(took)
        for i in range(N_PER):
            pa[i], _ = anomaly.evaluate_series(temp[i], took[i], b)
            po[i], _ = anomaly.evaluate_series(temp[i], took[i], "adult" if b == "older" else b)
        rules["personal (one rule)"], rules["personal (age-aware)"] = po, pa
        warm = np.zeros(D, dtype=bool); warm[14:] = True
        pos, neg = took & truth & warm, took & ~truth & warm
        res[b] = {r: {"sens": float((f & pos).sum() / pos.sum()), "fp_per_1000": float(1000 * (f & neg).sum() / neg.sum())}
                  for r, f in rules.items()}
        res[b]["_n_fever_days"] = int(pos.sum())
    return res


def main():
    runs = [run(s) for s in range(SEEDS)]
    summ = {}
    for b in pm.BANDS:
        summ[b] = {}
        for r in runs[0][b]:
            if r.startswith("_"):
                continue
            s = [x[b][r]["sens"] for x in runs]; f = [x[b][r]["fp_per_1000"] for x in runs]
            summ[b][r] = {"sens": round(float(np.mean(s)), 3), "sens_min": round(float(min(s)), 3),
                          "sens_max": round(float(max(s)), 3), "fp_per_1000": round(float(np.mean(f)), 2)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "individual_results.json").write_text(json.dumps({"seeds": SEEDS, "n_per_band": N_PER, "days": D,
                                                             "summary": summ}, indent=2))
    for b in summ:
        print(b, json.dumps(summ[b]))


if __name__ == "__main__":
    main()
