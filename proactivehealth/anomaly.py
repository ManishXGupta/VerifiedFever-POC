"""Individual and cohort anomaly detection.

Individual layer
    Each person's baseline is the median of their recent afebrile readings. A reading is a
    fever if it reaches the fixed cutoff, or if it is above an age-specific floor AND at least
    delta above the person's own baseline. Older adults use the long-term-care criteria
    (>= 37.8 C, or >= 37.2 C and >= 1.1 C above baseline), because their baselines are lower
    and fever responses are blunted.

Cohort layer
    Two signals per group (class, workplace, postal code) and day:
      count   number of members flagged febrile today, tested against the count expected from
              the group's own trailing rate (one-sided Poisson tail, Bonferroni over groups);
      drift   mean personal deviation (reading minus own baseline) of the members who reported
              today, as a z-score against the group's trailing daily means. Drift picks up a
              synchronized sub-threshold rise before many members cross a fever threshold.
    Population level: one-sided CUSUM on the daily share of reporters flagged febrile.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AgePolicy:
    fixed_cutoff_c: float
    floor_c: float
    delta_c: float
    default_baseline_c: float


POLICIES = {
    "child": AgePolicy(38.0, 37.5, 1.0, 36.8),
    "adult": AgePolicy(38.0, 37.5, 1.0, 36.7),
    "older": AgePolicy(37.8, 37.2, 1.1, 36.5),
}
BASELINE_WINDOW, BASELINE_MIN, BASELINE_EXCLUDE = 14, 5, 37.5


def age_band(age: int) -> str:
    return "child" if age < 18 else ("older" if age >= 65 else "adult")


def baseline(history: list[float], band: str) -> float:
    afebrile = [t for t in history if t < BASELINE_EXCLUDE][-BASELINE_WINDOW:]
    if len(afebrile) < BASELINE_MIN:
        return POLICIES[band].default_baseline_c
    return float(np.median(afebrile))


def is_fever(temp: float, base: float, band: str) -> bool:
    p = POLICIES[band]
    return temp >= p.fixed_cutoff_c or (temp >= p.floor_c and temp - base >= p.delta_c)


def evaluate_series(temp: np.ndarray, took: np.ndarray, band: str):
    """Personal-rule flags and deviations for one person's daily series (NaN where no reading)."""
    D = len(temp)
    flag = np.zeros(D, dtype=bool)
    dev = np.full(D, np.nan)
    hist: list[float] = []
    for t in range(D):
        if not took[t]:
            continue
        x = float(temp[t])
        b = baseline(hist, band)
        flag[t] = is_fever(x, b, band)
        dev[t] = x - b
        hist.append(x)
    return flag, dev


# ---------- cohort layer ----------

def poisson_sf(k: int, mu: float) -> float:
    """P(X >= k) for X ~ Poisson(mu)."""
    if k <= 0:
        return 1.0
    mu = max(mu, 1e-9)
    term, cdf = math.exp(-mu), 0.0
    for i in range(k):
        cdf += term
        term *= mu / (i + 1)
    return max(0.0, 1.0 - cdf)


def trailing(x: np.ndarray, t: int, window: int = 28, guard: int = 3) -> np.ndarray:
    lo, hi = max(0, t - window), max(0, t - guard)
    return x[..., lo:hi]


def group_count_alerts(flags_g: np.ndarray, reporters_g: np.ndarray, t: int, alpha: float,
                       min_count: int = 3, prior_rate: float = 0.004) -> list[tuple[int, float]]:
    """flags_g, reporters_g: (G, D). Return [(group, p)] alerting on day t (Bonferroni over G)."""
    G = flags_g.shape[0]
    fl, rp = trailing(flags_g, t).sum(1), trailing(reporters_g, t).sum(1)
    rate = (fl + prior_rate * 50) / (rp + 50)          # shrink towards a prior rate
    out = []
    for g in range(G):
        k = int(flags_g[g, t])
        if k < min_count:
            continue
        p = poisson_sf(k, rate[g] * reporters_g[g, t])
        if p < alpha / G:
            out.append((g, p))
    return out


def group_drift_z(devsum_g: np.ndarray, reporters_g: np.ndarray, t: int, min_reporters: int = 8) -> np.ndarray:
    """z-score of today's mean personal deviation per group vs its trailing daily means."""
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = devsum_g / np.maximum(reporters_g, 1)
    hist = trailing(mean, t)
    mu = np.nanmean(hist, axis=1) if hist.shape[1] else np.zeros(mean.shape[0])
    sd = np.nanstd(hist, axis=1, ddof=1) if hist.shape[1] > 2 else np.full(mean.shape[0], np.nan)
    se = 0.25 / np.sqrt(np.maximum(reporters_g[:, t], 1))     # floor: sampling noise of the mean
    z = (mean[:, t] - mu) / np.sqrt(np.nan_to_num(sd, nan=0.0) ** 2 + se ** 2)
    z[reporters_g[:, t] < min_reporters] = np.nan
    return z


def cusum(x: np.ndarray, warmup: int = 14, k: float = 0.5, window: int = 28, guard: int = 3,
          sd_floor: float = 0.0) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    S = np.full(len(x), np.nan)
    s = 0.0
    for t in range(len(x)):
        base = trailing(x, t, window, guard)
        if t < warmup or len(base) < 7:
            continue
        mu, sd = base.mean(), max(base.std(ddof=1), sd_floor, 1e-9)
        s = max(0.0, s + (x[t] - mu) / sd - k)
        S[t] = s
    return S


def localize(signal_g: np.ndarray, t: int, lookback: int = 3) -> int:
    """Group with the largest recent excess over its own trailing mean."""
    lo = max(0, t - lookback + 1)
    recent = signal_g[:, lo:t + 1].mean(1)
    base = trailing(signal_g, lo, 14, 0)
    b = base.mean(1) if base.shape[1] else np.zeros(signal_g.shape[0])
    return int(np.argmax(recent - b))
