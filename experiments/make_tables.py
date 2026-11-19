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
    (OUT / "numbers.tex").write_text("\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()) + "\n")
    print("\n".join(f"{k} = {v}" for k, v in macros.items()))


if __name__ == "__main__":
    main()
