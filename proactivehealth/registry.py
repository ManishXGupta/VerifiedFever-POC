"""Consent-based registry of verified daily temperature readings.

Privacy by design:
  * the thermometer payload carries no personal data; the registry binds device -> pseudonymous person ID
  * three separately revocable consent scopes:
        monitoring   readings are stored and checked against the person's own baseline
        cohort       the person's flags may be counted in group statistics (class, workplace, postal code)
        physician    a named physician may view the person's trajectory
  * withdrawing consent stops processing and erases the person's readings
  * group views for public health are counts only, and cells with fewer than K_MIN reporters are suppressed
  * every access to an individual trajectory is written to a hash-chained audit log
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

import numpy as np

from verifiedfever.agents import AuditLog
from verifiedfever.verifier import Enrollment, Verdict, parse_ts, verify_reading

from . import anomaly

SCOPES = ("monitoring", "cohort", "physician")
GROUP_TYPES = ("class", "workplace", "postal_code")
K_MIN = 5


@dataclass
class Person:
    person_id: str
    age_band: str
    groups: dict          # group_type -> group_id
    physician_id: Optional[str] = None


class Registry:
    def __init__(self, start: date, path: str = ":memory:"):
        self.start = start
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS persons(person_id TEXT PRIMARY KEY, age_band TEXT, physician_id TEXT);
            CREATE TABLE IF NOT EXISTS memberships(person_id TEXT, group_type TEXT, group_id TEXT);
            CREATE TABLE IF NOT EXISTS consents(person_id TEXT, scope TEXT, granted INTEGER, ts TEXT,
                                                PRIMARY KEY(person_id, scope));
            CREATE TABLE IF NOT EXISTS devices(device_id TEXT PRIMARY KEY, person_id TEXT, public_key TEXT,
                                               active INTEGER, last_seq INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS readings(person_id TEXT, day INTEGER, temp_c REAL, baseline_c REAL,
                                                deviation_c REAL, fever INTEGER, PRIMARY KEY(person_id, day));
            CREATE INDEX IF NOT EXISTS ix_mem ON memberships(group_type, group_id);
            CREATE INDEX IF NOT EXISTS ix_read_day ON readings(day);
        """)
        self.audit = AuditLog()

    # ---------------- enrollment and consent
    def enroll(self, person: Person, device_id: str, public_key: str, scopes=SCOPES) -> None:
        self.db.execute("INSERT INTO persons VALUES(?,?,?)", (person.person_id, person.age_band, person.physician_id))
        for gt, gid in person.groups.items():
            if gt not in GROUP_TYPES:
                raise ValueError(f"unknown group type {gt}")
            self.db.execute("INSERT INTO memberships VALUES(?,?,?)", (person.person_id, gt, gid))
        self.db.execute("INSERT INTO devices VALUES(?,?,?,1,0)", (device_id, person.person_id, public_key))
        for s in SCOPES:
            self.set_consent(person.person_id, s, s in scopes)
        self.db.commit()

    def set_consent(self, person_id: str, scope: str, granted: bool) -> None:
        if scope not in SCOPES:
            raise ValueError(scope)
        self.db.execute("INSERT OR REPLACE INTO consents VALUES(?,?,?,?)",
                        (person_id, scope, int(granted), datetime.now(timezone.utc).isoformat()))
        self.audit.add("person", f"consent_{scope}", True, {"person": person_id, "granted": granted})
        self.db.commit()

    def has_consent(self, person_id: str, scope: str) -> bool:
        r = self.db.execute("SELECT granted FROM consents WHERE person_id=? AND scope=?", (person_id, scope)).fetchone()
        return bool(r and r[0])

    def withdraw(self, person_id: str) -> int:
        """Withdraw all consent and erase stored readings. Returns the number of readings erased."""
        for s in SCOPES:
            self.set_consent(person_id, s, False)
        n = self.db.execute("DELETE FROM readings WHERE person_id=?", (person_id,)).rowcount
        self.db.execute("UPDATE devices SET active=0 WHERE person_id=?", (person_id,))
        self.audit.add("person", "withdraw_and_erase", True, {"person": person_id, "erased": n})
        self.db.commit()
        return n

    # ---------------- readings
    def _enrollment(self, device_id: str):
        r = self.db.execute("SELECT device_id, person_id, public_key, active FROM devices WHERE device_id=?",
                            (device_id,)).fetchone()
        return Enrollment(r[0], r[1], r[2], bool(r[3])) if r else None

    def _last_seq(self, device_id: str) -> int:
        r = self.db.execute("SELECT last_seq FROM devices WHERE device_id=?", (device_id,)).fetchone()
        return r[0] if r else 0

    def submit(self, signed: dict, now: datetime) -> dict:
        verdict, enr = verify_reading(signed, self._enrollment, self._last_seq, now)
        if verdict != Verdict.ACCEPTED:
            return {"accepted": False, "verdict": verdict.value}
        pid = enr.student_id
        if not self.has_consent(pid, "monitoring"):
            return {"accepted": False, "verdict": "no_consent"}
        p = signed["payload"]
        self.db.execute("UPDATE devices SET last_seq=? WHERE device_id=?", (p["seq"], p["device_id"]))
        day = (parse_ts(p["ts"]).date() - self.start).days
        band = self.db.execute("SELECT age_band FROM persons WHERE person_id=?", (pid,)).fetchone()[0]
        hist = [t for (t,) in self.db.execute(
            "SELECT temp_c FROM readings WHERE person_id=? AND day<? ORDER BY day", (pid, day))]
        b = anomaly.baseline(hist, band)
        temp = float(p["temp_c"])
        fever = anomaly.is_fever(temp, b, band)
        self.db.execute("INSERT OR REPLACE INTO readings VALUES(?,?,?,?,?,?)",
                        (pid, day, temp, round(b, 3), round(temp - b, 3), int(fever)))
        self.db.commit()
        streak = self._streak(pid, day)
        return {"accepted": True, "verdict": "accepted", "person_id": pid, "day": day, "fever": fever,
                "baseline_c": round(b, 2), "deviation_c": round(temp - b, 2), "age_band": band,
                "fever_days_in_row": streak, "temp_c": temp}

    def _streak(self, pid: str, day: int) -> int:
        n, d = 0, day
        while True:
            r = self.db.execute("SELECT fever FROM readings WHERE person_id=? AND day=?", (pid, d)).fetchone()
            if not r or not r[0]:
                return n
            n, d = n + 1, d - 1

    # ---------------- views
    def trajectory(self, person_id: str, requester: str, role: str) -> Optional[list[dict]]:
        """Individual readings. Allowed for the person, or for their named physician with consent."""
        phys = self.db.execute("SELECT physician_id FROM persons WHERE person_id=?", (person_id,)).fetchone()
        ok = (role == "person" and requester == person_id) or (
            role == "physician" and phys and phys[0] == requester and self.has_consent(person_id, "physician"))
        self.audit.add(requester, "view_trajectory", bool(ok), {"person": person_id, "role": role},
                       "" if ok else "no consent or not the named physician")
        if not ok:
            return None
        rows = self.db.execute("SELECT day, temp_c, baseline_c, deviation_c, fever FROM readings "
                               "WHERE person_id=? ORDER BY day", (person_id,)).fetchall()
        return [dict(zip(("day", "temp_c", "baseline_c", "deviation_c", "fever"), r)) for r in rows]

    def group_matrix(self, group_type: str, n_days: int):
        """(group ids, reporters, fevers, deviation sums), each (G, n_days); cohort consent only."""
        rows = self.db.execute("""
            SELECT m.group_id, r.day, COUNT(*), SUM(r.fever), SUM(r.deviation_c)
            FROM readings r JOIN memberships m ON m.person_id=r.person_id AND m.group_type=?
            JOIN consents c ON c.person_id=r.person_id AND c.scope='cohort' AND c.granted=1
            WHERE r.day < ? GROUP BY m.group_id, r.day""", (group_type, n_days)).fetchall()
        gids = sorted({r[0] for r in rows} | {g for (g,) in self.db.execute(
            "SELECT DISTINCT group_id FROM memberships WHERE group_type=?", (group_type,))})
        ix = {g: i for i, g in enumerate(gids)}
        rep, fev, dev = (np.zeros((len(gids), n_days)) for _ in range(3))
        for g, d, n, f, s in rows:
            if 0 <= d < n_days:
                rep[ix[g], d], fev[ix[g], d], dev[ix[g], d] = n, f or 0, s or 0.0
        return gids, rep, fev, dev

    def public_health_view(self, group_type: str, day: int) -> list[dict]:
        """Counts per group for one day; small cells suppressed."""
        gids, rep, fev, dev = self.group_matrix(group_type, day + 1)
        out = []
        for i, g in enumerate(gids):
            n = int(rep[i, day])
            if n < K_MIN:
                out.append({"group": g, "reporters": None, "fevers": None, "suppressed": True})
            else:
                out.append({"group": g, "reporters": n, "fevers": int(fev[i, day]),
                            "mean_deviation_c": round(dev[i, day] / n, 2), "suppressed": False})
        return out

    def daily_surveillance(self, day: int, alpha: float = 0.01, z_thr: float = 4.0) -> list[dict]:
        """Cohort alerts for one day across all group types (counts and drift)."""
        alerts = []
        for gt in GROUP_TYPES:
            gids, rep, fev, dev = self.group_matrix(gt, day + 1)
            if not gids or day < 14:
                continue
            for g, p in anomaly.group_count_alerts(fev, rep, day, alpha):
                alerts.append({"group_type": gt, "group": gids[g], "rule": "count", "fevers": int(fev[g, day]),
                               "reporters": int(rep[g, day]), "p": p})
            z = anomaly.group_drift_z(dev, rep, day)
            for g in np.where(np.nan_to_num(z, nan=-1) > z_thr)[0]:
                alerts.append({"group_type": gt, "group": gids[g], "rule": "drift", "z": round(float(z[g]), 2),
                               "reporters": int(rep[g, day])})
        return alerts

    def stats(self) -> dict:
        q = lambda s: self.db.execute(s).fetchone()[0]  # noqa: E731
        return {"persons": q("SELECT COUNT(*) FROM persons"), "readings": q("SELECT COUNT(*) FROM readings"),
                "fevers": q("SELECT COALESCE(SUM(fever),0) FROM readings")}


def by_group(rows, key):
    out = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out
