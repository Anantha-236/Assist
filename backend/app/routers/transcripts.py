from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..deps import require_token
from ..telegram_service import send_transcript

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


@router.post("/{session_id}/telegram")
async def send_to_telegram(session_id: str, token: dict = Depends(require_token)):
    """Send a transcript via Telegram to the user's linked chat."""
    features = db.get_features(token["sub"])
    if not features.get("email_transcripts", False):
        raise HTTPException(403, "transcript delivery not enabled")

    t = db.get_transcript_by_session(session_id)
    if t is None or t["key_id"] != token["sub"]:
        raise HTTPException(404, "transcript not found")

    chat_id = db.get_key_telegram_chat_id(token["sub"])
    if not chat_id:
        raise HTTPException(400, "no Telegram linked — complete onboarding via the bot first")

    ok, err = await send_transcript(chat_id, t)
    if not ok:
        raise HTTPException(500, err or "telegram delivery failed")
    return {"ok": True, "chat_id": chat_id}


# Backward-compat alias: old desktop clients call /email
@router.post("/{session_id}/email")
async def send_compat(session_id: str, token: dict = Depends(require_token)):
    return await send_to_telegram(session_id, token)


@router.get("")
def list_mine(limit: int = 20, token: dict = Depends(require_token)):
    return db.list_transcripts_for_key(token["sub"], limit)


@router.get("/{transcript_id}")
def get_mine(transcript_id: str, token: dict = Depends(require_token)):
    t = db.get_transcript(transcript_id)
    if t is None or t["key_id"] != token["sub"]:
        raise HTTPException(404, "transcript not found")
    return t