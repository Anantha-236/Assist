"""FastAPI dependencies: JWT enforcement."""

from fastapi import Header, HTTPException

from . import auth


async def require_token(authorization: str | None = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization[7:]
    ok, err = auth.validate(token)
    if not ok:
        raise HTTPException(401, err or "invalid token")
    payload = auth.decode_token(token)
    if payload is None:
        raise HTTPException(401, "invalid token payload")
    return payload  # {"sub": key_id, "fp": fingerprint, ...}