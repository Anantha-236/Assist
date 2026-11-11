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
from .routers import activation, admin, answer, transcripts, usage


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if db.count_keys() == 0:
        key_id, key_value = auth.generate_key()
        db.insert_key(key_id, key_value, label="bootstrap")
        print("=" * 78)
        print(f"  BOOTSTRAP KEY:  {key_value}")
        print("  Use this to activate your first device.")
        print("=" * 78)
    yield
    await close_client()


app = FastAPI(title="Assist Backend", version="0.3.0", lifespan=lifespan)

# Middleware order: last-added runs first (outermost).
# We want SessionMiddleware to run BEFORE the admin check,
# so admin check is registered first, Session last.
_PUBLIC_ADMIN_PATHS = {
    "/admin/login",
    "/admin/login/request-otp",
    "/admin/login/verify-otp",
}


@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/admin") and path not in _PUBLIC_ADMIN_PATHS:
        if not request.session.get("admin"):
            return RedirectResponse("/admin/login", status_code=303)
    return await call_next(request)


app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="assist_session",
    max_age=60 * 60 * 8,
    same_site="lax",
)

_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

app.include_router(activation.router)
app.include_router(admin.router)
app.include_router(answer.router)
app.include_router(transcripts.router)
app.include_router(usage.router)

app.include_router(admin_ui_routes.router)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)