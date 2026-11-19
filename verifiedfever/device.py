"""Virtual registered thermometer.

In the proof of concept the thermometer is simulated in software: it holds an
Ed25519 private key and signs every reading. In a real deployment the same
logic runs in device firmware and the key lives in a secure element, so it
never leaves the device (see docs/ROADMAP.md).

The device knows nothing about the student. The binding device -> student is
held only by the school-side enrollment registry, which keeps the device
payload free of personal data.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import crypto

PAYLOAD_VERSION = 1


def utc_iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class VirtualThermometer:
    device_id: str
    private_key: object = field(repr=False)
    seq: int = 0

    @classmethod
    def create(cls, device_id: str) -> "VirtualThermometer":
        return cls(device_id=device_id, private_key=crypto.new_private_key())

    @property
    def public_key(self) -> str:
        return crypto.public_key_b64(self.private_key)

    def read(self, temp_c: float, ts: datetime | None = None, site: str = "oral") -> dict:
        """Return a signed reading: {"payload": {...}, "sig": "..."}."""
        self.seq += 1
        ts = ts or datetime.now(timezone.utc)
        payload = {
            "v": PAYLOAD_VERSION,
            "device_id": self.device_id,
            "seq": self.seq,
            "ts": utc_iso(ts),
            "temp_c": round(float(temp_c), 2),
            "site": site,
            "nonce": secrets.token_hex(8),
        }
        return {"payload": payload, "sig": crypto.sign(self.private_key, payload)}
