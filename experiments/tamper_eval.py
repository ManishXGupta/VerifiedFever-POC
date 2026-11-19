"""Tamper-evidence evaluation and timing.

Enrolls 50 virtual thermometers, submits genuine readings (must all be accepted)
and scripted attacks (must all be rejected), and times signing, verification and
end-to-end processing (reading -> decision -> certificate).

Usage:  python experiments/tamper_eval.py
Output: experiments/results/tamper_results.json
"""
from __future__ import annotations

import copy
import json
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verifiedfever import FeverCertService, VirtualThermometer, Verdict  # noqa: E402
from verifiedfever import crypto  # noqa: E402

OUT = ROOT / "experiments" / "results"
N_DEVICES, TRIALS = 50, 200
T0 = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)


def build(rng):
    svc = FeverCertService()
    devs = []
    for k in range(N_DEVICES):
        d = VirtualThermometer.create(f"THERM-{k:03d}")
        svc.enroll(d.device_id, f"S-{k:03d}", f"Student {k}", d.public_key)
        devs.append(d)
    return svc, devs


def main():
    rng = random.Random(2026)
    svc, devs = build(rng)
    clock = [T0]

    def tick():
        clock[0] += timedelta(minutes=1)
        return clock[0]

    def fresh(dev, temp=None):
        now = tick()
        return dev.read(temp if temp is not None else round(rng.uniform(36.0, 37.2), 1), ts=now), now

    # genuine traffic
    genuine_ok = 0
    for _ in range(1000):
        d = rng.choice(devs)
        s, now = fresh(d)
        genuine_ok += svc.submit(s, claimed_student_id=f"S-{devs.index(d):03d}", now=now).verdict is Verdict.ACCEPTED

    attacks = {}

    def run(name, make, expected):
        detected, verdicts = 0, {}
        for _ in range(TRIALS):
            signed, now, claim = make()
            v = svc.submit(signed, claimed_student_id=claim, now=now).verdict
            verdicts[v.value] = verdicts.get(v.value, 0) + 1
            detected += v is not Verdict.ACCEPTED
        attacks[name] = {"trials": TRIALS, "detected": detected, "rate": detected / TRIALS,
                         "verdicts": verdicts, "expected_check": expected}

    def value_edit():
        d = rng.choice(devs); s, now = fresh(d, 36.6)
        s["payload"]["temp_c"] = round(rng.uniform(38.0, 39.5), 1)
        return s, now, None

    def ts_backdate():
        d = rng.choice(devs); s, now = fresh(d, 38.4)
        s["payload"]["ts"] = (now - timedelta(days=rng.randint(1, 5))).strftime("%Y-%m-%dT%H:%M:%SZ")
        return s, now, None

    def replay():
        d = rng.choice(devs); s, now = fresh(d)
        svc.submit(copy.deepcopy(s), now=now)  # genuine first use
        return copy.deepcopy(s), tick(), None

    def impersonate():
        d = rng.choice(devs)
        rogue = VirtualThermometer(d.device_id, crypto.new_private_key(), seq=d.seq + 1000)
        now = tick()
        return rogue.read(38.6, ts=now), now, None

    def substitute():
        a, b = rng.sample(range(N_DEVICES), 2)
        s, now = fresh(devs[b], 38.6)
        return s, now, f"S-{a:03d}"

    def stale():
        d = rng.choice(devs); now = tick()
        return d.read(38.6, ts=now - timedelta(hours=rng.uniform(6.5, 48))), now, None

    def unknown():
        rogue = VirtualThermometer.create(f"ROGUE-{rng.randint(0, 10**6)}"); now = tick()
        return rogue.read(38.6, ts=now), now, None

    run("Value edited after signing", value_edit, "signature")
    run("Timestamp back-dated after signing", ts_backdate, "signature")
    run("Replay of an accepted reading", replay, "sequence")
    run("Impersonation with a non-enrolled key", impersonate, "signature")
    run("Another student's device substituted", substitute, "enrollment binding")
    run("Delayed (hoarded) genuine reading", stale, "freshness")
    run("Unregistered device", unknown, "enrollment")

    # certificate alteration
    cert_detect = 0
    ids = []
    for k in range(TRIALS):
        d = devs[k % N_DEVICES]
        s, now = fresh(d, 38.4)
        res = svc.submit(s, now=now)
        ids.append(res.certificate_id)
    for cid in ids:
        rec = svc.school_record(cid)
        field = rng.choice(["absence_end", "absence_start", "status", "student_id"])
        rec[field] = {"absence_end": "2027-01-31", "absence_start": "2026-10-01",
                      "status": "approved" if rec["status"] != "approved" else "rejected",
                      "student_id": "S-999"}[field]
        cert_detect += not svc.verify_certificate(rec)
    attacks["Certificate field altered (dates, status, student)"] = {
        "trials": len(ids), "detected": cert_detect, "rate": cert_detect / len(ids), "expected_check": "issuer signature"}

    # timing
    dev = VirtualThermometer.create("TIMING")
    payload_signs, verifies = [], []
    for _ in range(2000):
        t = time.perf_counter(); s = dev.read(36.7); payload_signs.append(time.perf_counter() - t)
        t = time.perf_counter(); crypto.verify(dev.public_key, s["payload"], s["sig"]); verifies.append(time.perf_counter() - t)
    svc2, devs2 = build(rng)
    e2e = []
    base = datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc)
    for k, d in enumerate(devs2):
        for day in range(14):
            ts = base + timedelta(days=day)
            svc2.submit(d.read(36.6, ts=ts), now=ts)
        ts = base + timedelta(days=14)
        s = d.read(38.3, ts=ts)
        t = time.perf_counter(); r = svc2.submit(s, now=ts); e2e.append(time.perf_counter() - t)
        assert r.certificate_id
    sizes = len(json.dumps(dev.read(36.7)).encode())

    def ms(x):
        return {"median_ms": round(statistics.median(x) * 1000, 3), "p95_ms": round(sorted(x)[int(0.95 * len(x))] * 1000, 3)}

    result = {
        "genuine": {"submitted": 1000, "accepted": genuine_ok, "false_rejection_rate": 1 - genuine_ok / 1000},
        "attacks": attacks,
        "timing": {"sign_reading": ms(payload_signs), "verify_signature": ms(verifies),
                   "end_to_end_reading_to_certificate": ms(e2e), "signed_reading_bytes": sizes,
                   "platform": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}"},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tamper_results.json").write_text(json.dumps(result, indent=2))
    print(f"genuine accepted: {genuine_ok}/1000")
    for k, v in attacks.items():
        print(f"{k:55s} {v['detected']}/{v['trials']}  {v.get('verdicts', '')}")
    print(json.dumps(result["timing"], indent=1))


if __name__ == "__main__":
    main()
