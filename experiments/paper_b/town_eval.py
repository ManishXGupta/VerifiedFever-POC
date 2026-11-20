"""E3. Cohort synchrony detection and localization in a simulated town.

Town: 12,000 registry participants in 30 postal codes; children in classes of about 25,
working adults in 100 workplaces, and older adults at home or in 6 care homes. Each 120-day
term has sporadic febrile illness; outbreak terms add an influenza-like outbreak seeded in one
setting (a class, a workplace or a care home) that spreads within the setting, the postal code
and the town. The same terms feed three surveillance signals:

  Registry       daily verified readings with the age-aware personal rule; per-group count test
                 (Poisson, Bonferroni over all settings and postal codes), per-group drift test
                 (synchronized rise of members' personal deviations), and a town CUSUM
  Clinic visits  syndromic surveillance: symptomatic people who seek care (35%, 1-3 days after
                 onset), reported the next day by postal code; postal-code Poisson test + town CUSUM
  Lab-confirmed  a test for half of those who seek care, reported 3-6 days later, plus sporadic
                 unrelated confirmed influenza (0.03 a day); town 7-day count

Each signal's thresholds are tuned on calibration terms so that at most 10% of outbreak-free
terms raise any alert, then measured on fresh terms. Localization: the group named by the first
alert (registry: setting or postal code; clinic visits: postal code) versus the seed setting.
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import poisson

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))
import pop_model as pm  # noqa: E402

OUT = ROOT / "experiments" / "results" / "paper_b"
P = dict(N=12000, n_postal=30, class_size=25, n_work=100, n_care=6, care_size=60, D=120, warmup=28,
         p_bg_resp=0.0004, seed_window=(35, 90), n_index=2,
         beta={"class": 0.55, "workplace": 0.40, "care_home": 0.60}, beta_postal=0.05, beta_town=0.025,
         p_symptomatic=0.75, p_isolate=0.70, latent=(1, 2),
         p_seek=0.35, seek_delay=(1, 3), p_test=0.5, lab_delay=(3, 6), sporadic_lab=0.03)
FA_TARGET, WINDOW = 0.10, 21
TYPES = ("class", "workplace", "care_home")


def build_town(rng, p=P):
    band, mu, rr = pm.population(p["N"], rng)
    N = p["N"]
    postal = rng.integers(0, p["n_postal"], N)
    setting = np.full(N, -1)
    stype = []
    sid = 0
    kids = np.where(band == "child")[0]
    rng.shuffle(kids)
    for k in range(0, len(kids), p["class_size"]):
        setting[kids[k:k + p["class_size"]]] = sid; stype.append("class"); sid += 1
    older = np.where(band == "older")[0]
    rng.shuffle(older)
    for c in range(p["n_care"]):
        setting[older[c * p["care_size"]:(c + 1) * p["care_size"]]] = sid; stype.append("care_home"); sid += 1
    workers = np.where(band == "adult")[0]
    workers = workers[rng.random(len(workers)) < 0.7]
    sizes = rng.lognormal(0, 0.6, p["n_work"]); sizes = sizes / sizes.sum()
    wid = rng.choice(p["n_work"], len(workers), p=sizes)
    setting[workers] = sid + wid; stype += ["workplace"] * p["n_work"]
    return dict(band=band, mu=mu, rr=rr, postal=postal, setting=setting, stype=np.array(stype), N=N)


def simulate(town, rng, outbreak: bool, p=P):
    N, D = town["N"], p["D"]
    band, setting, postal, stype = town["band"], town["setting"], town["postal"], town["stype"]
    S_n = len(stype)
    ssize = np.bincount(setting[setting >= 0], minlength=S_n).astype(float)
    psize = np.bincount(postal, minlength=p["n_postal"]).astype(float)
    bi = np.array([pm.BANDS.index(b) for b in band])
    lo = np.array([pm.RISE[b][0] for b in pm.BANDS]); hi = np.array([pm.RISE[b][1] for b in pm.BANDS])
    rise = np.zeros((N, D)); truth = np.zeros((N, D), dtype=bool)
    sym_onset = np.full(N, -1)
    busy = np.zeros(N, dtype=int)

    def start_episode(idx, t, febrile_mask):
        L = rng.integers(pm.EPISODE_LEN[0], pm.EPISODE_LEN[1] + 1, len(idx))
        pk = rng.uniform(lo[bi[idx]], hi[bi[idx]])
        pk = np.where(febrile_mask, pk, rng.uniform(0.0, 0.5, len(idx)))
        for k in range(pm.EPISODE_LEN[1]):
            if t + k >= D:
                break
            ok = k < L
            j = idx[ok]
            rise[j, t + k] = np.maximum(rise[j, t + k], pk[ok] * (0.85 if k == 0 else 1.0))
            truth[j[febrile_mask[ok]], t + k] = True
        busy[idx] = t + L + 3

    # sporadic illness
    for t in range(D):
        free = busy <= t
        new = free & (rng.random(N) < town["rr"] * p["p_bg_resp"] + pm.P_BACKGROUND)
        idx = np.where(new)[0]
        if len(idx):
            start_episode(idx, t, np.ones(len(idx), dtype=bool))

    seed_setting, seed_type, t0, index_postal = -1, None, None, -1
    infected = np.zeros(N, dtype=bool)
    flu_onset = np.full(N, -1)
    flu_feb = np.zeros(N, dtype=bool)
    if outbreak:
        w = {"class": 0.45, "workplace": 0.35, "care_home": 0.20}
        seed_type = rng.choice(TYPES, p=[w[x] for x in TYPES])
        cand = np.where(stype == seed_type)[0]
        seed_setting = int(rng.choice(cand))
        members = np.where(setting == seed_setting)[0]
        idx0 = rng.choice(members, min(p["n_index"], len(members)), replace=False)
        index_postal = int(postal[idx0[0]])
        t0 = int(rng.integers(*p["seed_window"]))
        inf_day = np.full(N, -1)
        infected[idx0] = True; inf_day[idx0] = t0
        for t in range(t0, D):
            new_inf = np.where(infected & (flu_onset < 0))[0]
            for j in new_inf:
                flu_onset[j] = inf_day[j] + int(rng.integers(p["latent"][0], p["latent"][1] + 1))
                flu_feb[j] = rng.random() < p["p_symptomatic"]
                if flu_onset[j] < D:
                    start_episode(np.array([j]), int(flu_onset[j]), np.array([flu_feb[j]]))
                    if flu_feb[j]:
                        sym_onset[j] = flu_onset[j]
            infectious = infected & (flu_onset >= 0) & (flu_onset - 1 <= t) & (t <= flu_onset + 3)
            home = infectious & flu_feb & (t >= flu_onset) & (rng.random(N) < p["p_isolate"])
            out = infectious & ~home
            I_s = np.bincount(setting[out & (setting >= 0)], minlength=S_n)
            I_p = np.bincount(postal[infectious], minlength=p["n_postal"])
            lam = p["beta_postal"] * I_p[postal] / psize[postal] + p["beta_town"] * out.sum() / N
            has = setting >= 0
            beta_s = np.array([p["beta"][x] for x in stype])
            lam[has] += beta_s[setting[has]] * I_s[setting[has]] / ssize[setting[has]]
            new = (~infected) & (rng.random(N) < 1 - np.exp(-lam))
            infected[new] = True; inf_day[new] = t + 1

    temp = np.round(town["mu"][:, None] + rng.normal(0, pm.DAILY_SD, (N, D)) + rise + rng.normal(0, pm.MEAS_SD, (N, D)), 1)
    trans = (~truth) & (rise == 0) & (rng.random((N, D)) < pm.P_TRANSIENT)
    temp[trans] += np.round(rng.uniform(*pm.TRANSIENT, int(trans.sum())), 1)
    took = rng.random((N, D)) < pm.ADHERENCE

    # syndromic clinic visits and lab confirmations (any febrile illness can produce a visit; only flu tests positive)
    onset_all = np.where(truth[:, 1:] & ~truth[:, :-1])
    visits = np.zeros((p["n_postal"], D)); lab = np.zeros(D)
    for i, t in zip(onset_all[0], onset_all[1] + 1):
        if rng.random() < p["p_seek"]:
            v = t + int(rng.integers(p["seek_delay"][0], p["seek_delay"][1] + 1)) + 1
            if v < D:
                visits[postal[i], v] += 1
            if infected[i] and flu_feb[i] and rng.random() < p["p_test"]:
                r = v + int(rng.integers(p["lab_delay"][0], p["lab_delay"][1] + 1))
                if r < D:
                    lab[r] += 1
    lab += rng.poisson(p["sporadic_lab"], D)          # sporadic confirmed influenza unrelated to the outbreak
    first_sym = int(sym_onset[sym_onset >= 0].min()) if (sym_onset >= 0).any() else None
    return dict(temp=temp, took=took, visits=visits, lab=lab, seed_setting=seed_setting, seed_type=seed_type,
                index_postal=index_postal, first_sym=first_sym, sym_onset=sym_onset,
                n_infected=int(infected.sum()))


# ---------------- detector statistics (vectorized over days)

def trail_sum(x, window=28, guard=3):
    c = np.concatenate([np.zeros(x.shape[:-1] + (1,)), np.cumsum(x, -1)], -1)
    D = x.shape[-1]
    t = np.arange(D)
    lo, hi = np.maximum(0, t - window), np.maximum(0, t - guard)
    return c[..., hi] - c[..., lo], hi - lo


def count_pvals(fl, rp, prior=0.004):
    fs, _ = trail_sum(fl); rs, _ = trail_sum(rp)
    rate = (fs + prior * 50) / (rs + 50)
    p = poisson.sf(fl - 1, np.maximum(rate * rp, 1e-9))
    p[fl < 3] = 1.0
    return p


def drift_z(dev, rp, min_rep=8):
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.where(rp > 0, dev / np.maximum(rp, 1), np.nan)
    valid = ~np.isnan(m)
    m0 = np.nan_to_num(m)
    s1, _ = trail_sum(m0); s2, _ = trail_sum(m0 ** 2); n, _ = trail_sum(valid.astype(float))
    with np.errstate(invalid="ignore", divide="ignore"):
        mu = s1 / n; var = np.maximum(s2 / n - mu ** 2, 0) * n / np.maximum(n - 1, 1)
        z = (m - mu) / np.sqrt(var + (0.25 / np.sqrt(np.maximum(rp, 1))) ** 2)
    z[(rp < min_rep) | (n < 7)] = np.nan
    return z


def town_cusum(x, warmup, k=0.5):
    from proactivehealth.anomaly import cusum
    return cusum(x, warmup=warmup, k=k, sd_floor=np.sqrt(max(np.mean(x[:warmup]), 1.0)))


def registry_stats(sim, town, rule="personal", use_drift=True, p=P):
    if rule == "personal":
        flags, dev = pm.personal_flags(sim["temp"], sim["took"], town["band"])
    else:
        flags = sim["took"] & (sim["temp"] >= 38.0); dev = np.where(sim["took"], 0.0, np.nan)
    took = sim["took"].astype(float)
    S_n = len(town["stype"])
    has = town["setting"] >= 0
    def agg(arr, key, G):
        out = np.zeros((G, arr.shape[1]))
        np.add.at(out, key, arr)
        return out
    fl_s = agg(flags[has].astype(float), town["setting"][has], S_n)
    rp_s = agg(took[has], town["setting"][has], S_n)
    dv_s = agg(np.nan_to_num(dev[has]), town["setting"][has], S_n)
    fl_p = agg(flags.astype(float), town["postal"], p["n_postal"])
    rp_p = agg(took, town["postal"], p["n_postal"])
    dv_p = agg(np.nan_to_num(dev), town["postal"], p["n_postal"])
    fl, rp, dv = np.vstack([fl_s, fl_p]), np.vstack([rp_s, rp_p]), np.vstack([dv_s, dv_p])
    G = fl.shape[0]
    pv = count_pvals(fl, rp) * G                      # Bonferroni-adjusted
    z = drift_z(dv, rp) if use_drift else np.full(fl.shape, np.nan)
    S = town_cusum(flags.sum(0).astype(float), p["warmup"])
    zz = np.nan_to_num(z, nan=-9.0)
    return dict(minp=pv.min(0), gp=pv.argmin(0), maxz=zz.max(0), gz=zz.argmax(0), S=np.nan_to_num(S, nan=-1.0),
                fl=fl, n_settings=S_n)


def syndromic_stats(sim, p=P):
    v = sim["visits"]
    pv = count_pvals(v, np.full_like(v, 400.0), prior=0.0004) * v.shape[0]
    S = town_cusum(v.sum(0), p["warmup"])
    return dict(minp=pv.min(0), gp=pv.argmin(0), S=np.nan_to_num(S, nan=-1.0))


def first_alert_registry(st, a, zt, h, warm):
    hit = (st["minp"] < a) | (st["maxz"] > zt) | (st["S"] > h)
    hit[:warm] = False
    idx = np.where(hit)[0]
    if not len(idx):
        return None, None, None
    t = int(idx[0])
    if st["minp"][t] < a:
        return t, "count", int(st["gp"][t])
    if st["maxz"][t] > zt:
        return t, "drift", int(st["gz"][t])
    lo = max(1, t - 2)
    rec = st["fl"][:, lo:t + 1].mean(1) - st["fl"][:, max(0, lo - 14):lo].mean(1)
    return t, "town", int(np.argmax(rec[:st["n_settings"]]))


def first_alert_syndromic(st, a, h, warm):
    hit = (st["minp"] < a) | (st["S"] > h)
    hit[:warm] = False
    idx = np.where(hit)[0]
    if not len(idx):
        return None, None
    t = int(idx[0])
    return t, int(st["gp"][t])


def first_alert_lab(lab, m, warm):
    for t in range(warm, len(lab)):
        if lab[max(0, t - 6):t + 1].sum() >= m:
            return t
    return None


A_GRID = [1e-2, 1e-3, 1e-4, 1e-5, 1e-6, 1e-8, 0.0]
Z_GRID = [3.5, 4.0, 4.5, 5.0, 6.0, 8.0, 1e9]
H_GRID = [4, 6, 8, 10, 14, 20, 30, 1e9]
M_GRID = [1, 2, 3, 4, 5, 6, 8]


def run_terms(n, outbreak, seed, variants):
    rng = np.random.default_rng(seed)
    town = build_town(np.random.default_rng(7))
    res = []
    for _ in range(n):
        sim = simulate(town, rng, outbreak)
        r = {"seed_setting": sim["seed_setting"], "seed_type": sim["seed_type"], "first_sym": sim["first_sym"],
             "index_postal": sim["index_postal"], "n_infected": sim["n_infected"], "sym_onset": sim["sym_onset"]}
        for name, kw in variants.items():
            r[name] = registry_stats(sim, town, **kw)
        r["syn"] = syndromic_stats(sim)
        r["lab"] = sim["lab"]
        res.append(r)
    return town, res


VARIANTS = {"reg": {"rule": "personal", "use_drift": True},
            "reg_nodrift": {"rule": "personal", "use_drift": False},
            "reg_fixed": {"rule": "fixed", "use_drift": False}}


def evaluate_alert(r, t, warm):
    if r["first_sym"] is None:
        return False, None
    ok = t is not None and r["first_sym"] <= t <= r["first_sym"] + WINDOW
    return ok, (t - r["first_sym"]) if ok else None


def tune(null, outb, fn, grid):
    best = None
    for params in grid:
        fa = np.mean([fn(r, params)[0] is not None for r in null])
        if fa > FA_TARGET:
            continue
        hits = [evaluate_alert(r, fn(r, params)[0], P["warmup"]) for r in outb]
        det = np.mean([h[0] for h in hits])
        delays = [h[1] for h in hits if h[0]]
        key = (det, -np.median(delays) if delays else -99)
        if best is None or key > best[0]:
            best = (key, params, fa)
    return best


def main():
    t0 = time.time()
    warm = P["warmup"]
    N_CAL, N_TEST_NULL, N_TEST_OB = 300, 300, 300
    town, cal_null = run_terms(N_CAL, False, 101, VARIANTS)
    _, cal_ob = run_terms(N_CAL, True, 102, VARIANTS)
    cal_ob = [r for r in cal_ob if (r["sym_onset"] >= 0).sum() >= 5]
    print("calibration sims", f"{time.time() - t0:.0f}s", flush=True)
    detectors = {}
    for v in VARIANTS:
        grid = list(itertools.product(A_GRID, Z_GRID if v == "reg" else [1e9], H_GRID))
        fn = lambda r, prm, v=v: first_alert_registry(r[v], prm[0], prm[1], prm[2], warm)  # noqa: E731
        detectors[v] = (tune(cal_null, cal_ob, fn, grid), fn)
    fn_s = lambda r, prm: first_alert_syndromic(r["syn"], prm[0], prm[1], warm)  # noqa: E731
    detectors["syn"] = (tune(cal_null, cal_ob, fn_s, list(itertools.product(A_GRID, H_GRID))), fn_s)
    fn_l = lambda r, prm: (first_alert_lab(r["lab"], prm[0], warm),)  # noqa: E731
    detectors["lab"] = (tune(cal_null, cal_ob, fn_l, [(m,) for m in M_GRID]), fn_l)
    print({k: (v[0][1], round(v[0][2], 3)) for k, v in detectors.items()}, flush=True)

    _, te_null = run_terms(N_TEST_NULL, False, 201, VARIANTS)
    _, te_ob_all = run_terms(N_TEST_OB, True, 202, VARIANTS)
    te_ob = [r for r in te_ob_all if (r["sym_onset"] >= 0).sum() >= 5]
    print("test sims", f"{time.time() - t0:.0f}s", flush=True)
    stype = town["stype"]
    summary, per_ob = {}, []
    for name, ((_, prm, fa_cal), fn) in detectors.items():
        fa = float(np.mean([fn(r, prm)[0] is not None for r in te_null]))
        hits, delays, cases, loc_exact, loc_type, loc_postal, loc_n = [], [], [], 0, 0, 0, 0
        for i, r in enumerate(te_ob):
            out = fn(r, prm)
            t = out[0]
            ok, dly = evaluate_alert(r, t, warm)
            hits.append(ok)
            if ok:
                delays.append(dly)
                cases.append(int(((r["sym_onset"] >= 0) & (r["sym_onset"] <= t)).sum()))
                if name.startswith("reg"):
                    g = out[2]; loc_n += 1
                    if g == r["seed_setting"]:
                        loc_exact += 1; loc_type += 1
                    elif g < len(stype) and stype[g] == r["seed_type"]:
                        loc_type += 1
                    if g >= len(stype) and g - len(stype) == r["index_postal"]:
                        loc_postal += 1
                elif name == "syn":
                    loc_n += 1; loc_postal += int(out[1] == r["index_postal"])
            if len(per_ob) < len(te_ob):
                per_ob.append({"seed_type": r["seed_type"], "n_infected": r["n_infected"]})
            per_ob[i][name] = dly if ok else None
        summary[name] = {"params": list(prm), "false_alarm_terms": round(fa, 3), "detected": round(float(np.mean(hits)), 3),
                         "median_delay_days": float(np.median(delays)) if delays else None,
                         "iqr_delay": [float(np.percentile(delays, 25)), float(np.percentile(delays, 75))] if delays else None,
                         "median_cases_at_alert": float(np.median(cases)) if cases else None,
                         "localized_exact_setting": round(loc_exact / loc_n, 3) if loc_n and name.startswith("reg") else None,
                         "localized_setting_type": round(loc_type / loc_n, 3) if loc_n and name.startswith("reg") else None,
                         "localized_index_postal": round(loc_postal / loc_n, 3) if loc_n else None, "n_localized": loc_n}
    by_type = {}
    for ty in TYPES:
        rows = [x for x in per_ob if x["seed_type"] == ty]
        by_type[ty] = {"n": len(rows), **{k: round(float(np.mean([x[k] is not None for x in rows])), 3) for k in detectors}}
    lead = {}
    for other in ("syn", "lab"):
        both = [x["reg"] - x[other] for x in per_ob if x["reg"] is not None and x[other] is not None]
        lead[other] = {"n": len(both), "median_days_earlier": float(-np.median(both)) if both else None}
    sizes = [x["n_infected"] for x in per_ob]
    fsum = lambda r: int((r["sym_onset"] >= 0).sum())  # noqa: E731
    res = {"params": {k: v for k, v in P.items()}, "n_test_null": N_TEST_NULL, "n_test_outbreak": N_TEST_OB,
           "n_evaluable_outbreaks": len(te_ob), "n_fizzled": N_TEST_OB - len(te_ob),
           "n_settings": {ty: int((stype == ty).sum()) for ty in TYPES}, "summary": summary, "by_seed_type": by_type,
           "registry_lead": lead, "outbreak_size_median": float(np.median(sizes)),
           "outbreak_size_iqr": [float(np.percentile(sizes, 25)), float(np.percentile(sizes, 75))], "per_outbreak": per_ob}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "town_results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: v for k, v in res.items() if k not in ("per_outbreak", "params")}, indent=1, default=str))
    print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
