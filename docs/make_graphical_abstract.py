"""Render the graphical abstract (docs/figures/graphical_abstract.png, paper/figures/graphical_abstract.pdf).

Numbers are read from experiments/results/*.json so the image always matches the results.
Usage:  python docs/make_graphical_abstract.py [--chrome /usr/bin/google-chrome]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "experiments" / "results"

ICONS = {
    "therm": '<svg viewBox="0 0 64 64"><rect x="26" y="6" width="12" height="38" rx="6" fill="none" stroke="#1450a3" stroke-width="4"/>'
             '<circle cx="32" cy="48" r="10" fill="#eb6834"/><rect x="30" y="22" width="4" height="22" fill="#eb6834"/>'
             '<path d="M44 14h8M44 22h6M44 30h8" stroke="#1450a3" stroke-width="3" stroke-linecap="round"/></svg>',
    "shield": '<svg viewBox="0 0 64 64"><path d="M32 6l20 8v14c0 14-9 24-20 30C21 52 12 42 12 28V14z" fill="#e8f1fc" stroke="#1450a3" stroke-width="4"/>'
              '<path d="M22 32l7 7 14-15" fill="none" stroke="#0f7a45" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "nurse": '<svg viewBox="0 0 64 64"><circle cx="32" cy="20" r="10" fill="#1450a3"/><path d="M12 56c2-12 10-18 20-18s18 6 20 18z" fill="#2a78d6"/>'
             '<rect x="27" y="42" width="10" height="10" rx="2" fill="#fff"/><path d="M32 43v8M28 47h8" stroke="#eb6834" stroke-width="2.5"/></svg>',
    "phone": '<svg viewBox="0 0 64 64"><rect x="16" y="4" width="32" height="56" rx="6" fill="#16202c"/><rect x="19" y="10" width="26" height="42" rx="2" fill="#fff"/>'
             '<rect x="23" y="16" width="8" height="8" fill="#16202c"/><rect x="33" y="16" width="8" height="8" fill="#16202c"/>'
             '<rect x="23" y="26" width="8" height="8" fill="#16202c"/><rect x="35" y="28" width="4" height="4" fill="#16202c"/>'
             '<rect x="23" y="40" width="18" height="6" rx="3" fill="#0f7a45"/></svg>',
    "school": '<svg viewBox="0 0 64 64"><path d="M8 26L32 12l24 14z" fill="#1450a3"/><rect x="12" y="26" width="40" height="28" fill="#e8f1fc" stroke="#1450a3" stroke-width="3"/>'
              '<rect x="28" y="38" width="8" height="16" fill="#1450a3"/><circle cx="46" cy="46" r="10" fill="#0f7a45"/>'
              '<path d="M41 46l4 4 7-8" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/></svg>',
    "radar": '<svg viewBox="0 0 64 64"><path d="M6 50h52" stroke="#9aa3af" stroke-width="2"/><polyline points="6,48 14,47 20,46 26,44 30,38 34,28 38,20 42,22 48,34 54,44 58,47" fill="none" stroke="#1baf7a" stroke-width="4"/>'
             '<path d="M30 10v40" stroke="#eb6834" stroke-width="3" stroke-dasharray="4 3"/><circle cx="30" cy="10" r="5" fill="#eb6834"/></svg>',
}

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;font-family:Inter,system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#fff;color:#16202c}}
.wrap{{width:1600px;padding:34px 40px 30px;box-sizing:border-box;background:linear-gradient(180deg,#f3f7fd,#ffffff)}}
h1{{margin:0;font-size:38px;letter-spacing:-.5px}} .sub{{color:#5b6472;font-size:19px;margin-top:6px}}
.flow{{display:flex;align-items:stretch;gap:10px;margin:26px 0 22px}}
.st{{flex:1;background:#fff;border:1px solid #dfe4ec;border-radius:18px;padding:16px 14px;text-align:center;box-shadow:0 3px 12px #0000000d}}
.st svg{{width:74px;height:74px}} .st b{{display:block;font-size:20px;margin-top:6px}} .st span{{font-size:15px;color:#5b6472;line-height:1.35}}
.arr{{display:flex;align-items:center;color:#9aa3af;font-size:34px}}
.kpis{{display:flex;gap:14px}} .k{{flex:1;border-radius:16px;padding:16px 18px;color:#fff}}
.k .v{{font-size:38px;font-weight:800;letter-spacing:-1px}} .k .l{{font-size:15.5px;opacity:.95;line-height:1.35}}
.k1{{background:#1450a3}} .k2{{background:#0f7a45}} .k3{{background:#c2541f}} .k4{{background:#16202c}}
.foot{{color:#6b7280;font-size:13px;margin-top:12px}}
</style></head><body><div class="wrap">
<h1>Verified Fever, No Appointment</h1>
<div class="sub">Guardrailed AI agents turn a signed home thermometer reading into a verifiable school absence certificate and an early outbreak signal</div>
<div class="flow">
<div class="st">{therm}<b>Measure</b><span>Thermometer signs<br>every daily reading</span></div><div class="arr">&#10140;</div>
<div class="st">{shield}<b>Agents verify</b><span>Intake agent: signature, replay;<br>personal baseline rule</span></div><div class="arr">&#10140;</div>
<div class="st">{nurse}<b>Validate</b><span>Nurse or physician<br>approves in one click</span></div><div class="arr">&#10140;</div>
<div class="st">{phone}<b>Share</b><span>Parent sends code,<br>QR or signed file</span></div><div class="arr">&#10140;</div>
<div class="st">{school}<b>Accept</b><span>School verifies offline;<br>sees dates + status only</span></div>
<div class="st" style="flex:1.1;border-color:#bfe6d4">{radar}<b>Agent alert</b><span>Surveillance agent finds<br>and localizes outbreaks</span></div>
</div>
<div class="kpis">
<div class="k k1"><div class="v">{sens_low_fixed:.2f} &rarr; {sens_low_pers:.2f}</div><div class="l">fever detection for students with a<br>low normal temperature (vs 38.0 &deg;C)</div></div>
<div class="k k2"><div class="v">{lead:.0f} days earlier</div><div class="l">outbreak alert than absenteeism<br>or lab reports (median)</div></div>
<div class="k k3"><div class="v">${save:.0f}</div><div class="l">saved per avoided note-only visit<br>(visit, parent time, travel)</div></div>
<div class="k k4"><div class="v">{auto:.0f}% automated</div><div class="l">workflow actions run by agents;<br>{rt}/{rt} guardrail attacks stopped</div></div>
</div>
<div class="foot">Results from simulation (500 students; 480-student school terms); cost from 2026 price, wage and mileage data. Next: real thermometer bench test and school pilot. Code: github.com/ManishXGupta/VerifiedFever-POC</div>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default="/usr/bin/google-chrome")
    args = ap.parse_args()
    syn = json.loads((RES / "synthetic_results.json").read_text())["summary"]
    ob = json.loads((RES / "outbreak_results.json").read_text())
    cost = json.loads((RES / "cost_results.json").read_text())
    tam = json.loads((RES / "tamper_results.json").read_text())
    ag = json.loads((RES / "agent_results.json").read_text())
    auto = 100 * ag["term_outbreak"]["share_actions_automated"]
    rt = sum(v["prevented"] for v in ag["red_team"].values())
    att = sum(v["trials"] for v in tam["attacks"].values())
    lead = min(ob["lead_time_vs"]["Absence"]["median_days_earlier"], ob["lead_time_vs"]["Confirmed"]["median_days_earlier"])
    html = HTML.format(**ICONS, sens_low_fixed=syn["by_baseline"]["fixed38"]["low"]["sensitivity"][0],
                       sens_low_pers=syn["by_baseline"]["personal"]["low"]["sensitivity"][0], lead=lead,
                       save=cost["base"]["per_visit"]["net_saving"], att=att, auto=auto, rt=rt)
    src = ROOT / "docs" / "graphical_abstract.html"
    src.write_text(html)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=args.chrome, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1600, "height": 700}, device_scale_factor=2)
        pg.goto(src.as_uri())
        el = pg.locator(".wrap")
        el.screenshot(path=str(ROOT / "docs" / "figures" / "graphical_abstract.png"))
        el.screenshot(path=str(ROOT / "paper" / "figures" / "graphical_abstract.png"))
        # column-width variant: 3 x 2 stage grid and 2 x 2 headline tiles
        col_css = ("<style>.wrap{width:860px;padding:26px 28px}h1{font-size:34px}.sub{font-size:17px}"
                   ".flow{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:18px 0}.arr{display:none}"
                   ".st{flex:none!important;padding:12px 8px;min-width:0}"
                   ".st svg{width:60px;height:60px}.st b{font-size:19px}.st span{font-size:14px}"
                   ".kpis{display:grid;grid-template-columns:1fr 1fr;gap:12px}.k{box-sizing:border-box}"
                   ".k .v{font-size:32px}.k .l{font-size:14.5px}.foot{font-size:12.5px}</style></head>")
        col = ROOT / "docs" / "graphical_abstract_column.html"
        col.write_text(html.replace("</head>", col_css, 1))
        pg2 = b.new_page(viewport={"width": 860, "height": 900}, device_scale_factor=4)
        pg2.goto(col.as_uri())
        pg2.locator(".wrap").screenshot(path=str(ROOT / "docs" / "figures" / "graphical_abstract_column.png"))
        # two copy-paste-friendly images for Word (large text, no footnote): 1) workflow, 2) results
        base = ("<style>.wrap{width:720px;padding:22px 24px}.foot{display:none}.arr{display:none}"
                ".flow{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:16px 0 4px}"
                ".st{flex:none!important;padding:14px 10px;min-width:0}.st svg{width:70px;height:70px}"
                ".st b{font-size:25px}.st span{font-size:19px}"
                ".kpis{display:grid;grid-template-columns:1fr 1fr;gap:14px}.k{box-sizing:border-box;padding:18px 18px}"
                ".k .v{font-size:36px;white-space:nowrap}.k .l{font-size:19px;line-height:1.35}")
        parts = {"graphical_abstract_part1_workflow.png": base + "h1{font-size:36px}.sub{font-size:20px}.kpis{display:none}</style></head>",
                 "graphical_abstract_part2_results.png": base + "h1,.sub,.flow{display:none}</style></head>"}
        for name, css in parts.items():
            f = ROOT / "docs" / ("_" + name.replace(".png", ".html"))
            page = html.replace("</head>", css, 1)
            if "part2" in name:
                page = page.replace('<div class="kpis">', '<div class="kpis" data-p2="1">')
                k0 = page.index('<div class="kpis"'); k1 = page.index('<div class="foot">')
                page = page[:k0] + page[k0:k1].replace("<br>", " ") + page[k1:]
            f.write_text(page)
            pg3 = b.new_page(viewport={"width": 720, "height": 900}, device_scale_factor=4)
            pg3.goto(f.as_uri())
            pg3.locator(".wrap").screenshot(path=str(ROOT / "docs" / "figures" / name))
            f.unlink()
        # one compact merged image with dark, high-contrast text (for pasting into a Word column)
        compact = ("<style>.wrap{width:760px;padding:18px 20px 20px;background:#fff}.foot{display:none}.arr{display:none}"
                   "h1{font-size:32px;color:#0b1220}.sub{font-size:18px;color:#1f2937;margin-top:4px}"
                   ".flow{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0 12px}"
                   ".st{flex:none!important;padding:10px 6px;min-width:0;border:2px solid #c9d3e0;box-shadow:none}"
                   ".st svg{width:54px;height:54px}.st b{font-size:22px;color:#0b1220;margin-top:2px}"
                   ".st span{font-size:16.5px;color:#111827;line-height:1.3}"
                   ".kpis{display:grid;grid-template-columns:1fr 1fr;gap:10px}.k{box-sizing:border-box;padding:12px 14px}"
                   ".k .v{font-size:32px;white-space:nowrap}.k .l{font-size:16.5px;line-height:1.3;opacity:1}</style></head>")
        import re as _re
        compact = compact.replace("</style>", ".sub{display:none}.st span{display:none}.st b{font-size:26px;margin-top:6px}"
                                  ".st{padding:14px 6px}.st svg{width:62px;height:62px}"
                                  ".k .v{font-size:38px}.k .l{font-size:22px;font-weight:600}</style>")
        page = html.replace("</head>", compact, 1)
        short = {"k1": "fever detection, low-normal students", "k2": "outbreak alert", "k3": "saved per avoided visit",
                 "k4": "of routine actions run by AI agents"}
        for k, t in short.items():
            page = _re.sub(r'(<div class="k ' + k + r'"><div class="v">.*?</div><div class="l">).*?(</div>)',
                           lambda m: m.group(1) + t + m.group(2), page, count=1, flags=_re.S)
        page = _re.sub(r'>(\d+)% automated<', r'>\1%<', page)
        f = ROOT / "docs" / "_compact.html"
        f.write_text(page)
        pg4 = b.new_page(viewport={"width": 760, "height": 900}, device_scale_factor=4)
        pg4.goto(f.as_uri())
        pg4.locator(".wrap").screenshot(path=str(ROOT / "docs" / "figures" / "graphical_abstract_compact.png"))
        f.unlink()
        b.close()
    print("graphical abstract written")


if __name__ == "__main__":
    main()
