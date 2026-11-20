from datetime import date, datetime, timedelta, timezone

import numpy as np

from proactivehealth import anomaly
from proactivehealth.registry import Person, Registry
from proactivehealth.triage import Triage
from verifiedfever.device import VirtualThermometer

START = date(2026, 1, 5)


def ts(day, hour=7):
    return datetime(START.year, START.month, START.day, hour, tzinfo=timezone.utc) + timedelta(days=day)


def make(n=12, scopes=("monitoring", "cohort", "physician"), band="adult"):
    reg = Registry(START)
    devs = {}
    for i in range(n):
        pid = f"P{i:04d}"
        d = VirtualThermometer.create(f"D{i:04d}")
        reg.enroll(Person(pid, band, {"workplace": "W1", "postal_code": "Z1"}, physician_id="DR1"),
                   d.device_id, d.public_key, scopes)
        devs[pid] = d
    return reg, devs


def feed(reg, devs, day, temps):
    out = []
    for (pid, d), t in zip(devs.items(), temps):
        out.append(reg.submit(d.read(t, ts(day)), ts(day) + timedelta(minutes=5)))
    return out


def test_age_policies():
    assert anomaly.is_fever(37.8, 36.9, "older") and not anomaly.is_fever(37.8, 36.9, "adult")
    assert anomaly.is_fever(37.6, 36.4, "adult") and not anomaly.is_fever(37.6, 36.9, "adult")
    assert anomaly.is_fever(37.3, 36.1, "older")


def test_personal_baseline_flags_low_normal_person():
    reg, devs = make(1)
    for day in range(10):
        feed(reg, devs, day, [36.2])
    r = feed(reg, devs, 10, [37.5])[0]
    assert r["accepted"] and r["fever"] and abs(r["baseline_c"] - 36.2) < 1e-6


def test_tampered_reading_rejected():
    reg, devs = make(1)
    d = devs["P0000"]
    s = d.read(39.0, ts(0))
    s["payload"]["temp_c"] = 36.5
    assert reg.submit(s, ts(0) + timedelta(minutes=1))["verdict"] == "bad_signature"


def test_withdraw_stops_processing_and_erases():
    reg, devs = make(1)
    for day in range(3):
        feed(reg, devs, day, [36.6])
    assert reg.withdraw("P0000") == 3
    r = feed(reg, devs, 3, [36.6])[0]
    assert not r["accepted"]
    assert reg.stats()["readings"] == 0


def test_physician_access_requires_consent_and_is_audited():
    reg, devs = make(2, scopes=("monitoring", "cohort"))
    feed(reg, devs, 0, [36.6, 36.7])
    assert reg.trajectory("P0000", "DR1", "physician") is None
    reg.set_consent("P0000", "physician", True)
    assert len(reg.trajectory("P0000", "DR1", "physician")) == 1
    assert reg.trajectory("P0000", "DR2", "physician") is None
    assert reg.audit.verify() and sum(not e["allowed"] for e in reg.audit.entries) == 2


def test_small_cells_suppressed():
    reg, devs = make(4)
    feed(reg, devs, 0, [36.6] * 4)
    v = reg.public_health_view("workplace", 0)
    assert v[0]["suppressed"] and v[0]["fevers"] is None


def test_cohort_alert_and_counts_only_message():
    reg, devs = make(30)
    rng = np.random.default_rng(1)
    for day in range(20):
        feed(reg, devs, day, list(np.round(36.6 + rng.normal(0, 0.15, 30), 1)))
    temps = [38.3] * 6 + list(np.round(36.6 + rng.normal(0, 0.15, 24), 1))
    feed(reg, devs, 20, temps)
    alerts = reg.daily_surveillance(20)
    assert any(a["group"] == "W1" and a["rule"] == "count" for a in alerts)
    tri = Triage(reg)
    drafts = tri.on_day(20, alerts)
    assert drafts and not tri.confirm_alert("cohort_agent", drafts[0])  # agent cannot confirm
    assert tri.confirm_alert("human", drafts[0])
    assert "P00" not in tri.alerts_sent[0]["text"]


def test_guard_blocks_leaks_and_agent_decisions():
    reg, devs = make(6)
    tri = Triage(reg)
    g = tri.guard
    assert not g.outbound("x", "public_health", {"text": "P0001 has 38.6 C", "groups": []})
    assert not g.outbound("x", "public_health", {"text": "cluster", "groups": [{"group": "W1", "reporters": 3}]})
    assert not g.outbound("x", "employer", {"text": "anything"})
    assert not tri.decide("triage_agent", 1, "follow_up")
    assert tri.audit.verify()


def test_triage_priority_and_self_care():
    reg, devs = make(2, scopes=("monitoring", "cohort"))
    reg.set_consent("P0000", "physician", True)
    for day in range(6):
        feed(reg, devs, day, [36.6, 36.6])
    tri = Triage(reg)
    res = feed(reg, devs, 6, [39.8, 38.4])
    tri.on_reading(res[0])
    tri.on_reading(res[1])  # no physician consent -> self-care notice only
    assert [q.priority for q in tri.pending()] == ["urgent"] and tri.counts["self_care"] == 1
