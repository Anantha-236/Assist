"""Static free-tier limits per provider. Update as providers change.

All values are the DAILY ceiling for the free tier.
Monthly limits are expressed as a daily equivalent where relevant.
"""

# Each entry: (daily_requests, daily_tokens, rpm)
# None means "unlimited at this dimension" (still rate-limited per-minute)

PROVIDER_LIMITS = {
    "groq": {
        "llama-3.1-8b-instant": {
            "daily_requests": 14_400,
            "daily_tokens": 500_000,
            "rpm": 30,
            "reset_utc": False,  # Groq resets ~midnight UTC, but not strictly enforced
        },
        "openai/gpt-oss-20b": {
            "daily_requests": 1_000,
            "daily_tokens": 200_000,
            "rpm": 30,
        },
        "openai/gpt-oss-120b": {
            "daily_requests": 1_000,
            "daily_tokens": 200_000,
            "rpm": 30,
        },
        "qwen/qwen3.8-27b": {
            "daily_requests": 1_000,
            "daily_tokens": 200_000,
            "rpm": 30,
        },
    },
    "openrouter": {
        "_default": {
            "daily_requests": 50,       # 1,000 if lifetime top-up >= $10
            "daily_tokens": None,       # token cap depends on model
            "rpm": 20,
            "note": "Raises to 1,000 RPD after a one-time $10 credit purchase",
        },
    },
    "cerebras": {
        "_default": {
            "daily_requests": None,     # no hard RPD published
            "daily_tokens": 1_000_000,
            "rpm": 5,
            "tpm": 30_000,
        },
    },
    "cohere": {
        "_default": {
            "daily_requests": 33,       # 1,000/month ÷ 30
            "daily_tokens": None,
            "rpm": 20,
            "monthly_requests": 1_000,
            "note": "Trial key: 1,000 calls/month, resets monthly",
        },
    },
    "mistral": {
        "_default": {
            "daily_requests": None,
            "daily_tokens": 33_000_000, # 1B/month ÷ 30
            "rpm": 60,                  # ~1 req/sec
            "monthly_tokens": 1_000_000_000,
        },
    },
    "sambanova": {
        "_default": {
            "daily_requests": 20,
            "daily_tokens": 200_000,
            "rpm": 20,
        },
    },
    "cloudflare": {
        "_default": {
            "daily_requests": None,
            "daily_tokens": None,
            "daily_neurons": 10_000,
            "rpm": None,
            "note": "Billed in Neurons, not tokens; ≈314K input tokens on GPT-OSS-120B",
        },
    },
    "gemini": {
        "_default": {
            "daily_requests": None,     # unpublished since 2026
            "daily_tokens": None,
            "rpm": 10,
            "note": "Limits shown only in AI Studio; daily reset midnight PT",
        },
    },
}


def limits_for(provider: str, model_id: str) -> dict:
    """Return limits for a specific provider+model, falling back to _default."""
    p = PROVIDER_LIMITS.get(provider, {})
    if model_id in p:
        return p[model_id]
    if "_default" in p:
        return p["_default"]
    return {
        "daily_requests": None,
        "daily_tokens": None,
        "rpm": None,
    }