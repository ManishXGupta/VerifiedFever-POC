"""Collect every number quoted in Paper B into paper_b/numbers.json (so text and results cannot drift)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "experiments" / "results" / "paper_b"
ind = json.loads((RES / "individual_results.json").read_text())["summary"]
ili = json.loads((RES / "ilinet_results.json").read_text())
town = json.loads((RES / "town_results.json").read_text())
sysr = json.loads((RES / "system_results.json").read_text())

f2 = lambda x: f"{x:.2f}"  # noqa: E731
pct = lambda x: f"{100 * x:.0f}%"  # noqa: E731
sgn = lambda x: f"{x:+.0f}".replace("-", "−")  # noqa: E731
N = {}
for b in ("child", "adult", "older"):
    for rule, key in (("fixed 38.0", "F38"), ("fixed 37.8", "F378"), ("personal (one rule)", "P1"), ("personal (age-aware)", "PA")):
        N[f"{b}_{key}_sens"] = f2(ind[b][rule]["sens"])
        N[f"{b}_{key}_fp"] = f"{ind[b][rule]['fp_per_1000']:.1f}"

C = ili["configs"]
def cfg(name, rule="alert_personal"):
    return C[name]["summary"][rule]
m = cfg("main")
N.update({
    "ili_alerted": f"{m['alerted']} of {C['main']['summary']['n_with_onset']}",
    "ili_med": sgn(m["median_days_vs_onset_week"]),
    "ili_iqr": f"{sgn(m['iqr_days_vs_onset_week'][0])} to {sgn(m['iqr_days_vs_onset_week'][1])}",
    "ili_lead_decl": f"{m['median_lead_vs_declared_onset']:.0f}",
    "ili_lead_decl_iqr": f"{m['iqr_lead_vs_declared_onset'][0]:.0f} to {m['iqr_lead_vs_declared_onset'][1]:.0f}",
    "ili_lead_first": f"{m['median_lead_vs_first_week_published']:.0f}",
    "ili_before_decl": pct(m["share_before_declared"]),
    "ili_before_first": pct(m["share_before_first_week_published"]),
    "ili_noonset": str(m["alerts_in_seasons_without_onset"]),
    "ili_fixed_med": sgn(cfg("main", "alert_fixed")["median_days_vs_onset_week"]),
    "ili_fixed_lead_decl": f"{cfg('main', 'alert_fixed')['median_lead_vs_declared_onset']:.0f}",
    "ili_weekly_med": sgn(cfg("main", "alert_weekly")["median_days_vs_onset_week"]),
    "ili_A": f"{ili['A']:.3f}",
})
for name, key in (("N=2000", "n2k"), ("N=50000", "n50k"), ("delay=0", "d0"), ("delay=4", "d4")):
    s = cfg(name)
    N[f"{key}_alerted"] = f"{s['alerted']} of 90"
    N[f"{key}_med"] = sgn(s["median_days_vs_onset_week"])
    N[f"{key}_lead_decl"] = sgn(s["median_lead_vs_declared_onset"])
    N[f"{key}_before_decl"] = pct(s["share_before_declared"])
    N[f"{key}_noonset"] = str(s["alerts_in_seasons_without_onset"])

S = town["summary"]
for k in S:
    s = S[k]
    N[f"t_{k}_fa"] = pct(s["false_alarm_terms"])
    N[f"t_{k}_det"] = pct(s["detected"])
    N[f"t_{k}_delay"] = f"{s['median_delay_days']:.0f}" if s["median_delay_days"] is not None else "n/a"
    N[f"t_{k}_iqr"] = f"{s['iqr_delay'][0]:.0f}–{s['iqr_delay'][1]:.0f}" if s["iqr_delay"] else "n/a"
    N[f"t_{k}_cases"] = f"{s['median_cases_at_alert']:.0f}" if s["median_cases_at_alert"] is not None else "n/a"
    N[f"t_{k}_loc"] = pct(s["localized_exact_setting"]) if s.get("localized_exact_setting") is not None else "n/a"
    N[f"t_{k}_loctype"] = pct(s["localized_setting_type"]) if s.get("localized_setting_type") is not None else "n/a"
N.update({"t_n_eval": str(town["n_evaluable_outbreaks"]), "t_n_null": str(town["n_test_null"]),
          "t_n_fizzled": str(town["n_fizzled"]), "t_size_med": f"{town['outbreak_size_median']:.0f}",
          "t_size_iqr": f"{town['outbreak_size_iqr'][0]:.0f}–{town['outbreak_size_iqr'][1]:.0f}",
          "t_lead_lab": f"{town['registry_lead']['lab']['median_days_earlier']:.0f}", "t_lead_lab_n": str(town["registry_lead"]["lab"]["n"]),
          "t_lead_syn": f"{town['registry_lead']['syn']['median_days_earlier']:.0f}", "t_lead_syn_n": str(town["registry_lead"]["syn"]["n"]),
          "t_classes": str(town["n_settings"]["class"]), "t_work": str(town["n_settings"]["workplace"]),
          "t_care": str(town["n_settings"]["care_home"])})
for ty in ("class", "workplace", "care_home"):
    for k in ("reg", "lab"):
        N[f"t_by_{ty}_{k}"] = pct(town["by_seed_type"][ty][k])
tp = sysr["throughput"]
N.update({"rt_total": str(sysr["total_attempts"]), "rt_prev": str(sysr["total_prevented"]),
          "ms_reading": f"{tp['ms_per_reading_median']:.2f}", "ms_p95": f"{tp['ms_per_reading_p95']:.2f}",
          "per_hour": f"{tp['readings_per_hour_one_core'] / 1e6:.0f} million", "surv_s": f"{tp['daily_surveillance_seconds']:.2f}",
          "tp_people": f"{tp['participants']:,}", "tp_groups": str(tp["groups"]), "rt_n_attempts": str(len(sysr["red_team"]))})
out = ROOT / "paper_b"
out.mkdir(exist_ok=True)
(out / "numbers.json").write_text(json.dumps(N, indent=1, ensure_ascii=False))
(out / "red_team.json").write_text(json.dumps(sysr["red_team"], indent=1))
print(json.dumps(N, indent=1, ensure_ascii=False))
