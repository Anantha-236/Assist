
"""Admin dashboard: OTP login, overview, keys, transcripts, settings."""

from pathlib import Path

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import auth, db, quota
from ..config import ADMIN_EMAILS, DAILY_QUESTION_LIMIT
from ..email_service import send_activation_key_email, send_otp_email


router = APIRouter(prefix="/admin", tags=["admin-ui"])

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _ctx(request: Request, **kw) -> dict:
    """Build shared template context."""
    base = {
        "request": request,
        "admin": True,
        "active": "",
    }
    base.update(kw)
    return base


def _render(request: Request, name: str, **kw):
    """Render templates using the Starlette 0.29+ signature."""
    return templates.TemplateResponse(
        request=request,
        name=name,
        context=_ctx(request, **kw),
    )


# ---------------- AUTH (OTP) ----------------

@router.get("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    error: str = "",
    step: str = "email",
):
    if step == "otp":
        email = request.session.get("otp_email", "")

        if not email:
            return RedirectResponse(
                "/admin/login",
                status_code=303,
            )

        return _render(
            request,
            "login_otp.html",
            email=email,
            error=error,
        )

    return _render(
        request,
        "login.html",
        error=error,
        active="login",
    )


@router.post("/login/request-otp")
async def request_otp(
    request: Request,
    email: str = Form(...),
):
    email_lower = email.strip().lower()

    if email_lower not in [e.lower() for e in ADMIN_EMAILS]:
        return RedirectResponse(
            "/admin/login?step=otp&error=If+authorised,+a+code+was+sent",
            status_code=303,
        )

    otp = db.create_admin_otp(email_lower)

    sent = await send_otp_email(email_lower, otp)

    if not sent:
        # SMTP not configured — log the code so testing works.
        print(f"[OTP] {email_lower} -> {otp}")

    request.session["otp_email"] = email_lower

    return RedirectResponse(
        "/admin/login?step=otp",
        status_code=303,
    )


@router.post("/login/verify-otp")
def verify_otp(
    request: Request,
    otp: str = Form(...),
):
    email = request.session.get("otp_email")

    if not email:
        return RedirectResponse(
            "/admin/login",
            status_code=303,
        )

    if db.verify_admin_otp(email, otp.strip()):
        request.session.pop("otp_email", None)
        request.session["admin"] = True

        return RedirectResponse(
            "/admin/",
            status_code=303,
        )

    return RedirectResponse(
        "/admin/login?step=otp&error=Invalid+or+expired+code",
        status_code=303,
    )


@router.get("/logout")
def logout(request: Request):
    request.session.clear()

    return RedirectResponse(
        "/admin/login",
        status_code=303,
    )


# ---------------- OVERVIEW ----------------

@router.get("/", response_class=HTMLResponse)
def overview(request: Request):
    keys = db.list_keys()
    active = [k for k in keys if not k["revoked"]]

    usage_all = db.get_today_usage_all()

    return _render(
        request,
        "dashboard.html",
        active="overview",
        total_keys=len(keys),
        active_keys=len(active),
        usage_today=usage_all["total"],
        token_today=db.get_token_usage_today(),
        daily_limit=DAILY_QUESTION_LIMIT,
        quota=quota.status(),
        settings=db.get_all_settings(),
    )


# ---------------- KEYS ----------------

@router.get("/keys", response_class=HTMLResponse)
def keys_list(request: Request):
    keys = db.list_keys()

    for k in keys:
        k["usage_today"] = db.get_today_usage(k["key_id"])
        k["usage_total"] = db.get_total_usage_for_key(k["key_id"])

    return _render(
        request,
        "keys.html",
        active="keys",
        keys=keys,
        daily_limit=DAILY_QUESTION_LIMIT,
    )


@router.post("/keys")
async def create_key(
    request: Request,
    label: str = Form(""),
    send_to_email: str = Form(""),
):
    key_id, key_value = auth.generate_key()

    db.insert_key(
        key_id,
        key_value,
        label=label or None,
    )

    if send_to_email.strip():
        try:
            await send_activation_key_email(
                send_to_email.strip(),
                key_value,
                label or None,
            )
        except Exception as e:
            print(f"[admin] key email failed: {e}")

    return RedirectResponse(
        f"/admin/keys/{key_id}?created=1",
        status_code=303,
    )


