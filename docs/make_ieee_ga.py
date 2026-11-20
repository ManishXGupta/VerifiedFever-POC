"""IEEE journal graphical abstract: 660 x 295 px, sans serif labels >= 16 px, contrast >= 4.5:1.

Writes docs/figures/gagraphic.png (and gagraphic.jpg). Needs Playwright + Chrome.
"""
import json
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
RES = ROOT / "experiments" / "results"

syn = json.loads((RES / "synthetic_results.json").read_text())
ob = json.loads((RES / "outbreak_results.json").read_text())
cost = json.loads((RES / "cost_results.json").read_text())
ag = json.loads((RES / "agent_results.json").read_text())


def first(d, *keys):
    for k in keys:
        d = d[k]
    return d


auto = f"{100 * ag['term_outbreak']['share_actions_automated']:.0f}%"
save = f"${round(cost['base']['per_visit']['net_saving'])}"

ICON = {
 "thermo": '<svg viewBox="0 0 24 24" width="34" height="34"><rect x="9" y="2" width="6" height="14" rx="3" fill="none" stroke="#b8461f" stroke-width="2"/><circle cx="12" cy="18" r="4" fill="#b8461f"/><rect x="11" y="7" width="2" height="9" fill="#b8461f"/></svg>',
 "agent": '<svg viewBox="0 0 24 24" width="34" height="34"><rect x="4" y="7" width="16" height="12" rx="3" fill="none" stroke="#1a5fb4" stroke-width="2"/><circle cx="9.5" cy="12.5" r="1.6" fill="#1a5fb4"/><circle cx="14.5" cy="12.5" r="1.6" fill="#1a5fb4"/><path d="M12 7V3" stroke="#1a5fb4" stroke-width="2"/><circle cx="12" cy="3" r="1.5" fill="#1a5fb4"/></svg>',
 "nurse": '<svg viewBox="0 0 24 24" width="34" height="34"><circle cx="9" cy="7" r="4" fill="none" stroke="#0f7a55" stroke-width="2"/><path d="M2 21c1-5 3.5-7 7-7s5 1.5 6 4" fill="none" stroke="#0f7a55" stroke-width="2"/><path d="M15 18l2.5 2.5L23 15" fill="none" stroke="#0f7a55" stroke-width="2.6"/></svg>',
 "school": '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M3 10l9-6 9 6v10H3z" fill="none" stroke="#333" stroke-width="2"/><rect x="10" y="14" width="4" height="6" fill="#333"/><path d="M12 4V1h4" stroke="#333" stroke-width="1.6" fill="none"/></svg>',
}

steps = [("thermo", "Signed reading", "home thermometer"),
         ("agent", "AI agents", "verify &amp; prepare"),
         ("nurse", "Nurse approves", "one click"),
         ("school", "School accepts", "dates only")]
kpis = [("#1a5fb4", "0.65 &rarr; 0.92", "fever detection in<br>low-normal students"),
        ("#0f7a55", "4 days", "earlier outbreak<br>alerts"),
        ("#333333", auto, "workflow actions<br>automated"),
        ("#b8461f", save, "saved per avoided<br>clinic visit")]

cards = []
for i, (ic, a, b) in enumerate(steps):
    cards.append(f'<div class="card">{ICON[ic]}<div class="l1">{a}</div><div class="l2">{b}</div></div>')
    if i < len(steps) - 1:
        cards.append('<div class="arr">&#10140;</div>')
tiles = "".join(f'<div class="kpi" style="background:{c}"><div class="n">{n}</div><div class="t">{t}</div></div>' for c, n, t in kpis)

html = f"""<!doctype html><html><head><style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ width: 660px; height: 295px; background: #fff; font-family: Roboto, Arial, Helvetica, sans-serif; color: #1d1d1d; overflow: hidden; }}
.top {{ display: flex; justify-content: space-between; align-items: baseline; padding: 8px 12px 0; }}
.title {{ font-size: 21px; font-weight: 700; }}
.sub {{ font-size: 16px; color: #1a5fb4; font-weight: 700; }}
.flow {{ display: flex; align-items: center; justify-content: space-between; padding: 6px 12px 0; }}
.card {{ width: 147px; height: 104px; border: 2px solid #d5dbe3; border-radius: 10px; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
.card:nth-child(3) {{ border-color: #1a5fb4; background: #eef4fc; }}
.l1 {{ font-size: 16px; font-weight: 700; margin-top: 2px; }}
.l2 {{ font-size: 16px; color: #444; }}
.arr {{ font-size: 16px; color: #555; }}
.guard {{ text-align: center; font-size: 16px; color: #0f7a55; font-weight: 700; padding-top: 3px; }}
.kpis {{ display: flex; gap: 8px; padding: 5px 12px 0; }}
.kpi {{ flex: 1; height: 106px; border-radius: 10px; color: #fff; padding: 8px 9px; }}
.n {{ font-size: 23px; font-weight: 700; line-height: 1.1; }}
.t {{ font-size: 16px; line-height: 1.2; margin-top: 4px; }}
</style></head><body>
<div class="top"><div class="title">Verified Fever, No Appointment</div><div class="sub">Agentic AI + IoT</div></div>
<div class="flow">{''.join(cards)}</div>
<div class="guard">Policy guard: human approval, minimum disclosure, audit log</div>
<div class="kpis">{tiles}</div>
</body></html>"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
    pg = b.new_page(viewport={"width": 660, "height": 295}, device_scale_factor=1)
    pg.set_content(html)
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(OUT / "gagraphic_raw.png"))
    pg2 = b.new_page(viewport={"width": 660, "height": 295}, device_scale_factor=4)
    pg2.set_content(html)
    pg2.wait_for_timeout(300)
    pg2.screenshot(path=str(OUT / "gagraphic_hires.png"))
    b.close()

im = Image.open(OUT / "gagraphic_raw.png").convert("RGB")
im.quantize(colors=64, method=Image.Quantize.MEDIANCUT).save(OUT / "gagraphic.png", optimize=True, dpi=(300, 300))
im.save(OUT / "gagraphic.jpg", quality=88, dpi=(300, 300), optimize=True)
(OUT / "gagraphic_raw.png").unlink()
for f in ("gagraphic.png", "gagraphic.jpg", "gagraphic_hires.png"):
    q = OUT / f
    print(f, Image.open(q).size, f"{q.stat().st_size / 1024:.1f} KB")
