"""Assist backend — app assembly, middleware, routers."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, db
from .admin_ui import routes as admin_ui_routes
from .config import SESSION_SECRET
from .llm import close_client
from .routers import (
    activation, admin, admin_api_keys, answer, answers, me,
    onboarding, transcripts, usage,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if db.count_keys() == 0:
        key_id, key_value = auth.generate_key()
        db.insert_key(key_id, key_value, label="bootstrap")
        print("=" * 78)
        print(f"  BOOTSTRAP KEY:  {key_value}")
        print("=" * 78)
    yield
    await close_client()


app = FastAPI(title="Assist Backend", version="0.4.0", lifespan=lifespan)

_PUBLIC_ADMIN_PATHS = {
    "/admin/login", "/admin/login/start",
    "/admin/login/verify-totp", "/admin/setup-totp",
    "/admin/setup-totp/verify",
}


@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/admin") and path not in _PUBLIC_ADMIN_PATHS:
        # JSON API + data endpoint require admin session too
        if not request.session.get("admin"):
            if "text/html" in (request.headers.get("accept") or ""):
                return RedirectResponse("/admin/login", status_code=303)
            return Response(status_code=403)
    return await call_next(request)


app.add_middleware(
    SessionMiddleware, secret_key=SESSION_SECRET,
    session_cookie="assist_session", max_age=60 * 60 * 8, same_site="lax",
)

_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

app.include_router(activation.router)
app.include_router(admin.router)
app.include_router(admin_api_keys.router)
app.include_router(answer.router)
app.include_router(answers.router)
app.include_router(me.router)
app.include_router(onboarding.router)
app.include_router(transcripts.router)
app.include_router(usage.router)
app.include_router(admin_ui_routes.router)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)