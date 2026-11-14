import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import auth, db
from ..telegram_service import send_activation_key, send_onboarding_link, send_message

router = APIRouter(prefix="/onboard", tags=["onboarding"])

TEMPLATES_DIR = Path(__file__).parent.parent / "admin_ui" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_invite(email: str, ttl_hours: int = 72) -> str:
    """Create a unique token and persist it in the DB."""
    token = secrets.token_urlsafe(16)  # fits Telegram's 64-char start param
    db.create_invite_row(token, email.strip().lower(), ttl_hours)
    return token


def _validate_invite(token: str) -> dict | None:
    info = db.get_invite_row(token)
    if not info:
        return None
    if info["used"]:
        return None
    # ISO string compare works lexicographically for UTC timestamps
    if info["expires_at"] < time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()):
        return None
    return info


def _public_base() -> str:
    return os.environ.get("ASSIST_PUBLIC_URL", "http://127.0.0.1:8000")


# ===== Telegram webhook =====
@router.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    """Receives updates from Telegram: /start TOKEN commands."""
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    message = update.get("message") or {}
    text = message.get("text") or ""
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if text.startswith("/start") and chat_id:
        # /start TOKEN or just /start
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            token = parts[1].strip()
            info = _validate_invite(token)
            if info:
                db.update_invite_chat_id(token, chat_id)
                onboarding_url = f"{_public_base()}/onboard/{token}"
                print(f"[onboard] linked chat {chat_id} to invite {token[:8]}…")
                await send_onboarding_link(str(chat_id), onboarding_url)
            else:
                await send_message(
                    str(chat_id),
                    "❌ This invite link is invalid or has expired. "
                    "Ask the admin for a new one."
                )
            return {"ok": True}
    from ..telegram_bot import handle_update
    await handle_update(update)
    return {"ok": True}


# ===== Onboarding form =====
@router.get("/{token}", response_class=HTMLResponse)
def onboarding_form(request: Request, token: str):
    info = _validate_invite(token)
    if not info:
        return templates.TemplateResponse(
            "onboarding_expired.html", {"request": request}, status_code=410)
    return templates.TemplateResponse(
        "onboarding.html",
        {"request": request, "token": token, "email": info["email"],
         "chat_linked": bool(info.get("chat_id"))})


@router.post("/{token}")
async def onboarding_submit(
    request: Request,
    token: str,
    full_name: str = Form(...),
    role: str = Form(...),
    experience: str = Form(...),
    skills: str = Form(...),
    company: str = Form(""),
    target_role: str = Form(""),
    target_company: str = Form(""),
    target_salary: str = Form(""),
    notice_period: str = Form(""),
    answer_style: str = Form(""),
):
    info = _validate_invite(token)
    if not info:
        return RedirectResponse("/onboard/expired", status_code=303)

    db.mark_invite_used(token)
    chat_id = info.get("chat_id")

    key_id, key_value = auth.generate_key()
    db.insert_key(key_id, key_value, label=full_name or info["email"])

    with db._conn() as c:
        c.execute(
            "UPDATE activation_keys SET role=?, experience=?, skills=?, "
            "company=?, target_role=?, target_company=?, target_salary=?, "
            "notice_period=?, answer_style=?, email=? WHERE key_id=?",
            (role, experience, skills, company, target_role, target_company,
             target_salary, notice_period, answer_style, info["email"], key_id))

    if chat_id:
        db.set_key_telegram_chat_id(key_id, chat_id)

    sent = False
    if chat_id:
        sent, _ = await send_activation_key(chat_id, key_value, full_name)

    return templates.TemplateResponse(
        "onboarding_done.html",
        {"request": request, "key": key_value, "email": info["email"],
         "email_sent": sent, "chat_linked": bool(chat_id)})