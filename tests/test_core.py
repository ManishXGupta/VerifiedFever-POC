import copy
from datetime import datetime, timedelta, timezone

import pytest

from verifiedfever import Decision, FeverCertService, Policy, VirtualThermometer, Verdict, evaluate
from verifiedfever.app import create_app
from verifiedfever.rules import personal_baseline

NOW = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)


def setup(normal=36.3, days=14):
    svc = FeverCertService()
    dev = VirtualThermometer.create("THERM-1")
    svc.enroll(dev.device_id, "S-1", "Test Student", dev.public_key)
    for d in range(days, 0, -1):
        ts = NOW - timedelta(days=d)
        assert svc.submit(dev.read(normal, ts=ts), now=ts).verdict is Verdict.ACCEPTED
    return svc, dev


# ------------------------------------------------------------------ rule engine
def test_baseline_uses_default_until_enough_readings():
    b = personal_baseline([36.2, 36.3])
    assert b.is_default and b.value_c == Policy().default_baseline_c


def test_baseline_excludes_febrile_readings():
    b = personal_baseline([36.3] * 6 + [38.9, 39.1])
    assert not b.is_default and b.value_c == 36.3


def test_low_baseline_student_certified_below_fixed_cutoff():
    ev = evaluate(37.6, [36.3] * 14)
    assert ev.decision is Decision.CERTIFY


def test_high_baseline_student_not_certified_at_same_reading():
    ev = evaluate(37.6, [37.1] * 14)
    assert ev.decision in (Decision.NORMAL, Decision.WATCH)


def test_fixed_policy_cutoff_always_honoured():
    assert evaluate(38.0, [37.4] * 14).decision is Decision.CERTIFY


def test_high_grade_escalates():
    assert evaluate(39.6, [36.6] * 14).decision is Decision.ESCALATE


def test_repeated_fever_escalates():
    assert evaluate(38.2, [36.6] * 14, prior_consecutive_febrile_days=2).decision is Decision.ESCALATE


# ------------------------------------------------------------------ evidence checks
def test_genuine_reading_accepted():
    svc, dev = setup()
    assert svc.submit(dev.read(36.4, ts=NOW), now=NOW).verdict is Verdict.ACCEPTED


def test_value_tampering_rejected():
    svc, dev = setup()
    s = dev.read(36.6, ts=NOW)
    s["payload"]["temp_c"] = 38.5
    assert svc.submit(s, now=NOW).verdict is Verdict.BAD_SIGNATURE


def test_replay_rejected():
    svc, dev = setup()
    s = dev.read(36.6, ts=NOW)
    assert svc.submit(copy.deepcopy(s), now=NOW).verdict is Verdict.ACCEPTED
    assert svc.submit(copy.deepcopy(s), now=NOW).verdict is Verdict.REPLAY


def test_impersonation_with_unenrolled_key_rejected():
    svc, dev = setup()
    rogue = VirtualThermometer("THERM-1", VirtualThermometer.create("x").private_key, seq=100)
    assert svc.submit(rogue.read(38.6, ts=NOW), now=NOW).verdict is Verdict.BAD_SIGNATURE


def test_cross_student_substitution_rejected():
    svc, dev = setup()
    other = VirtualThermometer.create("THERM-2")
    svc.enroll(other.device_id, "S-2", "Other", other.public_key)
    assert svc.submit(other.read(38.6, ts=NOW), claimed_student_id="S-1", now=NOW).verdict is Verdict.STUDENT_MISMATCH


def test_stale_and_future_rejected():
    svc, dev = setup()
    assert svc.submit(dev.read(38.6, ts=NOW - timedelta(hours=7)), now=NOW).verdict is Verdict.STALE
    assert svc.submit(dev.read(38.6, ts=NOW + timedelta(hours=1)), now=NOW).verdict is Verdict.FUTURE


def test_revoked_device_rejected():
    svc, dev = setup()
    svc.revoke(dev.device_id)
    assert svc.submit(dev.read(38.6, ts=NOW), now=NOW).verdict is Verdict.REVOKED_DEVICE


# ------------------------------------------------------------------ certificates
def test_certificate_flow_and_minimal_school_view():
    svc, dev = setup()
    res = svc.submit(dev.read(37.7, ts=NOW), now=NOW)
    assert res.decision is Decision.CERTIFY and res.certificate_id
    rec = svc.school_record(res.certificate_id)
    assert rec["status"] == "pending_validation"
    assert "temp" not in " ".join(rec.keys())
    assert svc.verify_certificate(rec)
    approved = svc.decide(res.certificate_id, True, "Nurse A", now=NOW)
    assert approved["status"] == "approved" and svc.verify_certificate(approved)
    view = svc.school_view()[0]
    assert set(view) >= {"absence_start", "absence_end", "status"} and "temp_c" not in view


def test_consecutive_days_extend_then_escalate():
    svc, dev = setup()
    ids = set()
    for d in range(3):
        ts = NOW + timedelta(days=d)
        ids.add(svc.submit(dev.read(38.3, ts=ts), now=ts).certificate_id)
    assert len(ids) == 1
    rec = svc.school_record(ids.pop())
    assert rec["status"] == "clinical_review"
    assert rec["absence_end"] == (NOW + timedelta(days=3)).date().isoformat()


def test_altered_certificate_fails_verification():
    svc, dev = setup()
    cid = svc.submit(dev.read(38.4, ts=NOW), now=NOW).certificate_id
    rec = svc.school_record(cid)
    rec["absence_end"] = "2026-12-31"
    assert not svc.verify_certificate(rec)


def test_enrollment_requires_consent():
    svc = FeverCertService()
    with pytest.raises(ValueError):
        svc.enroll("D", "S", "N", VirtualThermometer.create("D").public_key, consent=False)


# ------------------------------------------------------------------ web demo smoke test
def test_web_demo_end_to_end():
    app = create_app()
    c = app.test_client()
    assert c.get("/").status_code == 200
    r = c.post("/parent", data={"student_id": "S-1001", "temp_c": "37.6"})
    assert b"certify" in r.data and b"NOT flag" in r.data
    assert b"bad_signature" in c.post("/parent/tamper", data={"student_id": "S-1001"}).data
    assert b"replay" in c.post("/parent/replay", data={"student_id": "S-1001"}).data
    svc = app.config["svc"]
    cid = svc.nurse_queue()[0]["cert_id"]
    assert c.post(f"/nurse/{cid}/approve").status_code == 302
    assert b"approved" in c.get("/school").data
    assert b"Signature valid" in c.get(f"/verify/{cid}").data
    assert c.get(f"/api/certificates/{cid}").get_json()["valid"] is True
