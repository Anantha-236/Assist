import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db, quota
from ..config import DAILY_QUESTION_LIMIT
from ..deps import require_token
from ..llm import stream_answer

router = APIRouter(prefix="/answer", tags=["answer"])


class AnswerRequest(BaseModel):
    question: str
    context: str = ""


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _generate(question: str, context: str, key_id: str):
    if db.get_setting("answer_enabled", "1") != "1":
        yield _sse({"error": "assist disabled by admin"})
        yield "data: [DONE]\n\n"
        return

    limit = db.get_key_daily_limit(key_id, DAILY_QUESTION_LIMIT)
    if not db.try_increment_usage(key_id, limit):
        yield _sse({"error": f"daily question limit reached ({limit}/day for this key)"})
        yield "data: [DONE]\n\n"
        return

    # ... rest unchanged ...

    profile = db.get_profile(key_id)
    async for kind, payload in stream_answer(question, context, profile):
        if kind == "delta":
            yield _sse({"delta": payload})
        elif kind == "usage":
            db.record_token_usage(key_id, json.loads(payload))
        elif kind == "error":
            yield _sse({"error": payload})
            yield "data: [DONE]\n\n"
            return
        elif kind == "done":
            yield "data: [DONE]\n\n"
            return


@router.post("")
async def answer(req: AnswerRequest, token: dict = Depends(require_token)):
    return StreamingResponse(
        _generate(req.question, req.context, token["sub"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )