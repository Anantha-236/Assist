"""OpenRouter quota tracking. Degrades gracefully with demo keys."""

import time

import httpx

from .config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    QUOTA_REFRESH_SEC,
    QUOTA_WARN_FRACTION,
)

_cache = {"used": None, "limit": None, "remaining": None, "checked_at": 0.0}


def _is_demo_key() -> bool:
    return not OPENROUTER_API_KEY or "DEMO" in OPENROUTER_API_KEY


def _refresh():
    if _is_demo_key():
        _cache["checked_at"] = time.time()
        return
    try:
        r = httpx.get(
            f"{OPENROUTER_BASE_URL}/key",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            timeout=5.0,
        )
        if r.status_code != 200:
            _cache["checked_at"] = time.time()
            return
        data = r.json().get("data", {})
        fm = data.get("free_model_daily_requests") or {}
        _cache["used"] = fm.get("used")
        _cache["limit"] = fm.get("limit")
        _cache["remaining"] = fm.get("remaining")
        _cache["checked_at"] = time.time()
    except Exception as e:
        print(f"[quota] refresh failed: {e}")
        _cache["checked_at"] = time.time()


def status() -> dict:
    if _is_demo_key():
        return {
            "available": False,
            "reason": "demo or missing API key",
            "used": None,
            "limit": None,
            "remaining": None,
            "fraction_left": None,
            "low": False,
        }
    if time.time() - _cache["checked_at"] > QUOTA_REFRESH_SEC:
        _refresh()
    rem, lim = _cache["remaining"], _cache["limit"]
    if rem is None or not lim:
        return {
            "available": False,
            "reason": "not yet fetched",
            "used": None, "limit": None, "remaining": None,
            "fraction_left": None, "low": False,
        }
    frac = rem / lim
    return {
        "available": True,
        "used": _cache["used"],
        "limit": lim,
        "remaining": rem,
        "fraction_left": frac,
        "low": frac < QUOTA_WARN_FRACTION,
    }


def note_rate_limit():
    _cache["checked_at"] = 0.0