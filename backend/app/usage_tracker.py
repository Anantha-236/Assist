"""Track provider usage against free-tier limits; auto-suspend at 98%."""

from . import db
from .provider_limits import limits_for

SUSPEND_THRESHOLD = 0.98     # suspend at 98% of daily limit
WARN_THRESHOLD = 0.80        # log a warning at 80%


def check_and_track(
    key_id: str | None,
    provider: str,
    model_id: str,
    tokens_in: int,
    tokens_out: int,
    requests: int = 1,
) -> bool:
    """
    Increment usage and enforce the 98% rule.
    Returns True if the key is still usable, False if it should be skipped.
    If key_id is None (env fallback), tracking is skipped.
    """
    if key_id is None:
        return True

    limits = limits_for(provider, model_id)
    daily_req_limit = limits.get("daily_requests")
    daily_tok_limit = limits.get("daily_tokens")

    # Get current usage before incrementing
    current = db.get_provider_usage(key_id, provider) or {
        "requests": 0, "tokens_in": 0, "tokens_out": 0, "suspended": 0,
    }

    if current.get("suspended"):
        return False

    # Increment
    db.upsert_provider_usage(
        key_id=key_id,
        provider=provider,
        model_id=model_id,
        add_requests=requests,
        add_tokens_in=tokens_in,
        add_tokens_out=tokens_out,
    )

    # Re-fetch after increment
    updated = db.get_provider_usage(key_id, provider) or current
    new_req = updated["requests"]
    new_tok = updated["tokens_in"] + updated["tokens_out"]

    # Check request limit
    if daily_req_limit and new_req >= daily_req_limit * SUSPEND_THRESHOLD:
        print(
            f"[tracker] {provider}/{model_id} key {key_id[:8]} → "
            f"{new_req}/{daily_req_limit} requests "
            f"({new_req/daily_req_limit*100:.0f}%) — SUSPENDING"
        )
        db.suspend_key_for_today(key_id, provider)
        return False

    # Check token limit
    if daily_tok_limit and new_tok >= daily_tok_limit * SUSPEND_THRESHOLD:
        print(
            f"[tracker] {provider}/{model_id} key {key_id[:8]} → "
            f"{new_tok}/{daily_tok_limit} tokens "
            f"({new_tok/daily_tok_limit*100:.0f}%) — SUSPENDING"
        )
        db.suspend_key_for_today(key_id, provider)
        return False

    # Warn at 80%
    if daily_req_limit and new_req >= daily_req_limit * WARN_THRESHOLD:
        pct = new_req / daily_req_limit * 100
        print(f"[tracker] WARN {provider} key {key_id[:8]} at {pct:.0f}% of requests")
    if daily_tok_limit and new_tok >= daily_tok_limit * WARN_THRESHOLD:
        pct = new_tok / daily_tok_limit * 100
        print(f"[tracker] WARN {provider} key {key_id[:8]} at {pct:.0f}% of tokens")

    return True


def key_status_for_dashboard(key_id: str, provider: str) -> dict:
    """Compute usage + limits for the admin UI."""
    limits = limits_for(provider, "")
    usage = db.get_provider_usage(key_id, provider) or {
        "requests": 0, "tokens_in": 0, "tokens_out": 0, "suspended": 0,
    }

    req_limit = limits.get("daily_requests")
    tok_limit = limits.get("daily_tokens")

    req_pct = (usage["requests"] / req_limit * 100) if req_limit else None
    tok_pct = (
        ((usage["tokens_in"] + usage["tokens_out"]) / tok_limit * 100)
        if tok_limit else None
    )

    return {
        "requests": usage["requests"],
        "tokens_in": usage["tokens_in"],
        "tokens_out": usage["tokens_out"],
        "request_limit": req_limit,
        "token_limit": tok_limit,
        "request_pct": round(req_pct, 1) if req_pct is not None else None,
        "token_pct": round(tok_pct, 1) if tok_pct is not None else None,
        "suspended": bool(usage.get("suspended")),
        "suspended_at": usage.get("suspended_at"),
    }