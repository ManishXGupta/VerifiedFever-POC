"""Readable, colour-coded agentic architecture figure for pasting into a Word column.

Writes docs/figures/architecture_agentic_visual.png (needs Playwright + Chrome).
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures" / "architecture_agentic_visual.png"

ICON = {
    "therm": '<svg viewBox="0 0 64 64"><rect x="26" y="6" width="12" height="38" rx="6" fill="none" stroke="#1450a3" stroke-width="5"/><circle cx="32" cy="48" r="10" fill="#eb6834"/><rect x="29.5" y="22" width="5" height="22" fill="#eb6834"/></svg>',
    "phone": '<svg viewBox="0 0 64 64"><rect x="17" y="4" width="30" height="56" rx="6" fill="#16202c"/><rect x="20" y="10" width="24" height="40" rx="2" fill="#fff"/><rect x="24" y="16" width="16" height="16" fill="#16202c"/><rect x="24" y="38" width="16" height="6" rx="3" fill="#0f7a45"/></svg>',
    "hub": '<svg viewBox="0 0 64 64"><circle cx="32" cy="32" r="10" fill="#1450a3"/><g stroke="#1450a3" stroke-width="4"><path d="M32 22V8M32 42v14M22 32H8M42 32h14"/></g><g fill="#2a78d6"><circle cx="32" cy="8" r="5"/><circle cx="32" cy="56" r="5"/><circle cx="8" cy="32" r="5"/><circle cx="56" cy="32" r="5"/></g></svg>',
    "check": '<svg viewBox="0 0 64 64"><circle cx="32" cy="32" r="24" fill="#e6f4ee"/><path d="M20 33l8 8 16-18" fill="none" stroke="#0f7a45" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "doc": '<svg viewBox="0 0 64 64"><path d="M16 6h22l12 12v40H16z" fill="#fff" stroke="#1450a3" stroke-width="4"/><path d="M22 28h20M22 36h20M22 44h12" stroke="#1450a3" stroke-width="4"/><circle cx="46" cy="48" r="9" fill="#eb6834"/></svg>',
    "send": '<svg viewBox="0 0 64 64"><path d="M6 30L58 8 44 58 32 36z" fill="#2a78d6"/><path d="M32 36L58 8" stroke="#fff" stroke-width="3"/></svg>',
    "radar": '<svg viewBox="0 0 64 64"><path d="M6 52h52" stroke="#9aa3af" stroke-width="3"/><polyline points="6,50 16,48 24,44 30,34 36,18 42,24 48,40 58,50" fill="none" stroke="#1baf7a" stroke-width="5"/><circle cx="36" cy="14" r="6" fill="#eb6834"/></svg>',
    "shield": '<svg viewBox="0 0 64 64"><path d="M32 4l22 9v15c0 15-10 27-22 32C20 55 10 43 10 28V13z" fill="#f7a826"/><path d="M22 32l7 7 14-15" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "nurse": '<svg viewBox="0 0 64 64"><circle cx="32" cy="20" r="11" fill="#0f7a45"/><path d="M10 58c2-14 11-20 22-20s20 6 22 20z" fill="#1baf7a"/><path d="M32 42v10M27 47h10" stroke="#fff" stroke-width="4"/></svg>',
    "school": '<svg viewBox="0 0 64 64"><path d="M6 26L32 10l26 16z" fill="#0f7a45"/><rect x="11" y="26" width="42" height="30" fill="#e6f4ee" stroke="#0f7a45" stroke-width="4"/><rect x="28" y="38" width="8" height="18" fill="#0f7a45"/></svg>',
    "chart": '<svg viewBox="0 0 64 64"><rect x="8" y="34" width="10" height="22" fill="#0f7a45"/><rect x="27" y="22" width="10" height="34" fill="#1baf7a"/><rect x="46" y="12" width="10" height="44" fill="#0f7a45"/></svg>',
}

HTML = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:#fff;font-family:Inter,Roboto,Arial,sans-serif;color:#0b1220}}
.wrap{{width:720px;padding:16px 18px 18px;box-sizing:border-box;background:#fff}}
.row{{display:flex;gap:12px;justify-content:center}}
.box{{flex:1;border-radius:16px;padding:12px 12px;display:flex;align-items:center;gap:12px;box-sizing:border-box}}
.box svg{{width:52px;height:52px;flex:none}}
.box b{{display:block;font-size:24px;line-height:1.15}} .box span{{display:block;font-size:19px;color:#1f2937;margin-top:2px}}
.dev{{background:#e8f1fc;border:3px solid #1450a3}}
.arrow{{text-align:center;font-size:20px;font-weight:700;color:#475569;margin:4px 0;line-height:1}}
.up{{margin:4px 0 22px}}.arrow i{{display:block;font-style:normal;font-size:28px;color:#1450a3}}
.layer{{border:3px dashed #1450a3;border-radius:20px;padding:30px 12px 12px;position:relative;background:#f6f9fe}}
.tag{{position:absolute;top:-17px;left:18px;background:#1450a3;color:#fff;font-size:19px;font-weight:700;padding:5px 14px;border-radius:999px}}
.orch{{background:#dbe8fa;border:3px solid #1450a3}}
.agent{{background:#fff1ea;border:3px solid #eb6834}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}}
.guard{{background:#fff7e3;border:3px solid #d98e04;margin-top:10px}}
.human{{background:#e6f4ee;border:3px solid #0f7a45;flex-direction:column;text-align:center;gap:6px;padding:12px 6px}}
.human b{{font-size:21px}} .human span{{font-size:17px}}
</style></head><body><div class="wrap">
<div class="row">
 <div class="box dev">{ICON['therm']}<div><b>IoT thermometer</b><span>signs every reading</span></div></div>
 <div class="box dev">{ICON['phone']}<div><b>Parent app</b><span>relay + certificate wallet</span></div></div>
</div>
<div class="arrow up"><i>&#9660;</i></div>
<div class="layer"><div class="tag">Agentic AI layer</div>
 <div class="box orch">{ICON['hub']}<div><b>Orchestrator</b><span>routes events, orders the nurse queue</span></div></div>
 <div class="grid">
  <div class="box agent">{ICON['check']}<div><b>Intake agent</b><span>verify + triage</span></div></div>
  <div class="box agent">{ICON['doc']}<div><b>Certificate agent</b><span>prepares for nurse</span></div></div>
  <div class="box agent">{ICON['send']}<div><b>Communication</b><span>notice + share</span></div></div>
  <div class="box agent">{ICON['radar']}<div><b>Surveillance</b><span>outbreak alert</span></div></div>
 </div>
 <div class="box guard">{ICON['shield']}<div><b>Policy guard + audit log</b><span>humans decide &middot; no temperatures shared &middot; all logged</span></div></div>
</div>
<div class="arrow"><i>&#9660;</i></div>
<div class="row">
 <div class="box human">{ICON['nurse']}<b>Nurse</b><span>approves</span></div>
 <div class="box human">{ICON['school']}<b>School</b><span>verifies + accepts</span></div>
 <div class="box human">{ICON['chart']}<b>Public health</b><span>counts only</span></div>
</div>
</div></body></html>"""


def main():
    f = ROOT / "docs" / "_arch.html"
    f.write_text(HTML)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        pg = b.new_page(viewport={"width": 720, "height": 1000}, device_scale_factor=4)
        pg.goto(f.as_uri())
        pg.locator(".wrap").screenshot(path=str(OUT))
        b.close()
    f.unlink()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
