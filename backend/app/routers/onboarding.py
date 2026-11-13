import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import auth, db
from ..email_service import send_activation_key_email

router = APIRouter(prefix="/onboard", tags=["onboarding"])

TEMPLATES_DIR = Path(__file__).parent.parent / "admin_ui" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_invites = {}


def create_invite(email, ttl_hours=72):
    token = secrets.token_urlsafe(24)
    _invites[token] = {"email": email, "expires": time.time() + ttl_hours * 3600,
                       "used": False}
    return token


def validate_invite(token):
    info = _invites.get(token)
    if not info or info["used"] or info["expires"] < time.time():
        return None
    return info


@router.get("/{token}", response_class=HTMLResponse)
def onboarding_form(request: Request, token: str):
    info = validate_invite(token)
    if not info:
        return templates.TemplateResponse(
            "onboarding_expired.html", {"request": request}, status_code=410)
    return templates.TemplateResponse(
        "onboarding.html",
        {"request": request, "token": token, "email": info["email"]})


@router.post("/{token}")
async def onboarding_submit(
    request: Request, token: str,
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
    info = validate_invite(token)
    if not info:
        return RedirectResponse("/onboard/expired", status_code=303)

    _invites[token]["used"] = True

    key_id, key_value = auth.generate_key()
    db.insert_key(key_id, key_value, label=full_name or info["email"])

    with db._conn() as c:
        c.execute(
            "UPDATE activation_keys SET role=?, experience=?, skills=?, "
            "company=?, target_role=?, target_company=?, target_salary=?, "
            "notice_period=?, answer_style=?, email=? WHERE key_id=?",
            (role, experience, skills, company, target_role, target_company,
             target_salary, notice_period, answer_style, info["email"], key_id))

    sent = False
    try:
        sent = await send_activation_key_email(info["email"], key_value, full_name)
    except Exception as e:
        print(f"[onboard] email failed: {e}")

    return templates.TemplateResponse(
        "onboarding_done.html",
        {"request": request, "key": key_value, "email": info["email"],
         "email_sent": sent})