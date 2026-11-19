"""Demo web app: four screens (parent/device, nurse, school, verify) plus a JSON API.

Run:  python -m verifiedfever.app      then open http://127.0.0.1:5000

DEMO ONLY: the virtual thermometers' private keys are held in this process so
the browser can "press the thermometer button". In a real deployment the key
never leaves the device and the device posts to /api/readings itself.
"""
from __future__ import annotations

import argparse
import copy
import os
import random
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, redirect, render_template_string, request, url_for

from .device import VirtualThermometer
from .rules import Policy, fixed_rule
from .service import FeverCertService

DEMO_STUDENTS = [  # (student_id, name, normal temperature used to seed history)
    ("S-1001", "Aarav (low normal 36.3 C)", 36.3),
    ("S-1002", "Maya (normal 36.6 C)", 36.6),
    ("S-1003", "Liam (normal 36.9 C)", 36.9),
    ("S-1004", "Sofia (high normal 37.1 C)", 37.1),
]


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


LAYOUT = """<!doctype html><html><head><meta charset="utf-8"><title>VerifiedFever POC</title>
<style>
body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f6f7f9;color:#1d2430}
header{background:#123c69;color:#fff;padding:14px 24px}header a{color:#cfe3ff;margin-right:18px;text-decoration:none}
header b{margin-right:28px}main{max-width:1000px;margin:24px auto;padding:0 16px}
.card{background:#fff;border-radius:10px;padding:18px 22px;margin-bottom:18px;box-shadow:0 1px 3px #0001}
table{border-collapse:collapse;width:100%}td,th{padding:7px 9px;border-bottom:1px solid #e6e8ec;text-align:left;font-size:14px}
.ok{color:#11743b;font-weight:600}.bad{color:#b3261e;font-weight:600}.warn{color:#9a5b00;font-weight:600}
button,select,input{font-size:15px;padding:7px 10px;border-radius:6px;border:1px solid #c5cad3}
button{background:#123c69;color:#fff;border:0;cursor:pointer}button.alt{background:#6b7280}button.red{background:#b3261e}
.pill{display:inline-block;padding:2px 9px;border-radius:12px;font-size:12px;background:#eef1f5}
code{font-size:12px;word-break:break-all}.muted{color:#6b7280;font-size:13px}
</style></head><body><header><b>VerifiedFever POC</b>
<a href="{{ url_for('home') }}">Overview</a><a href="{{ url_for('parent') }}">1. Parent / Thermometer</a>
<a href="{{ url_for('nurse') }}">2. Nurse console</a><a href="{{ url_for('school') }}">3. School portal</a>
<a href="{{ url_for('verify_form') }}">4. Verify certificate</a></header><main>{{ body|safe }}</main></body></html>"""


def page(body_tpl: str, **ctx):
    body = render_template_string(body_tpl, **ctx)
    return render_template_string(LAYOUT, body=body)


