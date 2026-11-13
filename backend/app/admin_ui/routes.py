"""Admin dashboard: TOTP login, keys, features, usage, routing, onboarding."""

import base64
import io
import os
from pathlib import Path

import pyotp
import qrcode
from fastapi import APIRouter, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import auth, db, quota
from ..config import ADMIN_EMAILS, ADMIN_PASSWORD, DAILY_QUESTION_LIMIT
from ..features import DEFAULT_FEATURES, FEATURE_LABELS
from ..models import MODEL_REGISTRY
from ..provider_limits import PROVIDER_LIMITS
from ..usage_tracker import key_status_for_dashboard

router = APIRouter(prefix="/admin", tags=["admin-ui"])

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _ctx(request, **kw):
    base = {"request": request, "admin": True, "active": ""}
    base.update(kw)
    return base


def _render(request, name, **kw):
    return templates.TemplateResponse(
        request=request, name=name, context=_ctx(request, **kw))


# ===== auth (TOTP) =====
@router.get("/login", response_class=HTMLResponse)
def login_form(request, error=""):
    return _render(request, "login.html", error=error, active="login")


@router.post("/login/start")
def login_start(request, email: str = Form(...)):
    e = email.strip().lower()
    if e not in [x.lower() for x in ADMIN_EMAILS]:
        return RedirectResponse("/admin/login?error=Email+not+authorised", status_code=303)
    if db.get_totp_secret(e):
        return RedirectResponse(f"/admin/login/verify-totp?email={e}", status_code=303)
    return RedirectResponse(f"/admin/setup-totp?email={e}", status_code=303)


@router.get("/setup-totp", response_class=HTMLResponse)
def setup_totp(request, email="", error=""):
    e = email.strip().lower()
    if e not in [x.lower() for x in ADMIN_EMAILS]:
        return RedirectResponse("/admin/login?error=Email+not+authorised", status_code=303)
    secret = pyotp.random_base32()
    request.session["pending_totp_secret"] = secret
    request.session["pending_totp_email"] = e
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=e, issuer_name="Assist Admin")
    img = qrcode.make(uri)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    return _render(request, "setup_totp.html", email=e, secret=secret,
                   qr_b64=qr_b64, error=error, active="login")


@router.post("/setup-totp/verify")
def setup_totp_verify(request, code: str = Form(...)):
    secret = request.session.get("pending_totp_secret")
    email = request.session.get("pending_totp_email")
    if not secret or not email:
        return RedirectResponse("/admin/login?error=Session+expired", status_code=303)
    if not pyotp.TOTP(secret).verify(code.strip(), valid_window=1):
        return RedirectResponse(f"/admin/setup-totp?email={email}&error=Invalid+code", status_code=303)
    db.set_totp_secret(email, secret)
    request.session.pop("pending_totp_secret", None)
    request.session.pop("pending_totp_email", None)
    request.session["admin"] = True
    request.session["admin_email"] = email
    return RedirectResponse("/admin/", status_code=303)


@router.get("/login/verify-totp", response_class=HTMLResponse)
def login_verify_totp_form(request, email="", error=""):
    e = email.strip().lower()
    if e not in [x.lower() for x in ADMIN_EMAILS]:
        return RedirectResponse("/admin/login?error=Email+not+authorised", status_code=303)
    if not db.get_totp_secret(e):
        return RedirectResponse(f"/admin/setup-totp?email={e}", status_code=303)
    return _render(request, "verify_totp.html", email=e, error=error, active="login")


@router.post("/login/verify-totp")
def login_verify_totp(request, email: str = Form(...), code: str = Form(...)):
    e = email.strip().lower()
    secret = db.get_totp_secret(e)
    if not secret:
        return RedirectResponse(f"/admin/setup-totp?email={e}", status_code=303)
    if pyotp.TOTP(secret).verify(code.strip(), valid_window=1):
        request.session["admin"] = True
        request.session["admin_email"] = e
        return RedirectResponse("/admin/", status_code=303)
    return RedirectResponse(f"/admin/login/verify-totp?email={e}&error=Invalid+code", status_code=303)


