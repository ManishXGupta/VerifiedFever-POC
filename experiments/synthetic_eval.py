"""Synthetic evaluation: personal-baseline rule vs fixed cutoffs.

Cohort model (all parameters are explicit assumptions, see PARAMS):
  * each student i has a normal temperature mu_i ~ N(36.7, 0.25) C, clipped to [36.0, 37.4]
    (individual normal temperatures differ between people: Obermeyer et al., BMJ 2017;
     Diamond et al., PLoS ONE 2021)
  * one morning reading per day = mu_i + day-to-day variation + measurement noise
  * fever episodes start with a small daily probability, last 1-3 days, and raise the
    temperature by 1.0-2.5 C above that student's own normal on each episode day
  * non-infectious transient elevations (warm room, activity) raise it by 0.3-0.8 C
Ground truth: a day is a fever day if it falls inside a fever episode.

Methods compared on each day after a 14-day baseline warm-up:
  fixed38   one cutoff for everyone, 38.0 C
  fixed37.5 one cutoff for everyone, 37.5 C
  personal  the VerifiedFever rule (school 38.0 C cutoff OR >=37.5 C and >=1.0 C above
            the student's own causal baseline)

Usage:  python experiments/synthetic_eval.py
Outputs: experiments/results/synthetic_results.json, synthetic_sensitivity.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verifiedfever.rules import Policy, is_febrile, personal_baseline  # noqa: E402

OUT = ROOT / "experiments" / "results"

PARAMS = dict(
    n_students=500, n_days=90, warmup_days=14,
    mu_mean=36.7, mu_sd=0.25, mu_min=36.0, mu_max=37.4,
    daily_sd=0.15, meas_sd=0.10,
    p_fever_onset=0.012, fever_len=(1, 3), fever_rise=(1.0, 2.5),
    p_transient=0.03, transient_rise=(0.3, 0.8),
)


def simulate(rng: np.random.Generator, p: dict):
    n, d = p["n_students"], p["n_days"]
    mu = np.clip(rng.normal(p["mu_mean"], p["mu_sd"], n), p["mu_min"], p["mu_max"])
    rise = np.zeros((n, d))
    fever = np.zeros((n, d), dtype=bool)
    episodes = []  # (student, start, end_inclusive)
    for i in range(n):
        t = 0
        while t < d:
            if rng.random() < p["p_fever_onset"]:
                length = int(rng.integers(p["fever_len"][0], p["fever_len"][1] + 1))
                end = min(d, t + length)
                fever[i, t:end] = True
                rise[i, t:end] = rng.uniform(*p["fever_rise"], end - t)
                episodes.append((i, t, end - 1))
                t = end + 2  # short recovery gap
            else:
                t += 1
    transient = (~fever) & (rng.random((n, d)) < p["p_transient"])
    rise[transient] = rng.uniform(*p["transient_rise"], int(transient.sum()))
    temp = (mu[:, None] + rng.normal(0, p["daily_sd"], (n, d)) + rise
            + rng.normal(0, p["meas_sd"], (n, d)))
    return mu, np.round(temp, 1), fever, episodes  # consumer thermometers display 0.1 C


def personal_flags(temp: np.ndarray, policy: Policy) -> np.ndarray:
    n, d = temp.shape
    flags = np.zeros_like(temp, dtype=bool)
    for i in range(n):
        hist: list[float] = []
        for t in range(d):
            b = personal_baseline(hist, policy)
            flags[i, t] = is_febrile(float(temp[i, t]), b.value_c, policy)
            hist.append(float(temp[i, t]))
    return flags


def metrics(pred: np.ndarray, truth: np.ndarray) -> dict:
    tp = int((pred & truth).sum()); fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum()); tn = int((~pred & ~truth).sum())
    sens = tp / (tp + fn) if tp + fn else float("nan")
    spec = tn / (tn + fp) if tn + fp else float("nan")
    ppv = tp / (tp + fp) if tp + fp else float("nan")
    f1 = 2 * ppv * sens / (ppv + sens) if ppv + sens else 0.0
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, sensitivity=sens, specificity=spec, ppv=ppv, f1=f1,
                false_cert_per_1000=1000 * fp / pred.size)


def episode_detection(pred: np.ndarray, episodes, warmup: int) -> float:
    eps = [(i, s, e) for i, s, e in episodes if s >= warmup]
    hit = sum(bool(pred[i, s:e + 1].any()) for i, s, e in eps)
    return hit / len(eps) if eps else float("nan")


def run_once(seed: int, p: dict = PARAMS, policy: Policy = Policy()) -> dict:
    rng = np.random.default_rng(seed)
    mu, temp, fever, episodes = simulate(rng, p)
    w = p["warmup_days"]
    preds = {
        "fixed38": temp >= 38.0,
        "fixed37.5": temp >= 37.5,
        "personal": personal_flags(temp, policy),
    }
    tert = np.quantile(mu, [1 / 3, 2 / 3])
    groups = {"low": mu <= tert[0], "mid": (mu > tert[0]) & (mu <= tert[1]), "high": mu > tert[1]}
    out = {"seed": seed, "n_fever_days": int(fever[:, w:].sum()), "n_days_eval": int(fever[:, w:].size),
           "n_episodes_eval": sum(1 for _, s, _ in episodes if s >= w), "overall": {}, "by_baseline": {}}
    for name, pr in preds.items():
        m = metrics(pr[:, w:], fever[:, w:])
        m["episode_detection"] = episode_detection(pr, episodes, w)
        out["overall"][name] = m
        out["by_baseline"][name] = {g: metrics(pr[mask][:, w:], fever[mask][:, w:]) for g, mask in groups.items()}
    # cold start (first 14 days, population default baseline) reported separately
    out["cold_start"] = {k: metrics(v[:, :w], fever[:, :w]) for k, v in preds.items()}
    return out


def summarize(runs: list[dict]) -> dict:
    keys = ["sensitivity", "specificity", "ppv", "f1", "false_cert_per_1000", "episode_detection"]
    summ = {"overall": {}, "by_baseline": {}, "cold_start": {}}
    for m in runs[0]["overall"]:
        summ["overall"][m] = {k: [float(np.mean([r["overall"][m][k] for r in runs])),
                                  float(np.std([r["overall"][m][k] for r in runs]))] for k in keys}
        summ["by_baseline"][m] = {g: {k: [float(np.mean([r["by_baseline"][m][g][k] for r in runs])),
                                          float(np.std([r["by_baseline"][m][g][k] for r in runs]))]
                                      for k in ["sensitivity", "specificity"]} for g in ("low", "mid", "high")}
        summ["cold_start"][m] = {k: float(np.mean([r["cold_start"][m][k] for r in runs]))
                                 for k in ["sensitivity", "specificity"]}
    summ["mean_fever_days"] = float(np.mean([r["n_fever_days"] for r in runs]))
    summ["mean_episodes"] = float(np.mean([r["n_episodes_eval"] for r in runs]))
    summ["days_eval"] = runs[0]["n_days_eval"]
    return summ


def sensitivity_analysis(seeds=range(5)) -> list[dict]:
    rows = []
    for mu_sd in (0.15, 0.25, 0.35):
        for meas_sd in (0.05, 0.10, 0.20):
            p = dict(PARAMS, mu_sd=mu_sd, meas_sd=meas_sd)
            runs = [run_once(1000 + s, p) for s in seeds]
            for m in ("fixed38", "fixed37.5", "personal"):
                rows.append(dict(mu_sd=mu_sd, meas_sd=meas_sd, method=m,
                                 sensitivity=float(np.mean([r["overall"][m]["sensitivity"] for r in runs])),
                                 specificity=float(np.mean([r["overall"][m]["specificity"] for r in runs])),
                                 false_cert_per_1000=float(np.mean([r["overall"][m]["false_cert_per_1000"] for r in runs]))))
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runs = [run_once(s) for s in range(10)]
    result = {"params": PARAMS, "policy": Policy().__dict__, "n_seeds": len(runs), "summary": summarize(runs)}
    (OUT / "synthetic_results.json").write_text(json.dumps(result, indent=2))
    rows = sensitivity_analysis()
    with open(OUT / "synthetic_sensitivity.csv", "w") as f:
        f.write("mu_sd,meas_sd,method,sensitivity,specificity,false_cert_per_1000\n")
        for r in rows:
            f.write(f"{r['mu_sd']},{r['meas_sd']},{r['method']},{r['sensitivity']:.4f},"
                    f"{r['specificity']:.4f},{r['false_cert_per_1000']:.2f}\n")
    s = result["summary"]
    print(f"{len(runs)} seeds, {s['days_eval']} student-days each, ~{s['mean_fever_days']:.0f} fever days")
    print(f"{'method':10s} {'sens':>14s} {'spec':>14s} {'PPV':>8s} {'F1':>7s} {'FP/1000':>8s} {'episode':>8s}")
    for m, v in s["overall"].items():
        print(f"{m:10s} {v['sensitivity'][0]:.3f}+/-{v['sensitivity'][1]:.3f} {v['specificity'][0]:.4f}+/-{v['specificity'][1]:.4f}"
              f" {v['ppv'][0]:8.3f} {v['f1'][0]:7.3f} {v['false_cert_per_1000'][0]:8.2f} {v['episode_detection'][0]:8.3f}")
    print("by baseline tertile (sensitivity):")
    for m, g in s["by_baseline"].items():
        print(f"  {m:10s} " + "  ".join(f"{k}={g[k]['sensitivity'][0]:.3f}" for k in ("low", "mid", "high")))
    print("cold start:", {m: round(v["sensitivity"], 3) for m, v in s["cold_start"].items()})


if __name__ == "__main__":
    main()
