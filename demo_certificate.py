"""Step-by-step certificate walkthrough you can run and check yourself.

    python demo_certificate.py

It follows one student, Aarav, whose normal temperature is 36.3 C:
  1. enrol a registered thermometer (parent consent)
  2. record 14 normal mornings, so the system learns Aarav's own baseline
  3. record a 37.6 C morning (below the usual 38.0 C cutoff, but 1.3 C above his normal)
  4. the system creates a signed absence certificate, pending nurse approval
  5. the nurse approves it with one click
  6. the parent shares it with the school; the school verifies the signature and accepts it
  7. three negative checks: an edited certificate, an edited reading and a replayed reading are all refused
It also writes two files you can inspect or edit:
  demo_output/signed_reading.json      what the thermometer sends
  demo_output/certificate_package.json what the school receives
Check the package on its own with:  python verify_certificate_file.py demo_output/certificate_package.json
Every step prints PASS or FAIL; the script exits with an error if any check fails.
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from verifiedfever import FeverCertService, VirtualThermometer
from verifiedfever.rules import personal_baseline

OUT = Path(__file__).resolve().parent / "demo_output"
DAY = datetime(2026, 11, 23, 7, 0, tzinfo=timezone.utc)
results: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append(bool(ok))
    print(f"   [{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))


def step(n: int, text: str) -> None:
    print(f"\nStep {n}. {text}")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    svc = FeverCertService()
    therm = VirtualThermometer.create("THERM-AARAV")

    step(1, "Enrol the thermometer for student S-1001 (Aarav), with parent consent")
    svc.enroll(therm.device_id, "S-1001", "Aarav", therm.public_key, consent=True, now=DAY - timedelta(days=15))
    print(f"   device {therm.device_id}, public key {therm.public_key[:16]}...")
    check("student enrolled", svc.students()[0]["student_id"] == "S-1001")

    step(2, "Record 14 normal mornings (36.2 to 36.4 C) so the system learns Aarav's baseline")
    normals = [36.3, 36.2, 36.4, 36.3, 36.3, 36.2, 36.4, 36.3, 36.3, 36.2, 36.3, 36.4, 36.3, 36.3]
    for i, t in enumerate(normals):
        ts = DAY - timedelta(days=len(normals) - i)
        r = svc.submit(therm.read(t, ts=ts), now=ts)
        assert r.verdict.value == "accepted"
    b = personal_baseline(normals)
    print(f"   baseline = median of the last 14 normal readings = {b.value_c:.1f} C")
    check("baseline learned from Aarav's own readings", abs(b.value_c - 36.3) < 0.05 and not b.is_default)

    step(3, "Record a 37.6 C morning")
    signed = therm.read(37.6, ts=DAY)
    (OUT / "signed_reading.json").write_text(json.dumps(signed, indent=2))
    print(f"   thermometer sends: {json.dumps(signed['payload'])}")
    print(f"   with signature:    {signed['sig'][:32]}...  (saved to demo_output/signed_reading.json)")
    res = svc.submit(copy.deepcopy(signed), now=DAY + timedelta(minutes=2))
    print(f"   verdict = {res.verdict.value}, decision = {res.decision.value}, "
          f"baseline = {res.baseline_c:.1f} C, deviation = {res.deviation_c:+.1f} C")
    print("   rule: fever if T >= 38.0, or (T >= 37.5 and T - baseline >= 1.0)")
    print(f"         37.6 >= 37.5 and 37.6 - {res.baseline_c:.1f} = {res.deviation_c:.1f} >= 1.0  -> fever")
    check("signature and device verified", res.verdict.value == "accepted")
    check("fever recognised even though 37.6 C is below 38.0 C", res.decision.value == "certify")
    check("a fixed 38.0 C rule would have missed it", 37.6 < 38.0)

    step(4, "The system creates a signed absence certificate")
    cert = svc.school_record(res.certificate_id)
    for k in ("cert_id", "student_id", "absence_start", "absence_end", "status", "reason", "evidence_digest"):
        print(f"   {k:15s} {cert[k]}")
    print(f"   {'issuer_sig':15s} {cert['issuer_sig'][:32]}...")
    check("certificate waits for a nurse", cert["status"] == "pending_validation")
    check("no temperature appears in the certificate", "37.6" not in json.dumps(cert) and "temp" not in json.dumps(cert))
    check("issuer signature verifies", svc.verify_certificate(cert))
    check("absence covers the fever day plus 24 h fever-free", cert["absence_start"] == "2026-11-23" and cert["absence_end"] == "2026-11-24")

    step(5, "Nurse reviews the queue and approves with one click")
    q = svc.nurse_queue()[0]
    print(f"   nurse sees: {q['student_name']}, readings {[r['temp_c'] for r in q['readings']]}, reasons {q['reasons']}")
    approved = svc.decide(res.certificate_id, True, "Nurse Patel", now=DAY + timedelta(hours=1))
    check("status is now approved", approved["status"] == "approved")
    check("certificate re-signed after approval and still verifies", svc.verify_certificate(approved))

    step(6, "Parent shares the certificate; the school verifies and accepts it")
    share = svc.share(res.certificate_id, now=DAY + timedelta(hours=2))
    (OUT / "certificate_package.json").write_text(json.dumps(share["package"], indent=2))
    print(f"   share code {share['share_code']} (package saved to demo_output/certificate_package.json)")
    recv = svc.school_receive(share_code=share["share_code"], now=DAY + timedelta(hours=3))
    print(f"   school result: {recv['result']} - {recv['reason']}")
    check("school accepted the shared certificate", recv["result"] == "accepted")

    step(7, "Negative checks: forged or reused evidence must be refused")
    forged = copy.deepcopy(share["package"])
    forged["certificate"]["absence_end"] = "2026-12-31"
    r1 = svc.school_receive(package=forged, now=DAY + timedelta(hours=4))
    check("certificate edited to extend the absence is refused", r1["result"] == "refused", r1["reason"])
    edited = copy.deepcopy(signed)
    edited["payload"]["temp_c"] = 39.0
    edited["payload"]["seq"] += 100
    r2 = svc.submit(edited, now=DAY + timedelta(minutes=5))
    check("reading edited from 37.6 to 39.0 C is refused", r2.verdict.value == "bad_signature", r2.verdict.value)
    r3 = svc.submit(copy.deepcopy(signed), now=DAY + timedelta(minutes=6))
    check("same reading sent a second time is refused", r3.verdict.value != "accepted", r3.verdict.value)

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
