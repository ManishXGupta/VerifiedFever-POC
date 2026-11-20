"""Shared population temperature model for Paper B experiments.

Age bands differ in normal temperature, illness rate and fever response:
  child   higher illness rate, strong fever response
  adult
  older   lower normal temperature and blunted fever response
All values are stated assumptions; they are varied in sensitivity analyses.
"""
from __future__ import annotations

import warnings

import numpy as np

BANDS = ("child", "adult", "older")
MIX = {"child": 0.22, "adult": 0.60, "older": 0.18}
MU = {"child": (36.8, 0.28), "adult": (36.7, 0.28), "older": (36.4, 0.30)}
RISE = {"child": (1.0, 2.5), "adult": (0.9, 2.2), "older": (0.6, 1.6)}
ILLNESS_RR = {"child": 1.6, "adult": 0.9, "older": 0.7}
DAILY_SD, MEAS_SD, ADHERENCE = 0.15, 0.10, 0.85
P_TRANSIENT, TRANSIENT = 0.03, (0.3, 0.8)
P_BACKGROUND = 0.0003           # non-respiratory fever onsets per person-day
EPISODE_LEN = (2, 4)


def population(n: int, rng, mix=MIX):
    band = rng.choice(np.array(BANDS), size=n, p=[mix[b] for b in BANDS])
    mu = np.empty(n)
    for b in BANDS:
        m = band == b
        mu[m] = np.clip(rng.normal(*MU[b], m.sum()), 35.8, 37.4)
    rr = np.vectorize(ILLNESS_RR.get)(band).astype(float)
    rr /= sum(MIX[b] * ILLNESS_RR[b] for b in BANDS)
    return band, mu, rr


def simulate(rng, band, mu, rr, p_ili: np.ndarray, p_bg: float = P_BACKGROUND):
    """p_ili: per-day probability of a new febrile respiratory episode for an average person.

    Returns temp (N, D), took (N, D), fever_truth (N, D), ili_onset_count (D,)."""
    N, D = len(mu), len(p_ili)
    lo = np.array([RISE[b][0] for b in BANDS]); hi = np.array([RISE[b][1] for b in BANDS])
    bi = np.array([BANDS.index(b) for b in band])
    rise = np.zeros((N, D))
    truth = np.zeros((N, D), dtype=bool)
    busy_until = np.zeros(N, dtype=int)
    onsets = np.zeros(D, dtype=int)
    for t in range(D):
        free = busy_until <= t
        p = np.clip(rr * p_ili[t] + p_bg, 0, 1)
        new = free & (rng.random(N) < p)
        idx = np.where(new)[0]
        if len(idx):
            onsets[t] = len(idx)
            L = rng.integers(EPISODE_LEN[0], EPISODE_LEN[1] + 1, len(idx))
            peak = rng.uniform(lo[bi[idx]], hi[bi[idx]])
            for k in range(EPISODE_LEN[1]):
                if t + k >= D:
                    break
                ok = k < L
                j = idx[ok]
                shape = 1.0 if k > 0 else 0.85        # first day slightly lower
                rise[j, t + k] = peak[ok] * shape
                truth[j, t + k] = True
            busy_until[idx] = t + L + 3
    trans = (~truth) & (rng.random((N, D)) < P_TRANSIENT)
    rise[trans] = rng.uniform(*TRANSIENT, int(trans.sum()))
    temp = np.round(mu[:, None] + rng.normal(0, DAILY_SD, (N, D)) + rise + rng.normal(0, MEAS_SD, (N, D)), 1)
    took = rng.random((N, D)) < ADHERENCE
    return temp, took, truth, onsets


FIX = {"child": (38.0, 37.5, 1.0), "adult": (38.0, 37.5, 1.0), "older": (37.8, 37.2, 1.1)}


def personal_flags(temp, took, band, refresh: int = 7, window: int = 21, warm: int = 14, default=36.7):
    """Vectorized personal rule: baseline = median of afebrile readings in the previous `window` days,
    refreshed every `refresh` days (age-specific cutoffs). Returns flags (N, D) and deviation (N, D)."""
    N, D = temp.shape
    x = np.where(took & (temp < 37.5), temp, np.nan)
    base = np.full((N, D), default)
    for start in range(0, D, refresh):
        lo = max(0, start - window)
        if start >= warm:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                b = np.nanmedian(x[:, lo:start], axis=1)
            b = np.where(np.isnan(b), default, b)
            base[:, start:start + refresh] = b[:, None]
    cut = np.array([FIX[b] for b in band])
    fixed_c, floor_c, delta = cut[:, :1], cut[:, 1:2], cut[:, 2:3]
    dev = temp - base
    flags = took & ((temp >= fixed_c) | ((temp >= floor_c) & (dev >= delta)))
    return flags, np.where(took, dev, np.nan)
