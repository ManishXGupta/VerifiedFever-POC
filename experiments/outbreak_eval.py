"""Early influenza outbreak detection from daily verified temperature readings.

Simulates one school term per run (480 students in 20 classes, 120 school days) with
background non-influenza fevers, ordinary absences and, in "outbreak" terms, a stochastic
influenza outbreak spreading within classes and across the school. The same simulated
terms feed four surveillance signals, so differences come only from the signal:

  VF-personal  daily count of students flagged febrile by the VerifiedFever personal rule
  VF-fixed     the same readings with one fixed 38.0 C cutoff
  Absence      all-cause daily absences (what schools already record)
  Confirmed    laboratory-confirmed influenza reported to the school (care seeking,
               testing and reporting delay)

Count signals use the same detector: a school-level one-sided CUSUM against a trailing
baseline, OR a class-level count threshold. Detector thresholds are tuned separately for
each signal on calibration terms so that at most 10% of outbreak-free terms raise any false
alert; results are then measured on fresh terms.

Usage:  python experiments/outbreak_eval.py
Output: experiments/results/outbreak_results.json, outbreak_example.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verifiedfever.rules import Policy, is_febrile, personal_baseline  # noqa: E402

OUT = ROOT / "experiments" / "results"
P = dict(
    n_classes=20, class_size=24, n_days=120, warmup=14,
    mu_mean=36.7, mu_sd=0.25, mu_min=36.0, mu_max=37.4, daily_sd=0.15, meas_sd=0.10,
    adherence=0.85,                      # share of mornings a reading is taken
    bg_fever_onset=0.008, bg_fever_len=(1, 3), fever_rise=(1.0, 2.5),
    p_transient=0.03, transient_rise=(0.3, 0.8),
    p_absent_other=0.045, day_effect_sd=0.25,  # ordinary absences, with school-wide day effects
    p_home_if_febrile=0.85,
    # influenza outbreak
    seed_window=(30, 90), latent=(1, 2), p_febrile=0.75, flu_fever_len=(2, 4),
    beta_class=0.65, beta_school=0.13,
    # confirmed-case reporting
    p_seek_care=0.40, p_tested=0.50, report_delay=(3, 6), sporadic_confirmed=0.00005,
)
FA_TARGET = 0.10
DETECT_WINDOW = 21  # days after first symptomatic case


def simulate(seed: int, outbreak: bool, p: dict = P):
    rng = np.random.default_rng(seed)
    C, S, D = p["n_classes"], p["class_size"], p["n_days"]
    N = C * S
    cls = np.repeat(np.arange(C), S)
    mu = np.clip(rng.normal(p["mu_mean"], p["mu_sd"], N), p["mu_min"], p["mu_max"])
    rise = np.zeros((N, D))
    febrile_truth = np.zeros((N, D), dtype=bool)
    # background (non-influenza) fevers
    for i in range(N):
        t = 0
        while t < D:
            if rng.random() < p["bg_fever_onset"]:
                L = int(rng.integers(p["bg_fever_len"][0], p["bg_fever_len"][1] + 1))
                rise[i, t:t + L] = rng.uniform(*p["fever_rise"], min(L, D - t))
                febrile_truth[i, t:t + L] = True
                t += L + 2
            else:
                t += 1
    trans = (~febrile_truth) & (rng.random((N, D)) < p["p_transient"])
    rise[trans] = rng.uniform(*p["transient_rise"], int(trans.sum()))

    flu_onset = np.full(N, -1)
    flu_febrile = np.zeros(N, dtype=bool)
    sym_onsets: list[int] = []
    if outbreak:
        state = np.zeros(N, dtype=int)  # 0 S, 1 infected
        inf_day = np.full(N, -1)
        t0 = int(rng.integers(*p["seed_window"]))
        idx = int(rng.integers(N))
        state[idx], inf_day[idx] = 1, t0 - 2
        for t in range(t0 - 2, D):
            # who is infectious and attending today
            inf_today = (state == 1)
            att = np.zeros(N, dtype=bool)
            for j in np.where(inf_today)[0]:
                if flu_onset[j] < 0:
                    flu_onset[j] = inf_day[j] + int(rng.integers(p["latent"][0], p["latent"][1] + 1))
                    flu_febrile[j] = rng.random() < p["p_febrile"]
                    L = int(rng.integers(p["flu_fever_len"][0], p["flu_fever_len"][1] + 1))
                    a, b = flu_onset[j], min(D, flu_onset[j] + L)
                    if a < D:
                        if flu_febrile[j]:
                            rise[j, a:b] = np.maximum(rise[j, a:b], rng.uniform(*p["fever_rise"], b - a))
                            febrile_truth[j, a:b] = True
                        else:
                            rise[j, a:b] = np.maximum(rise[j, a:b], rng.uniform(0.0, 0.5, b - a))
                o = flu_onset[j]
                infectious = (o - 1) <= t <= (o + 3)
                if not infectious:
                    continue
                home = flu_febrile[j] and t >= o and rng.random() < p["p_home_if_febrile"]
                att[j] = not home
            if t < 0:
                continue
            ic = np.bincount(cls[att], minlength=C)
            lam = p["beta_class"] * ic[cls] / S + p["beta_school"] * att.sum() / N
            new = (state == 0) & (rng.random(N) < 1 - np.exp(-lam))
            state[new], inf_day[new] = 1, t
        sym_onsets = sorted(int(flu_onset[j]) for j in range(N) if flu_febrile[j] and 0 <= flu_onset[j] < D)

    temp = np.round(mu[:, None] + rng.normal(0, p["daily_sd"], (N, D)) + rise
                    + rng.normal(0, p["meas_sd"], (N, D)), 1)
    took = rng.random((N, D)) < p["adherence"]
    # absences
    day_eff = np.exp(rng.normal(0, p["day_effect_sd"], D))
    other = rng.random((N, D)) < np.clip(p["p_absent_other"] * day_eff, 0, 0.5)[None, :]
    home_fever = febrile_truth & (rng.random((N, D)) < p["p_home_if_febrile"])
    absent = other | home_fever
    # confirmed influenza reports to the school
    reports = np.zeros(D, dtype=int)
    for j in range(N):
        if flu_febrile[j] and 0 <= flu_onset[j] < D and rng.random() < p["p_seek_care"] * p["p_tested"]:
            r = flu_onset[j] + int(rng.integers(p["report_delay"][0], p["report_delay"][1] + 1))
            if r < D:
                reports[r] += 1
    reports += rng.poisson(p["sporadic_confirmed"] * N, D)
    return dict(cls=cls, mu=mu, temp=temp, took=took, absent=absent, reports=reports,
                sym_onsets=sym_onsets, n_infected=int((flu_onset >= 0).sum()))


def vf_flags(sim, policy: Policy):
    temp, took = sim["temp"], sim["took"]
    N, D = temp.shape
    personal = np.zeros((N, D), dtype=bool)
    for i in range(N):
        hist: list[float] = []
        row, tk = temp[i], took[i]
        for t in range(D):
            if not tk[t]:
                continue
            x = float(row[t])
            b = personal_baseline(hist, policy).value_c
            personal[i, t] = is_febrile(x, b, policy)
            hist.append(x)
    fixed = took & (temp >= policy.fixed_cutoff_c)
    return personal, fixed


def signals(sim, policy):
    personal, fixed = vf_flags(sim, policy)
    cls, C = sim["cls"], int(sim["cls"].max()) + 1
    out = {}
    for name, m in (("VF-personal", personal), ("VF-fixed", fixed), ("Absence", sim["absent"])):
        school = m.sum(0)
        by_class = np.stack([m[cls == c].sum(0) for c in range(C)])
        out[name] = (school, by_class)
    out["Confirmed"] = sim["reports"]
    return out


def cusum_alarm_days(x, warmup, k=0.5, window=(28, 3)):
    """Return array S_t of the one-sided CUSUM statistic (NaN before warm-up)."""
    D = len(x)
    S = np.full(D, np.nan)
    s = 0.0
    for t in range(D):
        lo, hi = max(0, t - window[0]), t - window[1]
        if t < warmup or hi - lo < 7:
            continue
        base = x[lo:hi]
        mu = base.mean()
        sd = max(np.sqrt(mu), base.std(ddof=1), 1.0)
        s = max(0.0, s + (x[t] - mu) / sd - k)
        S[t] = s
    return S


def first_alert(sig, h, c_thr, warmup):
    school, by_class = sig
    S = cusum_alarm_days(school.astype(float), warmup)
    hit = (np.nan_to_num(S, nan=-1) > h) | (by_class.max(0) >= c_thr)
    hit[:warmup] = False
    idx = np.where(hit)[0]
    return int(idx[0]) if len(idx) else None


def first_alert_confirmed(rep, m, warmup, window=7):
    for t in range(warmup, len(rep)):
        if rep[max(0, t - window + 1):t + 1].sum() >= m:
            return t
    return None


H_GRID = [2, 3, 4, 5, 6, 8, 10, 12, 14, 17, 20, 25, 30]
C_GRID = {"VF-personal": [2, 3, 4, 5, 6], "VF-fixed": [2, 3, 4, 5, 6], "Absence": [4, 5, 6, 7, 8, 9, 10, 12]}
M_GRID = [1, 2, 3, 4, 5, 6]


def evaluate_alert(alert, sim):
    if not sim["sym_onsets"]:
        return None
    t1 = sim["sym_onsets"][0]
    if alert is None or alert < t1 - 2 or alert > t1 + DETECT_WINDOW:
        return dict(detected=False, delay=None, cases=None)
    return dict(detected=True, delay=alert - t1, cases=sum(1 for o in sim["sym_onsets"] if o <= alert))


def precompute(seeds, outbreak, policy):
    res = []
    for s in seeds:
        sim = simulate(s, outbreak)
        if outbreak and len(sim["sym_onsets"]) < 5:
            res.append(None)  # outbreak fizzled: not a detectable event
            continue
        res.append((sim, signals(sim, policy)))
    return res


def calibrate(null_runs, ob_runs, warmup):
    chosen = {}
    for name in ("VF-personal", "VF-fixed", "Absence"):
        best = None
        for h in H_GRID:
            for c in C_GRID[name]:
                fa = np.mean([first_alert(sg[name], h, c, warmup) is not None for _, sg in null_runs])
                if fa > FA_TARGET:
                    continue
                delays = []
                for sim, sg in ob_runs:
                    e = evaluate_alert(first_alert(sg[name], h, c, warmup), sim)
                    delays.append(e["delay"] if e["detected"] else DETECT_WINDOW + 5)
                score = float(np.mean(delays))
                if best is None or score < best[0]:
                    best = (score, h, c, float(fa))
        chosen[name] = {"h": best[1], "class_threshold": best[2], "calib_false_alarm": best[3]}
    best = None
    for m in M_GRID:
        fa = np.mean([first_alert_confirmed(sg["Confirmed"], m, warmup) is not None for _, sg in null_runs])
        if fa > FA_TARGET:
            continue
        delays = []
        for sim, sg in ob_runs:
            e = evaluate_alert(first_alert_confirmed(sg["Confirmed"], m, warmup), sim)
            delays.append(e["delay"] if e["detected"] else DETECT_WINDOW + 5)
        score = float(np.mean(delays))
        if best is None or score < best[0]:
            best = (score, m, float(fa))
    chosen["Confirmed"] = {"m_reports_in_7_days": best[1], "calib_false_alarm": best[2]}
    return chosen


def alert_for(name, sg, cfg, warmup):
    if name == "Confirmed":
        return first_alert_confirmed(sg["Confirmed"], cfg["m_reports_in_7_days"], warmup)
    return first_alert(sg[name], cfg["h"], cfg["class_threshold"], warmup)


def main():
    t_start = time.time()
    policy = Policy()
    w = P["warmup"]
    cal_null = [r for r in precompute(range(10_000, 10_150), False, policy)]
    cal_ob = [r for r in precompute(range(20_000, 20_160), True, policy) if r is not None]
    cfg = calibrate(cal_null, cal_ob, w)
    ev_null = precompute(range(30_000, 30_300), False, policy)
    ev_ob_all = precompute(range(40_000, 40_400), True, policy)
    ev_ob = [r for r in ev_ob_all if r is not None]
    methods = ["VF-personal", "VF-fixed", "Absence", "Confirmed"]
    summary = {}
    for name in methods:
        fa = float(np.mean([alert_for(name, sg, cfg[name], w) is not None for _, sg in ev_null]))
        evs = [evaluate_alert(alert_for(name, sg, cfg[name], w), sim) for sim, sg in ev_ob]
        det = [e for e in evs if e["detected"]]
        d = np.array([e["delay"] for e in det]) if det else np.array([np.nan])
        cs = np.array([e["cases"] for e in det]) if det else np.array([np.nan])
        summary[name] = {
            "false_alarm_terms": fa, "detection_rate": len(det) / len(evs),
            "delay_median": float(np.median(d)), "delay_q1": float(np.percentile(d, 25)),
            "delay_q3": float(np.percentile(d, 75)), "delay_mean": float(np.mean(d)),
            "cases_at_alert_median": float(np.median(cs)), "config": cfg[name],
            "delays": [e["delay"] if e["detected"] else None for e in evs],
        }
    sizes = [len(sim["sym_onsets"]) for sim, _ in ev_ob]
    # paired lead time of VF-personal over each comparator, on outbreaks detected by both
    lead = {}
    for other in ("VF-fixed", "Absence", "Confirmed"):
        diffs = []
        for sim, sg in ev_ob:
            a = evaluate_alert(alert_for("VF-personal", sg, cfg["VF-personal"], w), sim)
            b = evaluate_alert(alert_for(other, sg, cfg[other], w), sim)
            if a["detected"] and b["detected"]:
                diffs.append(b["delay"] - a["delay"])
        lead[other] = {"n_pairs": len(diffs), "median_days_earlier": float(np.median(diffs)) if diffs else None,
                       "mean_days_earlier": float(np.mean(diffs)) if diffs else None}
    result = {
        "params": P, "fa_target": FA_TARGET, "detect_window_days": DETECT_WINDOW,
        "n_eval_null_terms": len(ev_null), "n_eval_outbreak_terms": len(ev_ob),
        "n_outbreaks_fizzled": sum(r is None for r in ev_ob_all),
        "symptomatic_cases_median": float(np.median(sizes)), "symptomatic_cases_q1": float(np.percentile(sizes, 25)),
        "symptomatic_cases_q3": float(np.percentile(sizes, 75)),
        "summary": summary, "lead_time_vs": lead, "runtime_s": round(time.time() - t_start, 1),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "outbreak_results.json").write_text(json.dumps(result, indent=2))
    # one example term for the figure
    sim, sg = ev_ob[0]
    ex = {"sym_onsets": sim["sym_onsets"], "series": {k: (v[0].tolist() if k != "Confirmed" else v.tolist())
                                                         for k, v in sg.items()},
          "alerts": {k: alert_for(k, sg, cfg[k], w) for k in methods}}
    (OUT / "outbreak_example.json").write_text(json.dumps(ex))
    print(json.dumps({k: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items() if kk != "delays"}
                      for k, v in summary.items()}, indent=1))
    print("lead:", lead)
    print("outbreak size median", result["symptomatic_cases_median"], "fizzled", result["n_outbreaks_fizzled"],
          "runtime", result["runtime_s"])


if __name__ == "__main__":
    main()