@router.get("/logout")
def logout(request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.post("/api/reset-totp")
def reset_totp_api(email: str = Form(...), x_admin_password: str = Header(None)):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(401, "admin password required")
    db.clear_totp_secret(email.strip().lower())
    return {"ok": True, "reset": email}


# ===== overview =====
@router.get("/", response_class=HTMLResponse)
def overview(request):
    keys = db.list_keys()
    active = [k for k in keys if not k["revoked"]]
    return _render(request, "dashboard.html", active="overview",
                   total_keys=len(keys), active_keys=len(active),
                   usage_today=db.get_today_usage_all()["total"],
                   token_today=db.get_token_usage_today(),
                   daily_limit=DAILY_QUESTION_LIMIT,
                   quota=quota.status(),
                   settings=db.get_all_settings())


# ===== keys =====
@router.get("/keys", response_class=HTMLResponse)
def keys_list(request, invited: str = ""):
    keys = db.list_keys()
    for k in keys:
        k["usage_today"] = db.get_today_usage(k["key_id"])
        k["usage_total"] = db.get_total_usage_for_key(k["key_id"])
    return _render(request, "keys.html", active="keys", keys=keys,
                   daily_limit=DAILY_QUESTION_LIMIT, invited=bool(invited))


@router.post("/keys")
async def create_key(request, label: str = Form(""), send_to_email: str = Form("")):
    key_id, key_value = auth.generate_key()
    db.insert_key(key_id, key_value, label=label or None)
    if send_to_email.strip():
        try:
            from ..email_service import send_activation_key_email
            await send_activation_key_email(send_to_email.strip(), key_value, label or None)
        except Exception as e:
            print(f"[admin] key email failed: {e}")
    return RedirectResponse(f"/admin/keys/{key_id}?created=1", status_code=303)


@router.post("/keys/invite")
async def keys_invite(request, email: str = Form(...)):
    from ..routers.onboarding import create_invite
    from ..email_service import _send
    token = create_invite(email.strip().lower())
    base = os.environ.get("ASSIST_PUBLIC_URL", "http://127.0.0.1:8000")
    link = f"{base}/onboard/{token}"
    html = (
        f"<p>You're invited to Assist.</p>"
        f"<p><a href='{link}' style='background:#6366f1;color:#fff;"
        f"padding:10px 20px;border-radius:6px;text-decoration:none;"
        f"display:inline-block;'>Complete your profile</a></p>"
        f"<p style='color:#888;'>This link expires in 72 hours. "
        f"You'll receive your activation key by email after completing the form.</p>"
    )
    await _send(email, "You're invited to Assist", html)
    return RedirectResponse("/admin/keys?invited=1", status_code=303)


@router.get("/keys/{key_id}", response_class=HTMLResponse)
def key_detail(request, key_id, created="", saved=""):
    row = db.get_key_by_id(key_id)
    if row is None:
        return RedirectResponse("/admin/keys", status_code=303)
    k = dict(row)
    k["usage_today"] = db.get_today_usage(key_id)
    k["usage_total"] = db.get_total_usage_for_key(key_id)
    k["tokens"] = db.get_token_usage_for_key(key_id)
    return _render(request, "key_detail.html", active="keys", k=k,
                   profile=db.get_profile(key_id),
                   history=db.get_usage_history(key_id),
                   transcripts=db.list_transcripts_for_key(key_id, 20),
                   daily_limit=db.get_key_daily_limit(key_id, DAILY_QUESTION_LIMIT),
                   just_created=bool(created), just_saved=bool(saved),
                   features=db.get_features(key_id))


@router.post("/keys/{key_id}/revoke")
def revoke_key_form(key_id):
    db.revoke_key(key_id)
    return RedirectResponse(f"/admin/keys/{key_id}", status_code=303)


@router.post("/keys/{key_id}/profile")
def set_profile_form(
    key_id,
    role: str = Form(""), experience: str = Form(""), skills: str = Form(""),
    company: str = Form(""), target_role: str = Form(""),
    target_company: str = Form(""), industry: str = Form(""),
    achievements: str = Form(""), projects: str = Form(""),
    target_salary: str = Form(""), notice_period: str = Form(""),
    answer_style: str = Form(""), email: str = Form(""),
):
    profile = {"role": role, "experience": experience, "skills": skills,
               "company": company, "target_role": target_role,
               "target_company": target_company, "industry": industry,
               "achievements": achievements, "projects": projects,
               "target_salary": target_salary, "notice_period": notice_period,
               "answer_style": answer_style}
    db.set_profile(key_id, profile)
    with db._conn() as c:
        c.execute(
            "UPDATE activation_keys SET role=?, experience=?, skills=?, "
            "company=?, target_role=?, target_company=?, industry=?, "
            "achievements=?, projects=?, target_salary=?, notice_period=?, "
            "answer_style=?, email=? WHERE key_id=?",
            (role, experience, skills, company, target_role, target_company,
             industry, achievements, projects, target_salary, notice_period,
             answer_style, email, key_id))
    return RedirectResponse(f"/admin/keys/{key_id}?saved=1", status_code=303)


@router.post("/keys/{key_id}/limit")
def set_limit_form(key_id, tier: str = Form("free"), daily_limit: int = Form(200)):
    daily_limit = max(1, min(daily_limit, 100_000))
    db.set_key_limit(key_id, tier, daily_limit)
    return RedirectResponse(f"/admin/keys/{key_id}?saved=1", status_code=303)


@router.get("/keys/{key_id}/features", response_class=HTMLResponse)
def features_form(request, key_id):
    row = db.get_key_by_id(key_id)
    if row is None:
        return RedirectResponse("/admin/keys", status_code=303)
    return _render(request, "features.html", active="keys",
                   key_id=key_id, key_value=row["key_value"],
                   features=db.get_features(key_id),
                   labels=FEATURE_LABELS, defaults=DEFAULT_FEATURES)


@router.post("/keys/{key_id}/features")
async def features_save(request, key_id, grant_basic: str = Form("0")):
    form = await request.form()
    if grant_basic == "1":
        features = dict(DEFAULT_FEATURES)
    else:
        features = {k: (form.get(k) == "1") for k in DEFAULT_FEATURES}
    db.set_features(key_id, features)
    return RedirectResponse(f"/admin/keys/{key_id}?saved=1", status_code=303)


# ===== API key vault =====
@router.get("/api-keys", response_class=HTMLResponse)
def api_keys_page(request, saved="", error=""):
    keys = db.list_api_keys()
    return _render(request, "api_keys.html", active="api_keys",
                   keys=keys, saved=bool(saved), error=error)


@router.post("/api-keys")
def api_keys_create(
    provider: str = Form(...), key_value: str = Form(...),
    label: str = Form(""), priority: int = Form(100),
):
    kv = key_value.strip()
    if not kv:
        return RedirectResponse("/admin/api-keys?error=Empty+key", status_code=303)
    if provider == "groq" and not kv.startswith("gsk_"):
        return RedirectResponse("/admin/api-keys?error=groq+keys+start+with+gsk_", status_code=303)
    if provider == "openrouter" and not kv.startswith("sk-or-"):
        return RedirectResponse("/admin/api-keys?error=openrouter+keys+start+with+sk-or-", status_code=303)
    db.create_api_key(provider, kv, label or None, priority)
    return RedirectResponse("/admin/api-keys?saved=1", status_code=303)


@router.post("/api-keys/{key_id}/toggle")
def api_keys_toggle(key_id):
    k = db.get_api_key(key_id)
    if k:
        db.set_api_key_active(key_id, not bool(k["active"]))
    return RedirectResponse("/admin/api-keys", status_code=303)


@router.post("/api-keys/{key_id}/delete")
def api_keys_delete(key_id):
    db.delete_api_key(key_id)
    return RedirectResponse("/admin/api-keys", status_code=303)


@router.post("/api-keys/{key_id}/priority")
def api_keys_priority(key_id, priority: int = Form(...)):
    db.set_api_key_priority(key_id, priority)
    return RedirectResponse("/admin/api-keys", status_code=303)


# ===== provider usage + chart =====
@router.get("/provider-usage", response_class=HTMLResponse)
def provider_usage_page(request, saved=""):
    keys = db.list_api_keys()
    rows = []
    for k in keys:
        st = key_status_for_dashboard(k["id"], k["provider"])
        rows.append({
            "id": k["id"], "provider": k["provider"],
            "label": k.get("label") or "—",
            "key_masked": f"{k['key_value'][:10]}…{k['key_value'][-4:]}",
            "active": bool(k["active"]), **st,
        })
    agg = {}
    for r in rows:
        a = agg.setdefault(r["provider"], {"keys": 0, "active_keys": 0,
                                            "suspended_keys": 0, "total_requests": 0,
                                            "total_tokens_in": 0, "total_tokens_out": 0})
        a["keys"] += 1
        a["active_keys"] += 1 if r["active"] else 0
        a["suspended_keys"] += 1 if r["suspended"] else 0
        a["total_requests"] += r["requests"]
        a["total_tokens_in"] += r["tokens_in"]
        a["total_tokens_out"] += r["tokens_out"]
    return _render(request, "provider_usage.html", active="provider_usage",
                   rows=rows, aggregates=agg, saved=bool(saved),
                   limits=PROVIDER_LIMITS)


@router.get("/api/provider-usage/data")
def provider_usage_data(request):
    import time as _time
    keys = db.list_api_keys()
    out = []
    for k in keys:
        st = key_status_for_dashboard(k["id"], k["provider"])
        urow = db.get_provider_usage(k["id"], k["provider"]) or {}
        rem_req = urow.get("remaining_requests")
        lim_req = urow.get("limit_requests")
        if rem_req is not None and lim_req:
            used = lim_req - rem_req
            pct = (used / lim_req * 100) if lim_req else 0
            source = "live-header"
        else:
            used = st["requests"]
            pct = st["request_pct"] or 0
            source = "internal-counter"
        if st["suspended"] or pct >= 98:
            color = "red"
        elif pct >= 80:
            color = "orange"
        else:
            color = "green"
        out.append({
            "key_id": k["id"], "label": k.get("label") or k["key_value"][:12],
            "provider": k["provider"], "used": used,
            "remaining": rem_req if rem_req is not None else (
                (lim_req - used) if lim_req else None),
            "limit": lim_req, "pct": round(pct, 1), "color": color,
            "suspended": st["suspended"], "source": source,
            "reset_at": urow.get("reset_at"),
        })
    return JSONResponse({"keys": out, "ts": int(_time.time())})


@router.post("/provider-usage/{key_id}/unsuspend")
def unsuspend_key(key_id):
    with db._conn() as c:
        c.execute(
            "UPDATE provider_usage SET suspended = 0, suspended_at = NULL "
            "WHERE key_id = ? AND day = ?", (key_id, db._today()))
    return RedirectResponse("/admin/provider-usage", status_code=303)


# ===== routing =====
@router.get("/routing", response_class=HTMLResponse)
def routing_page(request, saved=""):
    return _render(request, "routing.html", active="routing",
                   registry=MODEL_REGISTRY,
                   provider_order=db.get_setting("router_provider_order", "groq,openrouter"),
                   auto_route=db.get_setting("auto_route_enabled", "1") == "1",
                   saved=bool(saved))


@router.post("/routing")
def routing_save(provider_order: str = Form("groq,openrouter"),
                 auto_route: str = Form("0")):
    db.set_setting("router_provider_order", provider_order)
    db.set_setting("auto_route_enabled", "1" if auto_route == "1" else "0")
    return RedirectResponse("/admin/routing?saved=1", status_code=303)


# ===== usage map + pricing =====
@router.get("/usage-map", response_class=HTMLResponse)
def usage_map_page(request, days: int = 30, saved: str = ""):
    rows = db.user_usage_summary(days)
    pricing = db.get_pricing()

    def cost(row):
        t = 0.0
        for provider, p in row["providers"].items():
            t += (p["prompt"] / 1_000_000) * pricing.get(f"{provider}_input_per_mtok", 0.1)
            t += (p["completion"] / 1_000_000) * pricing.get(f"{provider}_output_per_mtok", 0.2)
        return t

    grand = 0.0
    for r in rows:
        r["cost"] = cost(r)
        grand += r["cost"]
    return _render(request, "usage_map.html", active="usage_map", rows=rows,
                   days=days, grand_total=grand, pricing=pricing, saved=bool(saved))


@router.post("/pricing")
def pricing_save(groq_input: float = Form(...), groq_output: float = Form(...),
                 openrouter_input: float = Form(...), openrouter_output: float = Form(...)):
    db.set_pricing("groq", groq_input, groq_output)
    db.set_pricing("openrouter", openrouter_input, openrouter_output)
    return RedirectResponse("/admin/usage-map?saved=1", status_code=303)


# ===== transcripts =====
@router.get("/transcripts", response_class=HTMLResponse)
def transcripts_list(request):
    return _render(request, "transcripts.html", active="transcripts",
                   transcripts=db.list_all_transcripts(100))


@router.get("/transcripts/{transcript_id}", response_class=HTMLResponse)
def transcript_detail(request, transcript_id):
    t = db.get_transcript(transcript_id)
    if t is None:
        return RedirectResponse("/admin/transcripts", status_code=303)
    return _render(request, "transcript_detail.html", active="transcripts", t=t)


# ===== answers =====
@router.get("/keys/{key_id}/answers", response_class=HTMLResponse)
def key_answers(request, key_id):
    row = db.get_key_by_id(key_id)
    if row is None:
        return RedirectResponse("/admin/keys", status_code=303)
    return _render(request, "key_answers.html", active="keys",
                   key_id=key_id, key_value=row["key_value"],
                   answers=db.list_answers_for_key(key_id, 50))


@router.post("/answers/{ans_id}/review")
async def trigger_review_form(ans_id):
    from ..answer_reviewer import review_answer
    await review_answer(ans_id)
    return RedirectResponse(f"/admin/answers/{ans_id}", status_code=303)


@router.get("/answers/{ans_id}", response_class=HTMLResponse)
def answer_detail(request, ans_id):
    ans = db.get_answer(ans_id)
    if not ans:
        return RedirectResponse("/admin/keys", status_code=303)
    return _render(request, "answer_detail.html", active="keys", ans=ans)


# ===== settings =====
@router.get("/settings", response_class=HTMLResponse)
def settings_view(request):
    return _render(request, "settings.html", active="settings",
                   settings=db.get_all_settings())


@router.post("/settings")
def settings_save(answer_enabled: str = Form("0"), max_tokens: str = Form("80"),
                  system_prompt_note: str = Form("")):
    db.set_setting("answer_enabled", "1" if answer_enabled == "1" else "0")
    db.set_setting("max_tokens", max_tokens)
    db.set_setting("system_prompt_note", system_prompt_note)
    return RedirectResponse("/admin/settings?saved=1", status_code=303)