"""Key generation, JWT issuance, and validation."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from . import db
from .config import JWT_EXPIRE_DAYS, JWT_SECRET


def generate_key() -> tuple[str, str]:
    key_id = uuid.uuid4().hex[:12]
    raw = secrets.token_hex(10).upper()
    formatted = f"ASSIST-{raw[0:5]}-{raw[5:10]}-{raw[10:15]}-{raw[15:20]}"
    return key_id, formatted


def create_token(key_id: str, fingerprint: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": key_id,
        "fp": fingerprint,
        "iat": now,
        "exp": now + timedelta(days=JWT_EXPIRE_DAYS),
        "iss": "assist",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer="assist")
    except jwt.PyJWTError:
        return None


def activate(key_value: str, fingerprint: str) -> tuple[str | None, str | None]:
    row = db.get_key_by_value(key_value.strip().upper())
    if row is None:
        return None, "invalid activation key"
    if row["revoked"]:
        return None, "activation key has been revoked"
    if row["device_fingerprint"] and row["device_fingerprint"] != fingerprint:
        return None, "activation key already bound to another device"
    if not row["device_fingerprint"]:
        db.bind_key(row["key_id"], fingerprint)
    return create_token(row["key_id"], fingerprint), None


def validate(token: str) -> tuple[bool, str | None]:
    payload = decode_token(token)
    if payload is None:
        return False, "invalid or expired token"
    row = db.get_key_by_id(payload["sub"])
    if row is None:
        return False, "key not found"
    if row["revoked"]:
        return False, "key revoked"
    if row["device_fingerprint"] and row["device_fingerprint"] != payload["fp"]:
        return False, "device mismatch"
    return True, None