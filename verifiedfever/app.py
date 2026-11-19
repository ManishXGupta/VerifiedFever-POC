"""Demo web app: parent app (thermometer + certificate wallet + share), nurse console,
school portal (receive, verify, accept), public verify page, and a JSON API.

Run:  python -m verifiedfever.app      then open http://127.0.0.1:5000

DEMO ONLY: the virtual thermometers' private keys are held in this process so
the browser can "press the thermometer button". In a real deployment the key
never leaves the device and the device posts to /api/readings itself.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
from datetime import datetime, timedelta, timezone

import segno
from flask import (Flask, Response, jsonify, redirect, render_template_string, request,
                   url_for)

from .device import VirtualThermometer
from .rules import fixed_rule
from .service import FeverCertService

DEMO_STUDENTS = [  # (student_id, name, normal temperature used to seed history)
    ("S-1001", "Aarav", 36.3),
    ("S-1002", "Maya", 36.6),
    ("S-1003", "Liam", 36.9),
    ("S-1004", "Sofia", 37.1),
]
NORMALS = {sid: t for sid, _, t in DEMO_STUDENTS}


def build_demo(db_path: str = ":memory:", seed: int = 7):
    rng = random.Random(seed)
    svc = FeverCertService(db_path)
    devices: dict[str, VirtualThermometer] = {}
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for sid, name, normal in DEMO_STUDENTS:
        dev = VirtualThermometer.create(f"THERM-{sid[-4:]}")
        svc.enroll(dev.device_id, sid, name, dev.public_key, consent=True, now=now - timedelta(days=30))
        devices[sid] = dev
        for d in range(14, 0, -1):  # two weeks of normal morning readings
            ts = now - timedelta(days=d)
            svc.submit(dev.read(normal + rng.gauss(0, 0.12), ts=ts), now=ts + timedelta(minutes=1))
    return svc, devices


CSS = """
:root{--ink:#16202c;--muted:#64707f;--line:#e5e8ee;--bg:#f3f5f9;--brand:#1450a3;--brand2:#2a78d6;
--ok:#0f7a45;--okbg:#e5f6ed;--warn:#9a5b00;--warnbg:#fff3df;--bad:#b3261e;--badbg:#fdeceb}
*{box-sizing:border-box}body{font-family:Inter,system-ui,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
header{background:linear-gradient(90deg,#0f3d7d,#2a78d6);color:#fff;padding:14px 28px;display:flex;align-items:center;gap:26px}
header .logo{font-weight:700;font-size:18px;letter-spacing:.2px;display:flex;align-items:center;gap:8px}
header a{color:#dce9ff;text-decoration:none;font-size:14px;padding:6px 10px;border-radius:8px}
header a.on,header a:hover{background:#ffffff26;color:#fff}
main{max-width:1060px;margin:26px auto;padding:0 18px}
.card{background:#fff;border-radius:14px;padding:20px 22px;margin-bottom:18px;box-shadow:0 1px 2px #0000000d,0 4px 14px #0000000a}
h2{margin:.1em 0 .4em;font-size:22px}h3{margin:.1em 0 .6em;font-size:17px}
.muted{color:var(--muted);font-size:13px}.row{display:flex;gap:18px;flex-wrap:wrap}.col{flex:1;min-width:300px}
table{border-collapse:collapse;width:100%}td,th{padding:8px 9px;border-bottom:1px solid var(--line);text-align:left;font-size:14px}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
button,.btn{font:inherit;font-size:14px;padding:9px 14px;border-radius:9px;border:0;cursor:pointer;background:var(--brand);color:#fff;text-decoration:none;display:inline-block}
button.ghost{background:#eef2f8;color:var(--brand)}button.red{background:var(--bad)}button.green{background:var(--ok)}
select,input{font:inherit;font-size:14px;padding:8px 10px;border-radius:9px;border:1px solid #cdd3dc;background:#fff}
.chip{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}
.c-ok{background:var(--okbg);color:var(--ok)}.c-warn{background:var(--warnbg);color:var(--warn)}.c-bad{background:var(--badbg);color:var(--bad)}.c-info{background:#e8f1fc;color:var(--brand)}
.phone{width:380px;border-radius:34px;background:#0d1520;padding:12px;box-shadow:0 10px 30px #0003;margin:0 auto}
.screen{background:#fff;border-radius:24px;overflow:hidden;min-height:640px}
.appbar{background:linear-gradient(135deg,#1450a3,#2a78d6);color:#fff;padding:18px 18px 22px}
.appbar .t{font-size:13px;opacity:.85}.appbar .n{font-size:22px;font-weight:700;margin-top:2px}
.big{font-size:44px;font-weight:700;letter-spacing:-1px}.pad{padding:16px 18px}
.tile{border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin-bottom:10px}
.qr{display:flex;justify-content:center;padding:6px}.code{font-family:ui-monospace,Menlo,monospace;font-size:26px;font-weight:700;letter-spacing:3px;text-align:center}
.steps{display:flex;gap:12px;flex-wrap:wrap}.step{flex:1;min-width:170px;background:#f7f9fc;border-radius:12px;padding:12px 14px;border:1px solid var(--line)}
.step b{display:block;color:var(--brand);font-size:13px;margin-bottom:4px}
code{font-size:12px;word-break:break-all}
"""

LAYOUT = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VerifiedFever POC</title><style>{{ css|safe }}</style></head><body>
<header><span class="logo">&#127777;&#xFE0F; VerifiedFever</span>
{% for ep,label in nav %}<a class="{{ 'on' if active==ep }}" href="{{ url_for(ep) }}">{{ label }}</a>{% endfor %}
</header><main>{{ body|safe }}</main></body></html>"""

NAV = [("home", "Overview"), ("parent", "Parent app"), ("nurse", "Nurse console"),
       ("school", "School portal"), ("verify_form", "Verify")]

STATUS_CHIP = {"approved": ("Approved", "c-ok"), "pending_validation": ("Awaiting nurse", "c-warn"),
               "clinical_review": ("Clinical review", "c-bad"), "rejected": ("Rejected", "c-bad")}


def qr_svg(text: str, scale: int = 5) -> str:
    return segno.make(text, error="m").svg_inline(scale=scale, dark="#0d1520")


def create_app(db_path: str = ":memory:") -> Flask:
    app = Flask(__name__)
    svc, devices = build_demo(db_path)
    app.config["svc"], app.config["devices"] = svc, devices
    last_signed: dict[str, dict] = {}
    shares: dict[str, dict] = {}
    policy = svc.policy

    def page(active, body_tpl, **ctx):
        ctx.setdefault("chips", STATUS_CHIP)
        body = render_template_string(body_tpl, **ctx)
        return render_template_string(LAYOUT, body=body, css=CSS, nav=NAV, active=active)

    @app.get("/")
    def home():
        return page("home", """<div class="card"><h2>Verified Fever, No Appointment</h2>
<p>A registered thermometer signs each reading. The rule engine compares it with the student's own
baseline and the school's fever policy. A nurse or physician validates the certificate with one click,
the parent shares it straight to the school, and the school verifies the signature and accepts it.
The school never sees temperatures.</p>
<div class="steps"><div class="step"><b>1 · Measure</b>Signed reading from the registered thermometer</div>
<div class="step"><b>2 · Decide</b>Personal baseline + school cutoff</div>
<div class="step"><b>3 · Validate</b>Nurse or physician approves in one click</div>
<div class="step"><b>4 · Share</b>Parent sends code, QR or file to the school</div>
<div class="step"><b>5 · Accept</b>School verifies the signature; absence excused</div></div></div>
<div class="card"><h3>Two-minute demo</h3><ol>
<li><b>Parent app</b>: pick <b>Aarav</b> (normal 36.3 °C), take <b>37.6 °C</b>. A fixed 38.0 °C rule would miss it; a certificate is created.</li>
<li>Pick <b>Sofia</b> (normal 37.1 °C), take <b>37.6 °C</b>: no certificate (only +0.5 °C for her).</li>
<li><b>Nurse console</b>: approve Aarav's certificate.</li>
<li>Back in the <b>Parent app</b>, open Aarav's wallet and press <b>Share with school</b>, then <b>Send to school</b> (or type the code in the School portal).</li>
<li><b>School portal</b>: the certificate is verified and accepted. Try an altered file: it is refused.</li></ol></div>""")

    # ------------------------------------------------------------------ parent app
    @app.route("/parent", methods=["GET", "POST"])
    def parent():
        result, compare = None, None
        sid = request.values.get("student_id", DEMO_STUDENTS[0][0])
        if request.method == "POST":
            temp = float(request.form["temp_c"])
            signed = devices[sid].read(temp)
            last_signed[sid] = copy.deepcopy(signed)
            result = svc.submit(signed, claimed_student_id=sid).to_dict()
            compare = fixed_rule(temp, policy.fixed_cutoff_c)
        return parent_page(sid, result, compare)

    def parent_page(sid, result, compare, note=None):
        name = dict((s, n) for s, n, _ in DEMO_STUDENTS)[sid]
        return page("parent", """<div class="row"><div class="col"><div class="phone"><div class="screen">
<div class="appbar"><div class="t">Parent app · {{ name }}</div><div class="n">Good morning</div></div>
<div class="pad"><form method="post" action="{{ url_for('parent') }}">
<div class="tile"><div class="muted">Child</div><select name="student_id" onchange="location='{{ url_for('parent') }}?student_id='+this.value">
{% for s in students %}<option value="{{s.student_id}}" {% if s.student_id==sid %}selected{% endif %}>{{s.student_name}}</option>{% endfor %}</select></div>
<div class="tile"><div class="muted">Registered thermometer reading (°C)</div>
<input name="temp_c" type="number" step="0.1" min="34" max="43" value="37.6" required style="width:110px;font-size:22px;font-weight:700">
<button style="float:right;margin-top:4px">Take signed reading</button></div></form>
{% if result %}<div class="tile">{% if result.verdict=='accepted' %}
<div class="muted">Today</div><div class="big">{{ '%.1f'|format(temp) }}°C</div>
<div>Normal for {{ name }}: {{ '%.1f'|format(result.baseline_c) }} °C · <b>{{ '%+.1f'|format(result.deviation_c) }} °C</b></div>
<p>{% if result.certificate_id %}<span class="chip c-warn">Certificate sent to nurse</span>{% elif result.decision=='watch' %}<span class="chip c-info">Watch: slightly above normal</span>{% else %}<span class="chip c-ok">No fever</span>{% endif %}</p>
<div class="muted">A fixed 38.0 °C rule would {{ 'flag' if compare else 'NOT flag' }} this reading.</div>
{% else %}<span class="chip c-bad">Rejected: {{ result.verdict }}</span>{% endif %}</div>{% endif %}
{% if note %}<div class="tile muted">{{ note|safe }}</div>{% endif %}
<div class="tile"><b>Certificate wallet</b>{% for c in certs %}<div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px">
<div><div style="font-weight:600">{{ c.absence_start }} → {{ c.absence_end }}</div>
<span class="chip {{ chips[c.status][1] }}">{{ chips[c.status][0] }}</span>{% if c.school_decision %} <span class="chip c-ok">School accepted</span>{% endif %}</div>
{% if c.status=='approved' and not c.school_decision %}<form method="post" action="{{ url_for('share', cert_id=c.cert_id) }}"><button>Share with school</button></form>{% endif %}</div>
{% else %}<div class="muted" style="margin-top:6px">No certificates yet.</div>{% endfor %}</div>
</div></div></div></div>
<div class="col"><div class="card"><h3>Evidence tests</h3><p class="muted">These show that edited or replayed readings are rejected.</p>
<form method="post" action="{{ url_for('tamper') }}" style="display:inline"><input type="hidden" name="student_id" value="{{sid}}"><button class="red">Tamper: edit 36.6 → 38.5 after signing</button></form>
<form method="post" action="{{ url_for('replay') }}" style="display:inline"><input type="hidden" name="student_id" value="{{sid}}"><button class="ghost">Replay last reading</button></form></div>
<div class="card"><h3>Recent readings</h3><table><tr><th>Time (UTC)</th><th>°C</th><th>Check</th><th>Decision</th><th>Baseline</th></tr>
{% for r in history %}<tr><td>{{r.ts[5:16].replace('T',' ')}}</td><td>{{r.temp_c}}</td><td>{{r.verdict}}</td><td>{{r.decision or ''}}</td><td>{{ '%.2f'|format(r.baseline_c) if r.baseline_c else '' }}</td></tr>{% endfor %}</table></div></div></div>""",
                    students=svc.students(), sid=sid, name=name, result=result, compare=compare, note=note,
                    temp=(last_signed[sid]["payload"]["temp_c"] if sid in last_signed else 0),
                    certs=svc.parent_certificates(sid), history=svc.student_readings(sid, 8))

    @app.post("/parent/tamper")
    def tamper():
        sid = request.form["student_id"]
        signed = devices[sid].read(36.6)
        signed["payload"]["temp_c"] = 38.5
        res = svc.submit(signed, claimed_student_id=sid).to_dict()
        return parent_page(sid, res, None, note="<b>Tamper test:</b> signed at 36.6 °C, edited to 38.5 °C afterwards.")

    @app.post("/parent/replay")
    def replay():
        sid = request.form["student_id"]
        if sid not in last_signed:
            return parent_page(sid, None, None, note="Take a reading first, then replay it.")
        res = svc.submit(copy.deepcopy(last_signed[sid]), claimed_student_id=sid).to_dict()
        return parent_page(sid, res, None, note="<b>Replay test:</b> the last genuine reading was sent again.")

    @app.post("/parent/share/<cert_id>")
    def share(cert_id):
        sh = svc.share(cert_id)
        shares[sh["share_code"]] = sh
        return redirect(url_for("share_view", code=sh["share_code"]))

    @app.get("/parent/shared/<code>")
    def share_view(code):
        sh = shares[code]
        rec = sh["package"]["certificate"]
        name = dict((s, n) for s, n, _ in DEMO_STUDENTS)[rec["student_id"]]
        link = request.host_url.rstrip("/") + url_for("school", code=code)
        return page("parent", """<div class="phone"><div class="screen">
<div class="appbar"><div class="t">Share with school</div><div class="n">{{ name }}'s absence certificate</div></div>
<div class="pad"><div class="tile"><div class="muted">Absence</div><b>{{ rec.absence_start }} → {{ rec.absence_end }}</b>
<div><span class="chip c-ok">Approved by {{ rec.validated_by }}</span></div>
<div class="muted" style="margin-top:6px">Shared with the school: dates, reason and status only. No temperatures.</div></div>
<div class="qr">{{ qr|safe }}</div><div class="code">{{ code }}</div>
<div class="muted" style="text-align:center">Valid until {{ sh.expires_at[:10] }} · school scans the QR or types the code</div>
<div style="display:flex;gap:8px;justify-content:center;margin-top:14px">
<form method="post" action="{{ url_for('send_to_school', code=code) }}" style="margin:0"><button class="green">Send to school</button></form>
<a class="btn" style="background:#eef2f8;color:#1450a3" href="{{ url_for('download', code=code) }}">Download file</a></div>
{% if msg %}<div class="tile"><span class="chip {{ 'c-ok' if msg.result in ('accepted','already_accepted') else 'c-bad' }}">School: {{ msg.result.replace('_',' ') }}</span> <span class="muted">{{ msg.reason }}</span></div>{% endif %}
<p><a href="{{ url_for('parent', student_id=rec.student_id) }}">← back to wallet</a></p></div></div></div>""",
                    sh=sh, rec=rec, name=name, code=code, qr=qr_svg(link), msg=request.args.get("msg") and json.loads(request.args["msg"]))

    @app.post("/parent/shared/<code>/send")
    def send_to_school(code):
        res = svc.school_receive(share_code=code, school_user="School office (auto)")
        return redirect(url_for("share_view", code=code, msg=json.dumps({"result": res["result"], "reason": res["reason"]})))

    @app.get("/parent/shared/<code>/certificate.json")
    def download(code):
        return Response(json.dumps(shares[code]["package"], indent=2), mimetype="application/json",
                        headers={"Content-Disposition": f"attachment; filename=certificate-{code}.json"})

    # ------------------------------------------------------------------ nurse
    @app.get("/nurse")
    def nurse():
        return page("nurse", """<div class="card"><h3>Nurse / physician console</h3>
<p class="muted">Sees temperatures, the personal baseline and reasons. One click to approve or reject.</p></div>
{% for c in queue %}<div class="card"><div style="display:flex;justify-content:space-between;align-items:center">
<div><b style="font-size:16px">{{c.student_name}}</b> <span class="muted">{{c.cert_id}} · absence {{c.absence_start}} → {{c.absence_end}}</span></div>
<span class="chip {{ chips[c.status][1] }}">{{ chips[c.status][0] }}</span></div>
{% if c.escalated %}<p class="chip c-bad" style="margin-top:8px">Refer to clinician before certifying</p>{% endif %}
<p>{{ c.reasons|join(' · ') }}</p><table><tr><th>Time</th><th>°C</th><th>Baseline</th><th>Deviation</th><th>Decision</th></tr>
{% for r in c.readings %}<tr><td>{{r.ts[5:16].replace('T',' ')}}</td><td><b>{{r.temp_c}}</b></td><td>{{'%.2f'|format(r.baseline_c)}}</td><td>{{'%+.2f'|format(r.deviation_c)}}</td><td>{{r.decision}}</td></tr>{% endfor %}</table><p></p>
<form method="post" action="{{ url_for('decide', cert_id=c.cert_id, action='approve') }}" style="display:inline"><button class="green">Approve</button></form>
<form method="post" action="{{ url_for('decide', cert_id=c.cert_id, action='reject') }}" style="display:inline"><button class="red">Reject</button></form></div>
{% else %}<div class="card muted">No certificates waiting.</div>{% endfor %}""", queue=svc.nurse_queue())

    @app.post("/nurse/<cert_id>/<action>")
    def decide(cert_id, action):
        svc.decide(cert_id, approve=(action == "approve"), validator="School Nurse")
        return redirect(url_for("nurse"))

    # ------------------------------------------------------------------ school
    @app.route("/school", methods=["GET", "POST"])
    def school():
        res = None
        code = request.values.get("code")
        if request.method == "POST":
            if request.files.get("file") and request.files["file"].filename:
                try:
                    pkg = json.load(request.files["file"])
                except ValueError:
                    pkg = None
                res = svc.school_receive(package=pkg)
            elif code:
                res = svc.school_receive(share_code=code)
        return page("school", """<div class="row"><div class="col"><div class="card"><h3>Receive a certificate</h3>
<form method="post" action="{{ url_for('school') }}"><div class="muted">Share code (or scan the parent's QR)</div>
<input name="code" value="{{ code or '' }}" placeholder="ABCD-2345" style="font-family:ui-monospace,monospace;font-size:18px;width:170px"> <button>Verify & accept</button></form>
<p class="muted">or upload the certificate file the parent sent</p>
<form method="post" enctype="multipart/form-data" action="{{ url_for('school') }}"><input type="file" name="file" accept=".json"> <button class="ghost">Verify file</button></form>
{% if res %}<div class="tile" style="margin-top:14px"><span class="chip {{ 'c-ok' if res.result in ('accepted','already_accepted') else 'c-bad' }}">{{ res.result.replace('_',' ')|upper }}</span>
<div class="muted" style="margin-top:6px">{{ res.reason }}</div></div>{% endif %}</div></div>
<div class="col"><div class="card"><h3>Accepted certificates</h3><p class="muted">Minimum necessary information only.</p><table>
<tr><th>Student</th><th>Absence</th><th>Validated by</th><th>Attendance</th></tr>
{% for c in inbox %}<tr><td><b>{{c.student_name}}</b><div class="muted">{{c.cert_id}}</div></td><td>{{c.absence_start}} → {{c.absence_end}}</td><td>{{c.validated_by}}</td>
<td><span class="chip c-ok">Excused · verified</span></td></tr>{% else %}<tr><td colspan="4" class="muted">Nothing received yet.</td></tr>{% endfor %}</table></div></div></div>""",
                    res=res, code=code, inbox=svc.school_inbox())

    # ------------------------------------------------------------------ verify
    @app.get("/verify")
    def verify_form():
        cid = request.args.get("cert_id")
        if cid:
            return redirect(url_for("verify", cert_id=cid.strip()))
        return page("verify_form", """<div class="card"><h3>Verify a certificate</h3><form>Certificate ID
<input name="cert_id" placeholder="VF-..."> <button>Verify</button></form></div>""")

    @app.get("/verify/<cert_id>")
    def verify(cert_id):
        rec = svc.school_record(cert_id)
        valid = svc.verify_certificate(rec) if rec else False
        return page("verify_form", """<div class="card"><h3>Certificate {{cid}}</h3>{% if rec %}
<p><span class="chip {{ 'c-ok' if valid else 'c-bad' }}">{{ 'Signature valid: issued here and unchanged' if valid else 'INVALID: altered or not issued here' }}</span></p>
<table>{% for k,v in rec.items() %}<tr><th>{{k}}</th><td><code>{{v}}</code></td></tr>{% endfor %}</table>
{% else %}<p class="chip c-bad">Not found.</p>{% endif %}</div>""", cid=cert_id, rec=rec, valid=valid)

    # ------------------------------------------------------------------ JSON API
    @app.post("/api/readings")
    def api_readings():
        body = request.get_json(force=True, silent=True) or {}
        res = svc.submit(body.get("signed", {}), claimed_student_id=body.get("student_id"))
        return jsonify(res.to_dict()), (200 if res.verdict.value == "accepted" else 422)

    @app.post("/api/certificates/<cert_id>/share")
    def api_share(cert_id):
        try:
            return jsonify(svc.share(cert_id))
        except ValueError as e:
            return jsonify({"error": str(e)}), 409

    @app.post("/api/school/receive")
    def api_receive():
        body = request.get_json(force=True, silent=True) or {}
        res = svc.school_receive(share_code=body.get("share_code"), package=body.get("package"))
        return jsonify(res), (200 if res["result"] in ("accepted", "already_accepted") else 422)

    @app.get("/api/certificates/<cert_id>")
    def api_cert(cert_id):
        rec = svc.school_record(cert_id)
        if not rec:
            return jsonify({"error": "not found"}), 404
        return jsonify({"certificate": rec, "valid": svc.verify_certificate(rec)})

    @app.get("/api/issuer-key")
    def api_key():
        return jsonify({"alg": "Ed25519", "public_key": svc.issuer_public_key})

    return app


def main():
    ap = argparse.ArgumentParser(description="VerifiedFever demo server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    args = ap.parse_args()
    create_app().run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
