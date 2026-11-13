"""Sync API keys to environment — .env locally, Render API in production."""

import os
from pathlib import Path

import httpx

RENDER_API_BASE = "https://api.render.com/v1"


def _is_render():
    return os.environ.get("RENDER") == "true"


def _write_local_env(key, value):
    try:
        from dotenv import set_key
    except ImportError:
        print("[env] python-dotenv missing")
        return
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        env_path.touch()
    set_key(str(env_path), key, value)
    try:
        from dotenv import load_dotenv
        load_dotenv(str(env_path), override=True)
    except Exception:
        pass
    print(f"[env] wrote {key} to {env_path}")


def _write_render_env(key, value):
    api_key = os.environ.get("RENDER_API_KEY", "")
    service_id = os.environ.get("RENDER_SERVICE_ID", "")
    if not api_key or not service_id:
        print("[env] RENDER_API_KEY or RENDER_SERVICE_ID missing")
        return

    r = httpx.put(
        f"{RENDER_API_BASE}/services/{service_id}/env-vars/{key}",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"value": value},
        timeout=15.0,
    )
    if r.status_code not in (200, 201):
        print(f"[env] render update failed: HTTP {r.status_code} {r.text[:120]}")
        return

    d = httpx.post(
        f"{RENDER_API_BASE}/services/{service_id}/deploys",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15.0,
    )
    print(f"[env] render env '{key}' updated, deploy triggered ({d.status_code})")


def sync_key(env_name, value):
    if _is_render():
        _write_render_env(env_name, value)
    else:
        _write_local_env(env_name, value)