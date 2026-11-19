"""Certification service: ingest signed readings, apply the rule engine, issue
and validate digital absence certificates. Backed by SQLite (one file, no
server), which keeps the proof of concept easy to run and inspect.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from . import crypto
from .rules import FEBRILE, Decision, Policy, evaluate
from .verifier import Enrollment, Verdict, VerifierConfig, parse_ts, verify_reading

SCHEMA = """
CREATE TABLE IF NOT EXISTS enrollments (
  device_id TEXT PRIMARY KEY, student_id TEXT UNIQUE NOT NULL, student_name TEXT NOT NULL,
  public_key TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, consent INTEGER NOT NULL DEFAULT 1,
  enrolled_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS readings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, student_id TEXT, seq INTEGER, ts TEXT,
  temp_c REAL, signed_json TEXT NOT NULL, verdict TEXT NOT NULL, decision TEXT,
  baseline_c REAL, deviation_c REAL, reasons TEXT, received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS certificates (
  cert_id TEXT PRIMARY KEY, student_id TEXT NOT NULL, absence_start TEXT NOT NULL,
  absence_end TEXT NOT NULL, status TEXT NOT NULL, escalated INTEGER NOT NULL DEFAULT 0,
  reasons TEXT NOT NULL, evidence_reading_ids TEXT NOT NULL, evidence_digest TEXT NOT NULL,
  issued_at TEXT NOT NULL, validated_by TEXT, validated_at TEXT, note TEXT, issuer_sig TEXT NOT NULL);
"""

# Certificate status values
PENDING = "pending_validation"
CLINICAL = "clinical_review"      # escalated: repeated or high-grade fever
APPROVED = "approved"
REJECTED = "rejected"
OPEN = (PENDING, CLINICAL)

REASON_TEXT = "Fever-related absence (device-verified reading)"


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SubmitResult:
    verdict: Verdict
    reading_id: int
    decision: Optional[Decision] = None
    baseline_c: Optional[float] = None
    deviation_c: Optional[float] = None
    reasons: Optional[list] = None
    certificate_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "reading_id": self.reading_id,
            "decision": self.decision.value if self.decision else None,
            "baseline_c": self.baseline_c,
            "deviation_c": self.deviation_c,
            "reasons": self.reasons,
            "certificate_id": self.certificate_id,
        }


class FeverCertService:
    def __init__(self, db_path: str = ":memory:", policy: Policy = Policy(),
                 verifier_config: VerifierConfig = VerifierConfig(), issuer_key=None):
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.policy = policy
        self.vconf = verifier_config
        self.issuer_key = issuer_key or crypto.new_private_key()
        self.issuer_public_key = crypto.public_key_b64(self.issuer_key)

    # ---------------------------------------------------------------- enrollment
    def enroll(self, device_id: str, student_id: str, student_name: str, public_key: str,
               consent: bool = True, now: Optional[datetime] = None) -> None:
        if not consent:
            raise ValueError("parental consent is required before enrollment")
        now = now or datetime.now(timezone.utc)
        self.db.execute(
            "INSERT INTO enrollments(device_id, student_id, student_name, public_key, active, consent, enrolled_at)"
            " VALUES (?,?,?,?,1,1,?)", (device_id, student_id, student_name, public_key, _iso(now)))
        self.db.commit()

    def revoke(self, device_id: str) -> None:
        self.db.execute("UPDATE enrollments SET active=0 WHERE device_id=?", (device_id,))
        self.db.commit()

    def _enrollment(self, device_id: str) -> Optional[Enrollment]:
        r = self.db.execute("SELECT * FROM enrollments WHERE device_id=?", (device_id,)).fetchone()
        return Enrollment(r["device_id"], r["student_id"], r["public_key"], bool(r["active"])) if r else None

    def _last_seq(self, device_id: str) -> int:
        r = self.db.execute("SELECT MAX(seq) AS m FROM readings WHERE device_id=? AND verdict=?",
                            (device_id, Verdict.ACCEPTED.value)).fetchone()
        return r["m"] or 0

    def students(self) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT device_id, student_id, student_name, active FROM enrollments ORDER BY student_id")]

    # ---------------------------------------------------------------- readings
    def submit(self, signed: dict, claimed_student_id: Optional[str] = None,
               now: Optional[datetime] = None) -> SubmitResult:
        now = now or datetime.now(timezone.utc)
        verdict, enr = verify_reading(signed, self._enrollment, self._last_seq, now,
                                      claimed_student_id, self.vconf)
        p = signed.get("payload", {}) if isinstance(signed, dict) else {}
        p = p if isinstance(p, dict) else {}
        cur = self.db.execute(
            "INSERT INTO readings(device_id, student_id, seq, ts, temp_c, signed_json, verdict, received_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (p.get("device_id"), enr.student_id if enr else None, p.get("seq"), p.get("ts"),
             p.get("temp_c"), json.dumps(signed, default=str), verdict.value, _iso(now)))
        rid = cur.lastrowid
        if verdict is not Verdict.ACCEPTED:
            self.db.commit()
            return SubmitResult(verdict, rid)

        student = enr.student_id
        ts = parse_ts(p["ts"])
        history = [r["temp_c"] for r in self.db.execute(
            "SELECT temp_c FROM readings WHERE student_id=? AND verdict=? AND id<>? AND ts<? ORDER BY ts",
            (student, Verdict.ACCEPTED.value, rid, p["ts"]))]
        prior_days = self._prior_consecutive_febrile_days(student, ts.date())
        ev = evaluate(p["temp_c"], history, prior_days, self.policy)
        self.db.execute("UPDATE readings SET decision=?, baseline_c=?, deviation_c=?, reasons=? WHERE id=?",
                        (ev.decision.value, ev.baseline.value_c, ev.deviation_c, json.dumps(ev.reasons), rid))
        cert_id = None
        if ev.decision in FEBRILE:
            cert_id = self._issue_or_extend(student, ts.date(), rid, ev, now)
        self.db.commit()
        return SubmitResult(verdict, rid, ev.decision, ev.baseline.value_c, ev.deviation_c, ev.reasons, cert_id)

    def _prior_consecutive_febrile_days(self, student: str, day: date) -> int:
        days = {r["d"] for r in self.db.execute(
            "SELECT DISTINCT substr(ts,1,10) AS d FROM readings WHERE student_id=? AND verdict=? AND decision IN (?,?)",
            (student, Verdict.ACCEPTED.value, Decision.CERTIFY.value, Decision.ESCALATE.value))}
        n, d = 0, day - timedelta(days=1)
        while d.isoformat() in days:
            n += 1
            d -= timedelta(days=1)
        return n

    # ---------------------------------------------------------------- certificates
    def _school_record(self, row: sqlite3.Row | dict) -> dict:
        """The only fields a school sees. No temperatures, no raw health data."""
        return {
            "cert_id": row["cert_id"], "student_id": row["student_id"], "reason": REASON_TEXT,
            "absence_start": row["absence_start"], "absence_end": row["absence_end"],
            "status": row["status"], "validated_by": row["validated_by"],
            "validated_at": row["validated_at"], "evidence_digest": row["evidence_digest"],
            "issued_at": row["issued_at"],
        }

    def _evidence_digest(self, reading_ids: list[int]) -> str:
        rows = self.db.execute(
            f"SELECT signed_json FROM readings WHERE id IN ({','.join('?' * len(reading_ids))}) ORDER BY id",
            reading_ids).fetchall()
        return crypto.sha256_hex(crypto.canonical([json.loads(r["signed_json"]) for r in rows]))

    def _resign(self, cert_id: str) -> None:
        row = self.db.execute("SELECT * FROM certificates WHERE cert_id=?", (cert_id,)).fetchone()
        sig = crypto.sign(self.issuer_key, self._school_record(row))
        self.db.execute("UPDATE certificates SET issuer_sig=? WHERE cert_id=?", (sig, cert_id))

    def _issue_or_extend(self, student: str, day: date, rid: int, ev, now: datetime) -> str:
        # Absence covers the fever day plus the fever-free period before return (24 h -> 1 day).
        end = day + timedelta(days=max(1, self.policy.fever_free_hours_before_return // 24))
        escalated = int(ev.decision is Decision.ESCALATE)
        status = CLINICAL if escalated else PENDING
        open_cert = self.db.execute(
            f"SELECT * FROM certificates WHERE student_id=? AND status IN ({','.join('?' * len(OPEN))})"
            " AND absence_end>=? ORDER BY issued_at DESC LIMIT 1",
            (student, *OPEN, day.isoformat())).fetchone()
        if open_cert:
            ids = json.loads(open_cert["evidence_reading_ids"]) + [rid]
            reasons = json.loads(open_cert["reasons"]) + ev.reasons
            esc = max(escalated, open_cert["escalated"])
            self.db.execute(
                "UPDATE certificates SET absence_end=?, evidence_reading_ids=?, evidence_digest=?, reasons=?,"
                " escalated=?, status=? WHERE cert_id=?",
                (max(open_cert["absence_end"], end.isoformat()), json.dumps(ids), self._evidence_digest(ids),
                 json.dumps(reasons), esc, CLINICAL if esc else PENDING, open_cert["cert_id"]))
            self._resign(open_cert["cert_id"])
            return open_cert["cert_id"]
        cert_id = "VF-" + uuid.uuid4().hex[:10].upper()
        self.db.execute(
            "INSERT INTO certificates(cert_id, student_id, absence_start, absence_end, status, escalated, reasons,"
            " evidence_reading_ids, evidence_digest, issued_at, issuer_sig) VALUES (?,?,?,?,?,?,?,?,?,?,'')",
            (cert_id, student, day.isoformat(), end.isoformat(), status, escalated, json.dumps(ev.reasons),
             json.dumps([rid]), self._evidence_digest([rid]), _iso(now)))
        self._resign(cert_id)
        return cert_id

    def decide(self, cert_id: str, approve: bool, validator: str, note: str = "",
               now: Optional[datetime] = None) -> dict:
        """One-click validation by a school nurse or physician."""
        now = now or datetime.now(timezone.utc)
        row = self.db.execute("SELECT status FROM certificates WHERE cert_id=?", (cert_id,)).fetchone()
        if row is None or row["status"] not in OPEN:
            raise ValueError("certificate not found or already decided")
        self.db.execute("UPDATE certificates SET status=?, validated_by=?, validated_at=?, note=? WHERE cert_id=?",
                        (APPROVED if approve else REJECTED, validator, _iso(now), note, cert_id))
        self._resign(cert_id)
        self.db.commit()
        return self.school_record(cert_id)

    def school_record(self, cert_id: str) -> Optional[dict]:
        row = self.db.execute("SELECT * FROM certificates WHERE cert_id=?", (cert_id,)).fetchone()
        if row is None:
            return None
        rec = self._school_record(row)
        rec["issuer_sig"] = row["issuer_sig"]
        return rec

    def school_view(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT c.*, e.student_name FROM certificates c JOIN enrollments e USING(student_id)"
            " ORDER BY issued_at DESC").fetchall()
        out = []
        for r in rows:
            rec = self._school_record(r)
            rec["student_name"] = r["student_name"]
            out.append(rec)
        return out

    def nurse_queue(self) -> list[dict]:
        rows = self.db.execute(
            f"SELECT c.*, e.student_name FROM certificates c JOIN enrollments e USING(student_id)"
            f" WHERE status IN ({','.join('?' * len(OPEN))}) ORDER BY escalated DESC, issued_at",
            OPEN).fetchall()
        out = []
        for r in rows:
            ids = json.loads(r["evidence_reading_ids"])
            readings = [dict(x) for x in self.db.execute(
                f"SELECT ts, temp_c, baseline_c, deviation_c, decision FROM readings WHERE id IN"
                f" ({','.join('?' * len(ids))}) ORDER BY ts", ids)]
            d = dict(r)
            d["reasons"] = json.loads(r["reasons"])
            d["readings"] = readings
            out.append(d)
        return out

    def student_readings(self, student_id: str, limit: int = 30) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT ts, temp_c, verdict, decision, baseline_c, deviation_c FROM readings WHERE student_id=?"
            " ORDER BY id DESC LIMIT ?", (student_id, limit))]

    def verify_certificate(self, record: dict) -> bool:
        """Anyone holding the issuer public key can check a certificate offline."""
        rec = {k: v for k, v in record.items() if k not in ("issuer_sig", "student_name")}
        return crypto.verify(self.issuer_public_key, rec, record.get("issuer_sig", ""))
