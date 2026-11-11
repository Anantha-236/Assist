from fastapi import APIRouter, Depends

from .. import db, quota
from ..config import DAILY_QUESTION_LIMIT
from ..deps import require_token

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
def my_usage(token: dict = Depends(require_token)):
    key_id = token["sub"]
    limit = db.get_key_daily_limit(key_id, DAILY_QUESTION_LIMIT)
    return {
        "used_today": db.get_today_usage(key_id),
        "daily_limit": limit,
    }


@router.get("/quota")
def openrouter_quota(token: dict = Depends(require_token)):
    return quota.status()