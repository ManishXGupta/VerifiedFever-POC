"""ProactiveHealth demo dashboard (physician, public health and person views).

Run:  python -m proactivehealth.dashboard   then open http://127.0.0.1:5050
The demo registry holds 240 consenting people with 42 days of signed readings and a
respiratory outbreak that starts in class 4B on day 33.
"""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta, timezone

import numpy as np
from flask import Flask, redirect, request, url_for

from verifiedfever.device import VirtualThermometer

from .registry import Person, Registry
from .triage import Triage

START = date(2026, 1, 5)
DAYS = 42
GROUPS = {"class": ["3A", "4B"], "workplace": ["Clinic", "Depot", "Library"], "postal_code": ["98004", "98005", "98006"]}


def build_demo(seed: int = 4):
    rng = np.random.default_rng(seed)
    reg = Registry(START)
    tri = Triage(reg)
    people = []
    for i in range(240):
        pid = f"P{i:04d}"
        if i < 50:
            band, groups = "child", {"class": GROUPS["class"][i % 2]}
        elif i < 200:
            band, groups = "adult", {"workplace": GROUPS["workplace"][i % 3]}
        else:
            band, groups = "older", {}
        groups["postal_code"] = GROUPS["postal_code"][i % 3]
        scopes = ("monitoring", "cohort", "physician") if i % 5 else ("monitoring", "cohort")
        dev = VirtualThermometer.create(f"D{i:04d}")
        reg.enroll(Person(pid, band, groups, physician_id="DR-ALVAREZ"), dev.device_id, dev.public_key, scopes)
        mu = {"child": 36.8, "adult": 36.7, "older": 36.4}[band] + rng.normal(0, 0.25)
        people.append((pid, dev, mu, band, groups))
    ill = {}
    for pid, dev, mu, band, groups in people:
        if groups.get("class") == "4B" and rng.random() < 0.55:
            ill[pid] = int(rng.integers(33, 41))
        elif rng.random() < 0.04:
            ill[pid] = int(rng.integers(10, 41))
    ill["P0001"] = 37                      # the patient shown in the physician view (class 4B)
    for d in range(DAYS):
        for pid, dev, mu, band, groups in people:
            if rng.random() > 0.9:
                continue
            rise = 0.0
            if pid in ill and ill[pid] <= d < ill[pid] + 3:
                rise = rng.uniform(0.9, 2.0) if band != "older" else rng.uniform(0.6, 1.4)
            elif pid in ill and d == ill[pid] - 1 and groups.get("class") == "4B":
                rise = rng.uniform(0.3, 0.7)
            t = round(mu + rng.normal(0, 0.15) + rise, 1)
            ts = datetime(START.year, START.month, START.day, 7, tzinfo=timezone.utc) + timedelta(days=d, minutes=int(rng.integers(0, 90)))
            res = reg.submit(dev.read(t, ts), ts + timedelta(minutes=2))
            if d == DAYS - 1:
                tri.on_reading(res)
        if d >= 14:
            for draft in tri.on_day(d, reg.daily_surveillance(d)):
                tri.pending_alerts = getattr(tri, "pending_alerts", []) + [draft]
    return reg, tri


def svg_trajectory(rows, w=620, h=210):
    if not rows:
        return "<p class='muted'>No readings shared.</p>"
    xs = [r["day"] for r in rows]; ys = [r["temp_c"] for r in rows]
    lo, hi = 35.8, max(39.6, max(ys) + 0.2)
    X = lambda d: 40 + (w - 60) * d / max(DAYS - 1, 1)  # noqa: E731
    Y = lambda t: 15 + (h - 45) * (hi - t) / (hi - lo)  # noqa: E731
    pts = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in zip(xs, ys))
    base = " ".join(f"{X(r['day']):.1f},{Y(r['baseline_c']):.1f}" for r in rows)
    g = []
    for t in (36.0, 37.0, 38.0, 39.0):
        g.append(f"<line x1='40' x2='{w - 20}' y1='{Y(t):.1f}' y2='{Y(t):.1f}' class='grid'/>"
                 f"<text x='34' y='{Y(t) + 4:.1f}' class='ax' text-anchor='end'>{t:.0f}</text>")
    fev = "".join(f"<circle cx='{X(r['day']):.1f}' cy='{Y(r['temp_c']):.1f}' r='5' class='fev'/>" for r in rows if r["fever"])
    xt = "".join(f"<text x='{X(d):.1f}' y='{h - 8}' class='ax' text-anchor='middle'>day {d}</text>" for d in (0, 14, 28, 41))
    return (f"<svg viewBox='0 0 {w} {h}' class='chart'>{''.join(g)}"
            f"<line x1='40' x2='{w - 20}' y1='{Y(38.0):.1f}' y2='{Y(38.0):.1f}' class='cut'/>"
            f"<polyline points='{base}' class='base'/><polyline points='{pts}' class='temp'/>{fev}{xt}"
            f"<text x='46' y='{Y(38.0) - 5:.1f}' class='ax'>fixed 38.0 C cutoff</text></svg>")


