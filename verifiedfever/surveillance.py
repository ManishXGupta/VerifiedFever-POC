"""Cohort surveillance detector shared by the surveillance agent and the experiments.

School-level one-sided CUSUM against a trailing baseline (28 days, 3-day guard band),
OR a class-level count threshold. Also localizes an alert to the class with the
largest excess of verified fevers over the last few days.
"""
from __future__ import annotations

import numpy as np


def cusum_series(x, warmup: int = 14, k: float = 0.5, window=(28, 3)) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    S = np.full(len(x), np.nan)
    s = 0.0
    for t in range(len(x)):
        lo, hi = max(0, t - window[0]), t - window[1]
        if t < warmup or hi - lo < 7:
            continue
        base = x[lo:hi]
        mu = base.mean()
        sd = max(np.sqrt(mu), base.std(ddof=1), 1.0)
        s = max(0.0, s + (x[t] - mu) / sd - k)
        S[t] = s
    return S


def alert_today(school_counts, class_counts_today, h: float, class_threshold: int, warmup: int = 14) -> dict | None:
    """Evaluate the detector on the latest day. Returns the triggering rule(s) or None."""
    t = len(school_counts) - 1
    if t < warmup:
        return None
    S = cusum_series(school_counts, warmup)
    rules = []
    if not np.isnan(S[t]) and S[t] > h:
        rules.append({"rule": "school_cusum", "statistic": round(float(S[t]), 2), "threshold": h})
    top = int(np.argmax(class_counts_today)) if len(class_counts_today) else -1
    if top >= 0 and class_counts_today[top] >= class_threshold:
        rules.append({"rule": "class_cluster", "class": top, "count": int(class_counts_today[top]),
                      "threshold": class_threshold})
    return {"day": t, "rules": rules} if rules else None


def localize(class_by_day: np.ndarray, day: int, lookback: int = 3, baseline_days: int = 14) -> int:
    """Class with the largest excess (recent mean minus its own trailing mean)."""
    lo = max(0, day - lookback + 1)
    recent = class_by_day[:, lo:day + 1].mean(axis=1)
    b_lo, b_hi = max(0, lo - baseline_days), lo
    base = class_by_day[:, b_lo:b_hi].mean(axis=1) if b_hi > b_lo else np.zeros(class_by_day.shape[0])
    return int(np.argmax(recent - base))
