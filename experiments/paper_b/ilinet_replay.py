"""E2. Replay of nine real US influenza seasons (CDC ILINet, 2010/11-2018/19) through a simulated registry.

For each of 99 location-seasons (US national + 10 HHS regions) the weekly wILI curve drives the
daily probability that a registry participant starts a febrile respiratory illness:
    p(d) = A * wILI(d + care_delay) / 100
where wILI is interpolated to days and care_delay shifts the curve earlier, because people run a
fever a few days before the clinic visit that ILINet counts. A is set so that an average season
gives about 20% of participants at least one febrile respiratory episode (stated assumption).

Each participant takes one reading on 85% of mornings; readings are flagged with the
age-aware personal rule (vectorized: afebrile median of the previous 21 days, refreshed weekly)
or with one fixed 38.0 C cutoff. The registry signal is the daily count of flagged readings.

Detector: one-sided Poisson CUSUM against the mean of the season's first 21 days (MMWR weeks
41-43, before any onset in these data); the threshold h is set on null replays (each season's
early level held flat) so that at most 5% of null seasons raise any alert.

Compared timings, all relative to the first day of the CDC onset week (negative = earlier):
    registry alert day (readings are available the same morning)
    ILINet, first week above baseline, published 6 days after the week ends
    ILINet, season onset as declared: third consecutive week above baseline, published 6 days later
Also: registry with weekly aggregation (ablation) and sensitivity to care delay and registry size.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import ilinet_data  # noqa: E402
import pop_model as pm  # noqa: E402

OUT = ROOT / "experiments" / "results" / "paper_b"
TARGET_ATTACK = 0.20
REF_DAYS = 21
K = 0.5
FA_TARGET = 0.05


def daily_wili(wili: list[float]) -> np.ndarray:
    W = len(wili)
    mid = np.arange(W) * 7 + 3
    return np.interp(np.arange(W * 7), mid, wili)


def scale_A(seasons) -> float:
    m = np.mean([np.mean(s["wili"]) * len(s["wili"]) * 7 / 100 for s in seasons])
    return TARGET_ATTACK / m


def cusum_fixed_ref(x: np.ndarray, ref_days: int = REF_DAYS, k: float = K) -> np.ndarray:
    mu = max(x[:ref_days].mean(), 0.5)
    sd = np.sqrt(mu)
    S = np.zeros(len(x)); s = 0.0
    for t in range(len(x)):
        if t >= ref_days:
            s = max(0.0, s + (x[t] - mu) / sd - k)
        S[t] = s
    return S


def weekly_cusum(x: np.ndarray, ref_weeks: int = 3, k: float = K) -> np.ndarray:
    w = x[: len(x) // 7 * 7].reshape(-1, 7).sum(1)
    return cusum_fixed_ref(w, ref_weeks, k)


PRE = 21  # pre-season days simulated (and discarded) so baselines exist from the first analysed day


def registry_counts(rng, N, p_ili, rule="personal"):
    band, mu, rr = pm.population(N, rng)
    p_ili = np.concatenate([np.full(PRE, p_ili[0]), p_ili])
    temp, took, truth, onsets = pm.simulate(rng, band, mu, rr, p_ili)
    if rule == "personal":
        flags, _ = pm.personal_flags(temp, took, band)
    else:
        flags = took & (temp >= 38.0)
    return flags.sum(0).astype(float)[PRE:], onsets[PRE:]


def run_season(s, A, N, delay, rng, rules=("personal", "fixed")):
    dw = daily_wili(s["wili"])
    shifted = np.concatenate([dw[delay:], np.full(delay, dw[-1])]) if delay else dw
    p = A * shifted / 100
    out = {}
    for r in rules:
        out[r], _ = registry_counts(rng, N, p, r)
    return out


def null_counts(s, A, N, rng, rules=("personal", "fixed")):
    dw = daily_wili(s["wili"])
    p = np.full(len(dw), A * dw[:REF_DAYS].mean() / 100)
    return {r: registry_counts(rng, N, p, r)[0] for r in rules}


def calibrate(null_runs, rule, weekly=False):
    peaks = []
    for c in null_runs:
        x = c[rule]
        S = weekly_cusum(x) if weekly else cusum_fixed_ref(x)
        peaks.append(S.max())
    return float(np.quantile(peaks, 1 - FA_TARGET)) + 1e-6


def first_day(S, h, weekly=False):
    idx = np.where(S > h)[0]
    if not len(idx):
        return None
    return int(idx[0] * 7 + 6) if weekly else int(idx[0])


def evaluate(seasons, A, N, delay, seed, n_null=200, rules=("personal", "fixed")):
    rng = np.random.default_rng(seed)
    nulls = [null_counts(seasons[i % len(seasons)], A, N, rng, rules) for i in range(n_null)]
    H = {r: calibrate(nulls, r) for r in rules}
    Hw = calibrate(nulls, "personal", weekly=True)
    rows = []
    for s in seasons:
        c = run_season(s, A, N, delay, rng, rules)
        row = {"location": s["location"], "season": s["season"], "onset_week": s["onset_week"]}
        for r in rules:
            row[f"alert_{r}"] = first_day(cusum_fixed_ref(c[r]), H[r])
        row["alert_weekly"] = first_day(weekly_cusum(c["personal"]), Hw, weekly=True)
        if s["onset_idx"] is not None:
            o = s["onset_idx"] * 7
            row["onset_day"] = o
            row["ilinet_first_week_published"] = o + 6 + 6
            row["ilinet_declared_published"] = o + 14 + 6 + 6
        rows.append(row)
    return rows, H, Hw


def summarize(rows):
    on = [r for r in rows if r.get("onset_day") is not None]
    no = [r for r in rows if r.get("onset_day") is None]
    def rel(key):
        v = [r[key] - r["onset_day"] for r in on if r[key] is not None]
        return v
    out = {"n_with_onset": len(on), "n_without_onset": len(no)}
    for key in ("alert_personal", "alert_fixed", "alert_weekly"):
        v = rel(key)
        detected_by_declared = [r for r in on if r[key] is not None and r[key] <= r["ilinet_declared_published"]]
        lead_decl = [r["ilinet_declared_published"] - r[key] for r in on if r[key] is not None]
        lead_first = [r["ilinet_first_week_published"] - r[key] for r in on if r[key] is not None]
        out[key] = {
            "alerted": len(v), "share_alerted": round(len(v) / len(on), 3),
            "median_days_vs_onset_week": float(np.median(v)) if v else None,
            "iqr_days_vs_onset_week": [float(np.percentile(v, 25)), float(np.percentile(v, 75))] if v else None,
            "median_lead_vs_declared_onset": float(np.median(lead_decl)) if v else None,
            "iqr_lead_vs_declared_onset": [float(np.percentile(lead_decl, 25)), float(np.percentile(lead_decl, 75))] if v else None,
            "median_lead_vs_first_week_published": float(np.median(lead_first)) if v else None,
            "share_before_declared": round(len(detected_by_declared) / len(on), 3),
            "share_before_first_week_published": round(sum(x > 0 for x in lead_first) / len(on), 3),
            "alerts_in_seasons_without_onset": sum(r[key] is not None for r in no),
        }
    out["ilinet_declared_vs_onset_week_days"] = 26
    out["ilinet_first_week_vs_onset_week_days"] = 12
    return out


def main():
    t0 = time.time()
    seasons = ilinet_data.load()
    A = scale_A(seasons)
    res = {"A": A, "target_attack": TARGET_ATTACK, "fa_target": FA_TARGET, "configs": {}}
    configs = [("main", 10000, 2, 11)] + [(f"N={n}", n, 2, 12 + i) for i, n in enumerate((2000, 50000))] + \
              [(f"delay={d}", 10000, d, 20 + d) for d in (0, 4)]
    for name, N, delay, seed in configs:
        rules = ("personal", "fixed") if name == "main" else ("personal",)
        if "fixed" not in rules:
            rows, H, Hw = evaluate_personal_only(seasons, A, N, delay, seed)
        else:
            rows, H, Hw = evaluate(seasons, A, N, delay, seed, rules=rules)
        res["configs"][name] = {"N": N, "care_delay": delay, "h": H, "h_weekly": Hw, "summary": summarize_any(rows),
                                "rows": rows}
        print(name, json.dumps(res["configs"][name]["summary"]), f"{time.time() - t0:.0f}s", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ilinet_results.json").write_text(json.dumps(res, indent=1))


def evaluate_personal_only(seasons, A, N, delay, seed):
    return evaluate(seasons, A, N, delay, seed, n_null=120, rules=("personal",))


def summarize_any(rows):
    for r in rows:
        r.setdefault("alert_fixed", None)
    s = summarize(rows)
    return s


if __name__ == "__main__":
    main()