def svg_cohorts(reg, gt, w=620, h=210):
    gids, rep, fev, dev = reg.group_matrix(gt, DAYS)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.where(rep > 0, dev / np.maximum(rep, 1), np.nan)
    lo, hi = -0.2, max(0.6, float(np.nanmax(m)) + 0.1)
    X = lambda d: 40 + (w - 140) * d / (DAYS - 1)  # noqa: E731
    Y = lambda v: 15 + (h - 45) * (hi - v) / (hi - lo)  # noqa: E731
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#8a5cd1", "#555"]
    out = [f"<line x1='40' x2='{w - 100}' y1='{Y(0):.1f}' y2='{Y(0):.1f}' class='grid'/>"]
    for v in (0.0, 0.25, 0.5):
        out.append(f"<text x='34' y='{Y(v) + 4:.1f}' class='ax' text-anchor='end'>{v:+.2f}</text>")
    for i, g in enumerate(gids):
        pts = " ".join(f"{X(d):.1f},{Y(m[i, d]):.1f}" for d in range(DAYS) if not np.isnan(m[i, d]))
        c = colors[i % len(colors)]
        last = next((m[i, d] for d in range(DAYS - 1, -1, -1) if not np.isnan(m[i, d])), 0)
        out.append(f"<polyline points='{pts}' fill='none' stroke='{c}' stroke-width='2'/>"
                   f"<text x='{w - 95}' y='{Y(last) + 4:.1f}' class='lab' fill='{c}'>{html.escape(gt.replace('_', ' '))} {g}</text>")
    xt = "".join(f"<text x='{X(d):.1f}' y='{h - 8}' class='ax' text-anchor='middle'>day {d}</text>" for d in (0, 14, 28, 41))
    return f"<svg viewBox='0 0 {w} {h}' class='chart'>{''.join(out)}{xt}</svg>"


CSS = """
body{font-family:Inter,Roboto,Arial,sans-serif;margin:0;background:#f4f6f9;color:#1d1d1d}
header{background:#14365d;color:#fff;padding:12px 22px;display:flex;justify-content:space-between;align-items:center}
header a{color:#cfe0f5;margin-left:16px;text-decoration:none;font-size:14px}
main{padding:18px 22px;display:grid;grid-template-columns:330px 1fr;gap:16px}
.card{background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h2{font-size:15px;margin:0 0 10px} .muted{color:#666;font-size:13px}
.q{display:flex;justify-content:space-between;padding:7px 8px;border-radius:7px;font-size:13px;margin-bottom:4px;background:#f6f8fb}
.q.sel{outline:2px solid #2a78d6}
.tag{font-size:11px;padding:2px 7px;border-radius:9px;color:#fff} .urgent{background:#c0392b} .routine{background:#2a78d6}
.chart{width:100%;height:auto} .grid{stroke:#e3e7ee} .cut{stroke:#c0392b;stroke-dasharray:4 4}
.temp{fill:none;stroke:#1d1d1d;stroke-width:1.6} .base{fill:none;stroke:#1baf7a;stroke-width:2;stroke-dasharray:6 3}
.fev{fill:#eb6834} .ax{font-size:11px;fill:#666} .lab{font-size:11px;font-weight:600}
.alert{border-left:4px solid #eb6834;padding:8px 10px;background:#fff8f3;margin-bottom:8px;font-size:13px}
button{background:#14365d;color:#fff;border:0;border-radius:6px;padding:6px 12px;font-size:12px;cursor:pointer}
table{border-collapse:collapse;width:100%;font-size:13px} td,th{padding:5px 6px;border-bottom:1px solid #eee;text-align:left}
.legend span{display:inline-block;margin-right:14px;font-size:12px}
"""


