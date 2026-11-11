from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .. import auth, db
from ..config import ADMIN_PASSWORD

router = APIRouter(prefix="/api/admin", tags=["admin"])

def _check(password: str | None):
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="admin password required")


class CreateKeyRequest(BaseModel):
    label: str | None = None


class CreateKeyResponse(BaseModel):
    key: str
    key_id: str


class SetProfileRequest(BaseModel):
    profile: dict


@router.post("/keys", response_model=CreateKeyResponse)
def create_key(req: CreateKeyRequest, x_admin_password: str | None = Header(None)):
    _check(x_admin_password)
    key_id, key_value = auth.generate_key()
    db.insert_key(key_id, key_value, label=req.label)
    return {"key": key_value, "key_id": key_id}


@router.get("/keys")
def list_keys(x_admin_password: str | None = Header(None)):
    _check(x_admin_password)
    return db.list_keys()


@router.delete("/keys/{key_id}")
def revoke_key(key_id: str, x_admin_password: str | None = Header(None)):
    _check(x_admin_password)
    db.revoke_key(key_id)
    return {"revoked": key_id}


@router.post("/keys/{key_id}/profile")
def set_profile(
    key_id: str,
    req: SetProfileRequest,
    x_admin_password: str | None = Header(None),
):
    _check(x_admin_password)
    if db.get_key_by_id(key_id) is None:
        raise HTTPException(404, "key not found")
    db.set_profile(key_id, req.profile)
    return {"ok": True}


@router.get("/transcripts")
def admin_list_transcripts(
    key_id: str,
    limit: int = 50,
    x_admin_password: str | None = Header(None),
):
    _check(x_admin_password)
    return db.list_transcripts_for_key(key_id, limit)


@router.get("/transcripts/{transcript_id}")
def admin_get_transcript(
    transcript_id: str, x_admin_password: str | None = Header(None)
):
    _check(x_admin_password)
    t = db.get_transcript(transcript_id)
    if t is None:
        raise HTTPException(404, "transcript not found")
    return t