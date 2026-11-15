import io
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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


@router.post("/resume")
async def upload_resume(
    file: UploadFile = File(...),
    token: dict = Depends(require_token),
):
    """Parse an uploaded resume and merge the result into the user's profile."""
    contents = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(contents))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError as exc:
            raise HTTPException(500, "pypdf is not installed on the server") from exc
        except Exception as exc:
            raise HTTPException(422, f"PDF parse failed: {exc}") from exc
    elif filename.endswith((".md", ".txt")):
        text = contents.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(400, "Unsupported file. Use PDF, MD, or TXT.")

    if len(text.strip()) < 100:
        raise HTTPException(422, "Resume text too short to parse")

    from ..resume_parser import parse_resume, save_parsed_profile

    parsed = await parse_resume(text)
    if not parsed:
        raise HTTPException(422, "Could not extract profile. Try a clearer file.")
    save_parsed_profile(token["sub"], parsed)
    return {"ok": True, "parsed": parsed}