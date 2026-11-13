from fastapi import APIRouter, Form, Header, HTTPException

from .. import db
from ..config import ADMIN_PASSWORD
from ..env_writer import sync_key

router = APIRouter(prefix="/admin/api/api-keys", tags=["admin-api-keys"])


def _check(password):
    if password != ADMIN_PASSWORD:
        raise HTTPException(401, "admin password required")


@router.post("")
def create_key(
    provider: str = Form(...),
    key_value: str = Form(...),
    label: str = Form(""),
    priority: int = Form(100),
    env_var_name: str = Form(""),
    x_admin_password: str = Header(None),
):
    _check(x_admin_password)
    key_value = key_value.strip()
    if not key_value:
        raise HTTPException(400, "key_value required")
    if provider == "groq" and not key_value.startswith("gsk_"):
        raise HTTPException(400, "groq keys start with gsk_")
    if provider == "openrouter" and not key_value.startswith("sk-or-"):
        raise HTTPException(400, "openrouter keys start with sk-or-")

    key_id = db.create_api_key(provider, key_value, label or None, priority)

    if env_var_name:
        env_map = {"groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
        resolved = env_var_name or env_map.get(provider, "")
        if resolved:
            sync_key(resolved, key_value)

    return {"id": key_id, "provider": provider, "synced_to_env": bool(env_var_name)}