def page(title, body):
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title><style>{CSS}</style></head><body>"
            "<header><b>ProactiveHealth registry</b><nav><a href='/'>Physician</a><a href='/public-health'>Public health</a>"
            "<a href='/me/P0001'>Person</a></nav></header>" + body + "</body></html>")


def create_app():
    reg, tri = build_demo()
    app = Flask(__name__)

    @app.get("/")
    def physician():
        items = tri.pending()
        sel = request.args.get("p") or (items[0].person_id if items else None)
        q = "".join(f"<a href='/?p={i.person_id}' style='text-decoration:none;color:inherit'><div class='q {'sel' if i.person_id == sel else ''}'>"
                    f"<span>{i.person_id} &middot; {html.escape(i.summary['summary'])}</span><span class='tag {i.priority}'>{i.priority}</span></div></a>"
                    for i in items[:12])
        traj = reg.trajectory(sel, "DR-ALVAREZ", "physician") if sel else None
        alerts = getattr(tri, "pending_alerts", [])[-3:]
        al = "".join(f"<div class='alert'><b>Day {a['day']}</b>: {html.escape(a['text'])}"
                     f"<form method='post' action='/confirm/{k}' style='margin-top:6px'><button>Confirm and notify public health</button></form></div>"
                     for k, a in enumerate(alerts))
        body = (f"<main><div><div class='card'><h2>Fever queue (Dr. Alvarez)</h2>{q or '<p class=muted>Empty</p>'}"
                f"<p class='muted'>AI triage orders the queue; only the physician decides.</p></div>"
                f"<div class='card' style='margin-top:14px'><h2>Cohort alerts</h2>{al or '<p class=muted>None</p>'}</div></div>"
                f"<div><div class='card'><h2>Temperature trajectory: {sel}</h2>"
                f"<div class='legend'><span>&#9473; reading</span><span style='color:#1baf7a'>- - personal baseline</span>"
                f"<span style='color:#eb6834'>&#9679; flagged fever</span></div>{svg_trajectory(traj or [])}</div>"
                f"<div class='card' style='margin-top:14px'><h2>Cohort comparison: mean deviation from personal baseline (C)</h2>"
                f"{svg_cohorts(reg, 'class')}</div></div></main>")
        return page("Physician", body)

    @app.post("/confirm/<int:k>")
    def confirm(k):
        alerts = getattr(tri, "pending_alerts", [])[-3:]
        if k < len(alerts):
            tri.confirm_alert("human", alerts[k])
        return redirect(url_for("public_health"))

    @app.get("/public-health")
    def public_health():
        rows = []
        for gt in ("class", "workplace", "postal_code"):
            for r in reg.public_health_view(gt, DAYS - 1):
                rows.append(f"<tr><td>{gt.replace('_', ' ')}</td><td>{r['group']}</td>"
                            + ("<td colspan=3 class=muted>suppressed (fewer than 5 reporters)</td>" if r["suppressed"] else
                               f"<td>{r['reporters']}</td><td>{r['fevers']}</td><td>{r['mean_deviation_c']:+.2f}</td>") + "</tr>")
        sent = "".join(f"<div class='alert'><b>Day {a['day']}</b>: {html.escape(a['text'])}</div>" for a in tri.alerts_sent) or "<p class=muted>No confirmed alerts yet.</p>"
        body = (f"<main><div class='card'><h2>Confirmed alerts</h2>{sent}</div><div class='card'><h2>Today by group (counts only)</h2>"
                f"<table><tr><th>Type</th><th>Group</th><th>Reporters</th><th>Fevers</th><th>Mean deviation</th></tr>{''.join(rows)}</table>"
                f"{svg_cohorts(reg, 'workplace')}</div></main>")
        return page("Public health", body)

    @app.get("/me/<pid>")
    def me(pid):
        traj = reg.trajectory(pid, pid, "person")
        cons = "".join(f"<tr><td>{s}</td><td>{'on' if reg.has_consent(pid, s) else 'off'}</td></tr>" for s in ("monitoring", "cohort", "physician"))
        body = (f"<main><div class='card'><h2>My consent</h2><table>{cons}</table><p class='muted'>Withdrawing stops processing and erases my readings.</p></div>"
                f"<div class='card'><h2>My readings</h2>{svg_trajectory(traj or [])}</div></main>")
        return page("Me", body)

    app.registry, app.triage = reg, tri
    return app


if __name__ == "__main__":
    create_app().run(port=5050)