def create_app(db_path: str = ":memory:") -> Flask:
    app = Flask(__name__)
    svc, devices = build_demo(db_path)
    app.config["svc"], app.config["devices"] = svc, devices
    last_signed: dict[str, dict] = {}
    policy = svc.policy

    @app.get("/")
    def home():
        return page("""<div class="card"><h2>Verified Fever, No Appointment</h2>
<p>A registered thermometer signs each reading. The rule engine compares it with the student's
own baseline and the school's fever policy. If criteria are met, a digital absence certificate is
created and a nurse approves it with one click. The school sees only the absence dates and status.</p>
<h3>Try this 2-minute demo</h3><ol>
<li>Go to <b>Parent / Thermometer</b>, pick <b>Aarav</b> (normal 36.3 C) and take a reading of <b>37.6 C</b>.
A fixed 38.0 C rule would miss it; the personal baseline rule issues a certificate.</li>
<li>Pick <b>Sofia</b> (normal 37.1 C) and take <b>37.6 C</b>: no certificate, because that is only +0.5 C for her.</li>
<li>Take <b>39.8 C</b> for anyone: the certificate is routed to <b>clinical review</b>.</li>
<li>Press <b>Try tampering</b> and <b>Try replay</b>: both are rejected.</li>
<li>Open the <b>Nurse console</b>, approve, then check the <b>School portal</b> and <b>Verify</b> pages.</li></ol>
<p class="muted">Each student already has 14 days of normal readings so the baseline is established.</p></div>""")

    @app.route("/parent", methods=["GET", "POST"])
    def parent():
        result, compare, sid = None, None, request.values.get("student_id", DEMO_STUDENTS[0][0])
        if request.method == "POST":
            dev = devices[sid]
            temp = float(request.form["temp_c"])
            signed = dev.read(temp)
            last_signed[sid] = copy.deepcopy(signed)
            result = svc.submit(signed, claimed_student_id=sid).to_dict()
            compare = fixed_rule(temp, policy.fixed_cutoff_c)
        return _parent_page(sid, result, compare)

    def _parent_page(sid, result, compare, note=None):
        return page("""<div class="card"><h3>Parent app + virtual registered thermometer</h3>
<form method="post" action="{{ url_for('parent') }}">Student
<select name="student_id">{% for s in students %}<option value="{{s.student_id}}" {% if s.student_id==sid %}selected{% endif %}>{{s.student_name}}</option>{% endfor %}</select>
Temperature (C) <input name="temp_c" type="number" step="0.1" min="34" max="43" value="37.6" required>
<button>Take signed reading</button></form><p></p>
<form method="post" action="{{ url_for('tamper') }}" style="display:inline"><input type="hidden" name="student_id" value="{{sid}}">
<button class="red">Try tampering (edit 36.6 to 38.5 after signing)</button></form>
<form method="post" action="{{ url_for('replay') }}" style="display:inline"><input type="hidden" name="student_id" value="{{sid}}">
<button class="alt">Try replay of last reading</button></form></div>
{% if note %}<div class="card">{{ note|safe }}</div>{% endif %}
{% if result %}<div class="card"><h3>Result</h3><table>
<tr><th>Evidence check</th><td class="{{ 'ok' if result.verdict=='accepted' else 'bad' }}">{{ result.verdict }}</td></tr>
{% if result.decision %}<tr><th>Decision</th><td><span class="pill">{{ result.decision }}</span> {{ result.reasons|join('; ') }}</td></tr>
<tr><th>Personal baseline</th><td>{{ '%.2f'|format(result.baseline_c) }} C (deviation {{ '%+.2f'|format(result.deviation_c) }} C)</td></tr>
<tr><th>Fixed 38.0 C rule would</th><td>{{ 'flag' if compare else 'NOT flag' }} this reading</td></tr>{% endif %}
{% if result.certificate_id %}<tr><th>Certificate</th><td><a href="{{ url_for('verify', cert_id=result.certificate_id) }}">{{ result.certificate_id }}</a> sent to nurse for one-click validation</td></tr>{% endif %}
</table></div>{% endif %}
<div class="card"><h3>Recent readings for {{ sid }}</h3><table><tr><th>Time (UTC)</th><th>Temp C</th><th>Check</th><th>Decision</th><th>Baseline</th></tr>
{% for r in history %}<tr><td>{{r.ts}}</td><td>{{r.temp_c}}</td><td>{{r.verdict}}</td><td>{{r.decision or ''}}</td><td>{{r.baseline_c or ''}}</td></tr>{% endfor %}</table></div>""",
                    students=svc.students(), sid=sid, result=result, compare=compare, note=note,
                    history=svc.student_readings(sid, 8))

    @app.post("/parent/tamper")
    def tamper():
        sid = request.form["student_id"]
        signed = devices[sid].read(36.6)
        signed["payload"]["temp_c"] = 38.5  # attacker edits the value after the device signed it
        res = svc.submit(signed, claimed_student_id=sid).to_dict()
        return _parent_page(sid, res, None, note="<b>Tamper test:</b> the reading was signed at 36.6 C, then edited to 38.5 C.")

    @app.post("/parent/replay")
    def replay():
        sid = request.form["student_id"]
        if sid not in last_signed:
            return _parent_page(sid, None, None, note="Take a reading first, then replay it.")
        res = svc.submit(copy.deepcopy(last_signed[sid]), claimed_student_id=sid).to_dict()
        return _parent_page(sid, res, None, note="<b>Replay test:</b> the last genuine reading was submitted a second time.")

    @app.get("/nurse")
    def nurse():
        return page("""<div class="card"><h3>Nurse / physician console</h3>
<p class="muted">Sees temperatures and reasons. Approve or reject with one click.</p></div>
{% for c in queue %}<div class="card"><b>{{c.cert_id}}</b> &middot; {{c.student_name}} &middot; absence {{c.absence_start}} to {{c.absence_end}}
{% if c.escalated %}<p class="bad">Clinical review: refer to clinician before certifying.</p>{% endif %}
<p>{{ c.reasons|join('; ') }}</p><table><tr><th>Time</th><th>Temp C</th><th>Baseline</th><th>Deviation</th><th>Decision</th></tr>
{% for r in c.readings %}<tr><td>{{r.ts}}</td><td>{{r.temp_c}}</td><td>{{r.baseline_c}}</td><td>{{'%+.2f'|format(r.deviation_c)}}</td><td>{{r.decision}}</td></tr>{% endfor %}</table><p></p>
<form method="post" action="{{ url_for('decide', cert_id=c.cert_id, action='approve') }}" style="display:inline"><button>Approve</button></form>
<form method="post" action="{{ url_for('decide', cert_id=c.cert_id, action='reject') }}" style="display:inline"><button class="red">Reject</button></form></div>
{% else %}<div class="card">No certificates waiting.</div>{% endfor %}""", queue=svc.nurse_queue())

    @app.post("/nurse/<cert_id>/<action>")
    def decide(cert_id, action):
        svc.decide(cert_id, approve=(action == "approve"), validator="School Nurse (demo)")
        return redirect(url_for("nurse"))

    @app.get("/school")
    def school():
        return page("""<div class="card"><h3>School portal</h3>
<p class="muted">Minimum necessary information only: no temperatures or health details.</p><table>
<tr><th>Certificate</th><th>Student</th><th>Reason</th><th>Absence</th><th>Status</th><th>Validated by</th></tr>
{% for c in certs %}<tr><td><a href="{{ url_for('verify', cert_id=c.cert_id) }}">{{c.cert_id}}</a></td><td>{{c.student_name}}</td><td>{{c.reason}}</td>
<td>{{c.absence_start}} to {{c.absence_end}}</td><td class="{{ 'ok' if c.status=='approved' else ('bad' if c.status=='rejected' else 'warn') }}">{{c.status}}</td><td>{{c.validated_by or ''}}</td></tr>
{% else %}<tr><td colspan="6">No certificates yet.</td></tr>{% endfor %}</table></div>""", certs=svc.school_view())

    @app.get("/verify")
    def verify_form():
        cid = request.args.get("cert_id")
        if cid:
            return redirect(url_for("verify", cert_id=cid.strip()))
        return page("""<div class="card"><h3>Verify a certificate</h3><form>Certificate ID
<input name="cert_id" placeholder="VF-..."> <button>Verify</button></form></div>""")

    @app.get("/verify/<cert_id>")
    def verify(cert_id):
        rec = svc.school_record(cert_id)
        valid = svc.verify_certificate(rec) if rec else False
        return page("""<div class="card"><h3>Certificate {{cid}}</h3>{% if rec %}
<p class="{{ 'ok' if valid else 'bad' }}">{{ 'Signature valid: issued by this school system and unchanged.' if valid else 'INVALID: record was altered or not issued here.' }}</p>
<table>{% for k,v in rec.items() %}<tr><th>{{k}}</th><td><code>{{v}}</code></td></tr>{% endfor %}</table>
{% else %}<p class="bad">Not found.</p>{% endif %}</div>""", cid=cert_id, rec=rec, valid=valid)

    # ------------------------------------------------------------------ JSON API
    @app.post("/api/readings")
    def api_readings():
        body = request.get_json(force=True, silent=True) or {}
        res = svc.submit(body.get("signed", {}), claimed_student_id=body.get("student_id"))
        return jsonify(res.to_dict()), (200 if res.verdict.value == "accepted" else 422)

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
