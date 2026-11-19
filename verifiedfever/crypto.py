"""Small cryptographic helpers: canonical JSON, Ed25519 signing, SHA-256 digests.

Ed25519 (RFC 8032) is used because it is fast, has small keys and signatures,
and is available on low-cost microcontrollers, so the same scheme can later
move from the virtual thermometer into real device firmware.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical(obj: Any) -> bytes:
    """Deterministic JSON encoding so that signer and verifier hash the same bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def new_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def public_key_b64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return b64e(raw)


def load_public_key(b64: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(b64d(b64))


def sign(private_key: Ed25519PrivateKey, payload: dict) -> str:
    return b64e(private_key.sign(canonical(payload)))


def verify(public_key_b64_text: str, payload: dict, signature_b64: str) -> bool:
    try:
        load_public_key(public_key_b64_text).verify(b64d(signature_b64), canonical(payload))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
