"""Generate LaTeX tables and number macros from saved results, so every number in
the paper comes straight from experiments/results/*.json (no hand copying).

Usage:  python experiments/make_tables.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "experiments" / "results"
OUT = ROOT / "paper" / "generated"
NAMES = {"fixed38": "Fixed 38.0\\,\\textdegree C", "fixed37.5": "Fixed 37.5\\,\\textdegree C",
         "personal": "Personal (ours)"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    syn = json.loads((RES / "synthetic_results.json").read_text())
    s = syn["summary"]
    tam = json.loads((RES / "tamper_results.json").read_text())

    rows = []
    for m, label in NAMES.items():
        v = s["overall"][m]
        low = s["by_baseline"][m]["low"]["sensitivity"][0]
        rows.append(f"{label} & {v['sensitivity'][0]:.3f} & {low:.3f} & {v['specificity'][0]:.4f} & "
                    f"{v['ppv'][0]:.3f} & {v['f1'][0]:.3f} & {v['false_cert_per_1000'][0]:.1f} \\\\")
    (OUT / "table_detection.tex").write_text(
        "\\begin{table}[t]\\centering\\caption{Fever-day detection on the synthetic cohort "
        f"(mean of {syn['n_seeds']} seeds; {s['days_eval']:,} student-days per seed after warm-up)}}"
        "\\label{tab:detection}\\footnotesize\\setlength{\\tabcolsep}{3pt}\n"
        "\\begin{tabular}{lcccccc}\\hline\n"
        "Rule & Sens. & Sens.\\,low & Spec. & PPV & F1 & FC \\\\\\hline\n"
        + "\n".join(rows) +
        "\n\\hline\\end{tabular}\\\\[2pt]\\parbox{\\columnwidth}{\\scriptsize Sens.\\,low: students in the "
        "lowest tertile of normal temperature. FC: false certificates per 1000 student-days.}\\end{table}\n")

    trows = []
    for name, v in tam["attacks"].items():
        trows.append(f"{name} & {v['expected_check']} & {v['detected']}/{v['trials']} \\\\")
    g = tam["genuine"]
    (OUT / "table_tamper.tex").write_text(
        "\\begin{table}[t]\\centering\\caption{Tamper-evidence tests (50 enrolled virtual thermometers)}"
        "\\label{tab:tamper}\\footnotesize\\setlength{\\tabcolsep}{3pt}\n"
        "\\begin{tabular}{p{4.1cm}p{2.0cm}r}\\hline\n"
        "Attack & Caught by & Detected \\\\\\hline\n" + "\n".join(trows) +
        f"\n\\hline Genuine readings (accepted) & -- & {g['accepted']}/{g['submitted']} \\\\"
        "\n\\hline\\end{tabular}\\end{table}\n")

    sens_rows = list(csv.DictReader(open(RES / "synthetic_sensitivity.csv")))

    def rng(method, key):
        vals = [float(r[key]) for r in sens_rows if r["method"] == method]
        return min(vals), max(vals)

    o = s["overall"]
    t = tam["timing"]
    macros = {
        "SensFixed": f"{o['fixed38']['sensitivity'][0]:.2f}",
        "SensFixedLow": f"{s['by_baseline']['fixed38']['low']['sensitivity'][0]:.2f}",
        "SensPers": f"{o['personal']['sensitivity'][0]:.2f}",
        "SensPersLow": f"{s['by_baseline']['personal']['low']['sensitivity'][0]:.2f}",
        "SensLow": f"{o['fixed37.5']['sensitivity'][0]:.2f}",
        "FCFixed": f"{o['fixed38']['false_cert_per_1000'][0]:.1f}",
        "FCPers": f"{o['personal']['false_cert_per_1000'][0]:.1f}",
        "FCLow": f"{o['fixed37.5']['false_cert_per_1000'][0]:.1f}",
        "EpiFixed": f"{100 * o['fixed38']['episode_detection'][0]:.1f}",
        "EpiPers": f"{100 * o['personal']['episode_detection'][0]:.1f}",
        "FOneFixed": f"{o['fixed38']['f1'][0]:.2f}",
        "FOnePers": f"{o['personal']['f1'][0]:.2f}",
        "SpecHighLow": f"{s['by_baseline']['fixed37.5']['high']['specificity'][0]:.3f}",
        "ColdSensPers": f"{s['cold_start']['personal']['sensitivity']:.2f}",
        "FeverDays": f"{s['mean_fever_days']:.0f}",
        "Episodes": f"{s['mean_episodes']:.0f}",
        "NSeeds": str(syn["n_seeds"]),
        "SensRangePers": "{:.2f}--{:.2f}".format(*rng("personal", "sensitivity")),
        "SensRangeFixed": "{:.2f}--{:.2f}".format(*rng("fixed38", "sensitivity")),
        "FCRangePers": "{:.1f}--{:.1f}".format(*rng("personal", "false_cert_per_1000")),
        "FCRangeLow": "{:.1f}--{:.1f}".format(*rng("fixed37.5", "false_cert_per_1000")),
        "SignMs": f"{t['sign_reading']['median_ms']:.3f}",
        "VerifyMs": f"{t['verify_signature']['median_ms']:.3f}",
        "EtoEMs": f"{t['end_to_end_reading_to_certificate']['median_ms']:.2f}",
        "EtoEPms": f"{t['end_to_end_reading_to_certificate']['p95_ms']:.2f}",
        "ReadingBytes": str(t["signed_reading_bytes"]),
    }
    # ---- outbreak table
    ob = json.loads((RES / "outbreak_results.json").read_text())
    names = {"VF-personal": "Verified fever, personal", "VF-fixed": "Verified fever, fixed 38.0\\,\\textdegree C",
             "Confirmed": "Confirmed-case reports", "Absence": "All-cause absence"}
    orows = []
    for k, label in names.items():
        v = ob["summary"][k]
        orows.append(f"{label} & {100 * v['detection_rate']:.0f}\\% & {v['delay_median']:.0f} ({v['delay_q1']:.0f}--{v['delay_q3']:.0f})"
                     f" & {v['cases_at_alert_median']:.0f} & {100 * v['false_alarm_terms']:.0f}\\% \\\\")
    (OUT / "table_outbreak.tex").write_text(
        "\\begin{table}[t]\\centering\\caption{School influenza outbreak detection "
        f"({ob['n_eval_outbreak_terms']} outbreak terms, {ob['n_eval_null_terms']} outbreak-free terms)}}"
        "\\label{tab:outbreak}\\footnotesize\\setlength{\\tabcolsep}{2.5pt}\n"
        "\\begin{tabular}{lcccc}\\hline\n"
        "Signal & Detected & Delay, d & Cases & False alarm \\\\\\hline\n" + "\n".join(orows) +
        "\n\\hline\\end{tabular}\\\\[2pt]\\parbox{\\columnwidth}{\\scriptsize Detected: within "
        f"{ob['detect_window_days']} days of the first symptomatic case. Delay: median (IQR) days from that case. "
        "Cases: median symptomatic cases by the alert day. False alarm: share of outbreak-free terms with any alert.}\\end{table}\n")

    # ---- cost table
    cost = json.loads((RES / "cost_results.json").read_text())
    def row(label, f):
        return label + " & " + " & ".join(f(cost[k]) for k in ("low", "base", "high")) + " \\\\"
    crow = [
        row("Visit price", lambda c: f"\\${c['per_visit']['visit_price']:.0f}"),
        row("Parent time (h)", lambda c: f"{c['per_visit']['parent_hours_saved']:.1f}"),
        row("Parent time value", lambda c: f"\\${c['per_visit']['parent_time_cost']:.0f}"),
        row("Travel", lambda c: f"\\${c['per_visit']['travel']:.0f}"),
        row("\\textbf{Net saving per visit}", lambda c: f"\\textbf{{\\${c['per_visit']['net_saving']:.0f}}}"),
        row("Note-only visits avoided$^{\\dagger}$", lambda c: f"{c['per_school_year']['visits_avoided']:.0f}"),
        row("\\textbf{Annual saving}$^{\\dagger}$", lambda c: f"\\textbf{{\\${c['per_school_year']['annual_net_saving']:,.0f}}}"),
        row("Parent hours saved$^{\\dagger}$", lambda c: f"{c['per_school_year']['parent_hours_saved']:.0f}"),
        row("Thermometer payback (yr)", lambda c: f"{c['per_school_year']['payback_years']:.1f}"),
    ]
    (OUT / "table_cost.tex").write_text(
        "\\begin{table}[t]\\centering\\caption{Estimated savings when a verified certificate replaces a note-only visit}"
        "\\label{tab:cost}\\footnotesize\\setlength{\\tabcolsep}{4pt}\n\\begin{tabular}{lrrr}\\hline\n"
        "& Low & Base & High \\\\\\hline\n" + "\n".join(crow) +
        "\n\\hline\\end{tabular}\\\\[2pt]\\parbox{\\columnwidth}{\\scriptsize $^{\\dagger}$Per 500-student school per year, "
        "with 10/20/30\\% of students otherwise making one note-only visit. Net of 3\\,min nurse review; "
        "\\$30 thermometer per student. Wage \\$37.53/h, vehicle \\$0.76/mile.}\\end{table}\n")
    sv = ob["summary"]
    macros.update({
        "ObDetPers": f"{100 * sv['VF-personal']['detection_rate']:.0f}",
        "ObDetFixed": f"{100 * sv['VF-fixed']['detection_rate']:.0f}",
        "ObDetAbs": f"{100 * sv['Absence']['detection_rate']:.0f}",
        "ObDetConf": f"{100 * sv['Confirmed']['detection_rate']:.0f}",
        "ObDelayPers": f"{sv['VF-personal']['delay_median']:.0f}",
        "ObDelayAbs": f"{sv['Absence']['delay_median']:.0f}",
        "ObDelayConf": f"{sv['Confirmed']['delay_median']:.0f}",
        "ObCasesPers": f"{sv['VF-personal']['cases_at_alert_median']:.0f}",
        "ObCasesAbs": f"{sv['Absence']['cases_at_alert_median']:.0f}",
        "ObCasesConf": f"{sv['Confirmed']['cases_at_alert_median']:.0f}",
        "ObLeadAbs": f"{ob['lead_time_vs']['Absence']['median_days_earlier']:.0f}",
        "ObLeadConf": f"{ob['lead_time_vs']['Confirmed']['median_days_earlier']:.0f}",
        "ObPairsAbs": str(ob['lead_time_vs']['Absence']['n_pairs']),
        "ObPairsConf": str(ob['lead_time_vs']['Confirmed']['n_pairs']),
        "ObTerms": str(ob["n_eval_outbreak_terms"]), "ObNull": str(ob["n_eval_null_terms"]),
        "ObSize": f"{ob['symptomatic_cases_median']:.0f}",
        "ObSizeQone": f"{ob['symptomatic_cases_q1']:.0f}", "ObSizeQthree": f"{ob['symptomatic_cases_q3']:.0f}",
        "ObFizzled": str(ob["n_outbreaks_fizzled"]),
        "CostVisitBase": f"{cost['base']['per_visit']['net_saving']:.0f}",
        "CostVisitLow": f"{cost['low']['per_visit']['net_saving']:.0f}",
        "CostVisitHigh": f"{cost['high']['per_visit']['net_saving']:.0f}",
        "CostSchoolBase": f"{cost['base']['per_school_year']['annual_net_saving']:,.0f}",
        "CostSchoolLow": f"{cost['low']['per_school_year']['annual_net_saving']:,.0f}",
        "CostSchoolHigh": f"{cost['high']['per_school_year']['annual_net_saving']:,.0f}",
        "HoursSchoolBase": f"{cost['base']['per_school_year']['parent_hours_saved']:.0f}",
        "PaybackBase": f"{cost['base']['per_school_year']['payback_years']:.1f}",
        "NAttacks": str(sum(v["trials"] for v in tam["attacks"].values())),
    })
    (OUT / "numbers.tex").write_text("\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()) + "\n")
    print("\n".join(f"{k} = {v}" for k, v in macros.items()))


if __name__ == "__main__":
    main()