@router.get("/keys/{key_id}", response_class=HTMLResponse)
def key_detail(
    request: Request,
    key_id: str,
    created: str = "",
    saved: str = "",
):
    row = db.get_key_by_id(key_id)

    if row is None:
        return RedirectResponse(
            "/admin/keys",
            status_code=303,
        )

    k = dict(row)

    k["usage_today"] = db.get_today_usage(key_id)
    k["usage_total"] = db.get_total_usage_for_key(key_id)
    k["tokens"] = db.get_token_usage_for_key(key_id)

    return _render(
        request,
        "key_detail.html",
        active="keys",
        k=k,
        profile=db.get_profile(key_id),
        history=db.get_usage_history(key_id),
        transcripts=db.list_transcripts_for_key(key_id, 20),
        daily_limit=db.get_key_daily_limit(
            key_id,
            DAILY_QUESTION_LIMIT,
        ),
        just_created=bool(created),
        just_saved=bool(saved),
    )


@router.post("/keys/{key_id}/revoke")
def revoke_key_form(key_id: str):
    db.revoke_key(key_id)

    return RedirectResponse(
        f"/admin/keys/{key_id}",
        status_code=303,
    )


@router.post("/keys/{key_id}/profile")
def set_profile_form(
    key_id: str,
    role: str = Form(""),
    experience: str = Form(""),
    skills: str = Form(""),
):
    db.set_profile(
        key_id,
        {
            "role": role,
            "experience": experience,
            "skills": skills,
        },
    )

    return RedirectResponse(
        f"/admin/keys/{key_id}",
        status_code=303,
    )


@router.post("/keys/{key_id}/limit")
def set_limit_form(
    key_id: str,
    tier: str = Form("free"),
    daily_limit: int = Form(200),
):
    daily_limit = max(1, min(daily_limit, 100_000))

    db.set_key_limit(
        key_id,
        tier,
        daily_limit,
    )

    return RedirectResponse(
        f"/admin/keys/{key_id}?saved=1",
        status_code=303,
    )


# ---------------- TRANSCRIPTS ----------------

@router.get("/transcripts", response_class=HTMLResponse)
def transcripts_list(request: Request):
    return _render(
        request,
        "transcripts.html",
        active="transcripts",
        transcripts=db.list_all_transcripts(100),
    )


@router.get(
    "/transcripts/{transcript_id}",
    response_class=HTMLResponse,
)
def transcript_detail(
    request: Request,
    transcript_id: str,
):
    t = db.get_transcript(transcript_id)

    if t is None:
        return RedirectResponse(
            "/admin/transcripts",
            status_code=303,
        )

    return _render(
        request,
        "transcript_detail.html",
        active="transcripts",
        t=t,
    )


# ---------------- SETTINGS ----------------

@router.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request):
    return _render(
        request,
        "settings.html",
        active="settings",
        settings=db.get_all_settings(),
    )


@router.post("/settings")
def settings_save(
    answer_enabled: str = Form("0"),
    max_tokens: str = Form("80"),
    system_prompt_note: str = Form(""),
):
    db.set_setting(
        "answer_enabled",
        "1" if answer_enabled == "1" else "0",
    )

    db.set_setting(
        "max_tokens",
        max_tokens,
    )

    db.set_setting(
        "system_prompt_note",
        system_prompt_note,
    )

    return RedirectResponse(
        "/admin/settings?saved=1",
        status_code=303,
    )


# ---------------- OPENROUTER API TEST ----------------

@router.post("/api-test")
async def admin_api_test(request: Request):
    """Make a real request to OpenRouter and return the result."""

    from ..config import (
        OPENROUTER_API_KEY,
        OPENROUTER_BASE_URL,
        OPENROUTER_MODELS_FAST,
    )

    if not OPENROUTER_API_KEY or any(
        tok in OPENROUTER_API_KEY
        for tok in ("REPLACE", "DEMO", "xxxx")
    ):
        return {
            "ok": False,
            "error": "OPENROUTER_API_KEY not configured in .env",
        }

    if not OPENROUTER_MODELS_FAST:
        return {
            "ok": False,
            "error": "OPENROUTER_MODELS_FAST is empty in .env",
        }

    model = OPENROUTER_MODELS_FAST[0]

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Reply with just the word OK.",
                        }
                    ],
                    "max_tokens": 8,
                },
            )

        if response.status_code != 200:
            return {
                "ok": False,
                "model": model,
                "status": response.status_code,
                "error": response.text[:400],
            }

        data = response.json()

        reply = (
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        return {
            "ok": True,
            "model": model,
            "reply": reply.strip()[:100],
        }

    except Exception as e:
        return {
            "ok": False,
            "model": model,
            "error": f"{type(e).__name__}: {e}",
        }
