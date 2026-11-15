import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import db
from ..deps import require_token

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/links")
def my_links(token: dict = Depends(require_token)):
    """Return useful URLs for the current user."""
    bot = os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@")
    return {
        "telegram_bot_url": f"https://t.me/{bot}" if bot else None,
        "support_contact": os.environ.get("ASSIST_SUPPORT_CONTACT", ""),
    }


@router.get("/profile")
def my_profile(token: dict = Depends(require_token)):
    """Return the admin-configured profile for the current key."""
    profile = db.get_full_profile(token["sub"])
    return profile or {}


@router.get("/features")
def my_features(token: dict = Depends(require_token)):
    """Return this user's feature flags."""
    return db.get_features(token["sub"])


class ProfileUpdate(BaseModel):
    role: str = ""
    experience: str = ""
    skills: str = ""
    company: str = ""
    target_role: str = ""
    target_company: str = ""
    target_salary: str = ""
    notice_period: str = ""
    answer_style: str = ""


@router.post("/profile")
def update_profile(req: ProfileUpdate, token: dict = Depends(require_token)):
    """User updates their own profile."""
    key_id = token["sub"]
    with db._conn() as c:
        c.execute(
            "UPDATE activation_keys SET role=?, experience=?, skills=?, "
            "company=?, target_role=?, target_company=?, target_salary=?, "
            "notice_period=?, answer_style=? WHERE key_id=?",
            (req.role, req.experience, req.skills, req.company,
             req.target_role, req.target_company, req.target_salary,
             req.notice_period, req.answer_style, key_id))
    return {"ok": True}