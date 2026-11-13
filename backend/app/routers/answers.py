from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..answer_reviewer import review_answer
from ..deps import require_token

router = APIRouter(prefix="/answers", tags=["answers"])


class AnswerUpload(BaseModel):
    session_id: str
    question: str
    answer: str
    question_ts: float
    answer_ts: float
    metrics: dict


@router.post("")
def upload_answer(req: AnswerUpload, token: dict = Depends(require_token)):
    features = db.get_features(token["sub"])
    if not features.get("save_answers", False):
        raise HTTPException(403, "save_answers not enabled")
    ans_id = db.insert_answer(
        key_id=token["sub"],
        session_id=req.session_id,
        question=req.question,
        answer=req.answer,
        question_ts=req.question_ts,
        answer_ts=req.answer_ts,
        metrics=req.metrics,
    )
    return {"id": ans_id}


@router.get("")
def list_answers(limit: int = 50, token: dict = Depends(require_token)):
    return db.list_answers_for_key(token["sub"], limit)


@router.post("/{ans_id}/review")
async def trigger_review(ans_id: str, token: dict = Depends(require_token)):
    ans = db.get_answer(ans_id)
    if not ans or ans["key_id"] != token["sub"]:
        raise HTTPException(404, "answer not found")
    review = await review_answer(ans_id)
    if not review:
        raise HTTPException(500, "review failed")
    return review