from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db, email_service
from ..deps import require_token

router = APIRouter(prefix="/transcripts", tags=["transcripts"])


class Segment(BaseModel):
    t: float
    dur: float
    text: str


class UploadRequest(BaseModel):
    session_id: str
    session_started: str
    session_ended: str
    segments: list[Segment]


@router.post("")
def upload(req: UploadRequest, token: dict = Depends(require_token)):
    tid = db.upsert_transcript(
        session_id=req.session_id,
        key_id=token["sub"],
        started=req.session_started,
        ended=req.session_ended,
        segments=[s.model_dump() for s in req.segments],
    )
    return {"session_id": req.session_id, "transcript_id": tid,
            "segment_count": len(req.segments)}


@router.post("/{session_id}/email")
async def email_me(session_id: str, token: dict = Depends(require_token)):
    t = db.get_transcript_by_session(session_id)
    if t is None or t["key_id"] != token["sub"]:
        raise HTTPException(404, "transcript not found")
    to = db.get_key_email(token["sub"])
    if not to:
        raise HTTPException(400, "no email on file — ask admin to add it")
    ok = await email_service.send_transcript_email(to, t)
    if not ok:
        raise HTTPException(500, "email delivery failed")
    return {"ok": True, "to": to}


@router.get("")
def list_mine(limit: int = 20, token: dict = Depends(require_token)):
    return db.list_transcripts_for_key(token["sub"], limit)


@router.get("/{transcript_id}")
def get_mine(transcript_id: str, token: dict = Depends(require_token)):
    t = db.get_transcript(transcript_id)
    if t is None or t["key_id"] != token["sub"]:
        raise HTTPException(404, "transcript not found")
    return t