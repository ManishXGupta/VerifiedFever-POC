"""Evidence checks applied to every incoming reading before it is used.

A reading is accepted only if all checks pass:
  1. well-formed payload
  2. device is enrolled and active
  3. if the submitter claims a student, it matches the enrolled student
  4. Ed25519 signature is valid for the enrolled public key
  5. sequence number is strictly greater than the last accepted one (anti-replay)
  6. timestamp is fresh: not in the future, not older than the freshness window
  7. temperature is physiologically plausible
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Optional

from . import crypto


class Verdict(str, Enum):
    ACCEPTED = "accepted"
    MALFORMED = "malformed"
    UNKNOWN_DEVICE = "unknown_device"
    REVOKED_DEVICE = "revoked_device"
    STUDENT_MISMATCH = "student_mismatch"
    BAD_SIGNATURE = "bad_signature"
    REPLAY = "replay_or_out_of_order"
    STALE = "stale_timestamp"
    FUTURE = "future_timestamp"
    IMPLAUSIBLE = "implausible_value"


@dataclass(frozen=True)
class Enrollment:
    device_id: str
    student_id: str
    public_key: str
    active: bool = True


@dataclass(frozen=True)
class VerifierConfig:
    max_age: timedelta = timedelta(hours=6)
    max_clock_skew: timedelta = timedelta(minutes=5)
    min_plausible_c: float = 34.0
    max_plausible_c: float = 43.0


REQUIRED = {"v": int, "device_id": str, "seq": int, "ts": str, "temp_c": (int, float), "site": str, "nonce": str}


def parse_ts(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def verify_reading(
    signed: dict,
    lookup_enrollment: Callable[[str], Optional[Enrollment]],
    last_seq: Callable[[str], int],
    now: datetime,
    claimed_student_id: Optional[str] = None,
    config: VerifierConfig = VerifierConfig(),
) -> tuple[Verdict, Optional[Enrollment]]:
    payload = signed.get("payload") if isinstance(signed, dict) else None
    sig = signed.get("sig") if isinstance(signed, dict) else None
    if not isinstance(payload, dict) or not isinstance(sig, str):
        return Verdict.MALFORMED, None
    for key, typ in REQUIRED.items():
        if key not in payload or not isinstance(payload[key], typ) or isinstance(payload[key], bool):
            return Verdict.MALFORMED, None
    try:
        ts = parse_ts(payload["ts"])
    except ValueError:
        return Verdict.MALFORMED, None

    enr = lookup_enrollment(payload["device_id"])
    if enr is None:
        return Verdict.UNKNOWN_DEVICE, None
    if not enr.active:
        return Verdict.REVOKED_DEVICE, enr
    if claimed_student_id is not None and claimed_student_id != enr.student_id:
        return Verdict.STUDENT_MISMATCH, enr
    if not crypto.verify(enr.public_key, payload, sig):
        return Verdict.BAD_SIGNATURE, enr
    if payload["seq"] <= last_seq(enr.device_id):
        return Verdict.REPLAY, enr
    if ts > now + config.max_clock_skew:
        return Verdict.FUTURE, enr
    if now - ts > config.max_age:
        return Verdict.STALE, enr
    if not (config.min_plausible_c <= payload["temp_c"] <= config.max_plausible_c):
        return Verdict.IMPLAUSIBLE, enr
    return Verdict.ACCEPTED, enr
