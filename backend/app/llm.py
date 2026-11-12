
"""LLM streaming client — Router-based Groq primary, OpenRouter fallback."""

import json
from typing import AsyncIterator

import httpx

from . import quota
from .config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    LLM_PROVIDER,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
)
from .usage_tracker import check_and_track


SYSTEM_PROMPT_PROSE = (
    "You are a silent meeting assistant. Answer in first person as the user. "
    "Max 2 sentences. No preamble, no 'Sure', no markdown. "
    "If unclear, give a short best guess — never ask for clarification."
)

SYSTEM_PROMPT_CODE = (
    "You are a coding copilot in a live technical interview. "
    "The user is the candidate; the answer goes on their screen verbatim. "
    "ALWAYS produce a complete, runnable, fenced code block that solves the problem. "
    "RULES: "
    "(1) Never refuse. Never say 'I can't', 'as an AI', 'I'm unable to'. "
    "(2) Never apologize. Never write disclaimers. "
    "(3) Output format: one short sentence, then a fenced block "
    "(```python ... ``` or ```javascript ... ``` etc.). "
    "(4) Inside the block: working code with minimal comments. "
    "(5) If the prompt is ambiguous, pick the most common interpretation and code it. "
    "If you have no preference, default to Python."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_system_prompt(is_code: bool, profile: dict | None) -> str:
    system = SYSTEM_PROMPT_CODE if is_code else SYSTEM_PROMPT_PROSE
    profile_str = json.dumps(profile) if profile else "none"
    return system + f"\nUser profile: {profile_str}"


def _fallback_key(provider: str) -> str | None:
    """Get the provider API key from environment configuration."""
    if provider == "groq":
        return GROQ_API_KEY

    if provider == "openrouter":
        return OPENROUTER_API_KEY

    return None


# ---------------------------------------------------------------------------
# HTTP clients
# ---------------------------------------------------------------------------

_groq_client: httpx.AsyncClient | None = None
_or_client: httpx.AsyncClient | None = None


def _get_groq() -> httpx.AsyncClient:
    global _groq_client

    if _groq_client is None:
        _groq_client = httpx.AsyncClient(
            base_url=GROQ_BASE_URL,
            timeout=httpx.Timeout(25.0, connect=5.0, read=15.0),
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            http2=True,
        )

    return _groq_client


def _get_openrouter() -> httpx.AsyncClient:
    global _or_client

    if _or_client is None:
        _or_client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            timeout=httpx.Timeout(25.0, connect=5.0, read=15.0),
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://assist.local",
                "X-Title": "Assist",
            },
            http2=True,
        )

    return _or_client


async def close_client():
    global _groq_client, _or_client

    if _groq_client is not None:
        await _groq_client.aclose()
        _groq_client = None

    if _or_client is not None:
        await _or_client.aclose()
        _or_client = None


# ---------------------------------------------------------------------------
# Groq — Router-based model selection + API key rotation
# ---------------------------------------------------------------------------

async def _rotate_groq(
    question: str,
    context: str,
    is_code: bool,
    profile: dict | None,
    classification: dict | None = None,
) -> AsyncIterator[tuple[str, str]]:

    from . import db, router

    # Classify if not provided.
    if classification is None:
        from .classifier import classify
        classification = classify(question)

    # Select the cheapest Groq model meeting the required tier.
    chosen = router.select_model(
        classification,
        force_provider="groq",
    )

    if not chosen:
        yield ("error", "no Groq model available for this tier")
        return

    model_id = chosen["model_id"]

    print(
        f"[llm] groq → {model_id} ({chosen['reason']})"
    )

    # Load active API keys.
    keys = db.get_active_keys("groq")

    if not keys:
        env_key = _fallback_key("groq")

        if env_key:
            keys = [
                {
                    "id": None,
                    "key_value": env_key,
                    "label": ".env",
                }
            ]
        else:
            yield ("error", "no Groq API keys configured")
            return

    system = _build_system_prompt(is_code, profile)

    messages = [
        {"role": "system", "content": "/no_think"},
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"Conversation:\n{context}\n\nQuestion: {question}",
        },
    ]

    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 1200 if is_code else 350,
        "temperature": 0.3,
        "stream": True,
    }

    client = _get_groq()

    for k in keys:
        key_id = k["id"]
        key_val = k["key_value"]
        label = k.get("label") or (
            key_id[:8] if key_id else "env"
        )

        # Skip keys suspended for today.
        if key_id and db.is_key_suspended(key_id, "groq"):
            print(
                f"[llm] groq key {label} → "
                "suspended today, skipping"
            )
            continue

        try:
            async with client.stream(
                "POST",
                "/chat/completions",
                headers={
                    "Authorization": f"Bearer {key_val}"
                },
                json=payload,
            ) as resp:

                if (
                    resp.status_code in (401, 403, 429)
                    or resp.status_code >= 500
                ):
                    print(
                        f"[llm] groq key {label} → "
                        f"HTTP {resp.status_code}, trying next"
                    )

                    if key_id:
                        db.mark_key_failure(key_id)

                    continue

                if resp.status_code != 200:
                    body = await resp.aread()

                    print(
                        f"[llm] groq key {label} → "
                        f"HTTP {resp.status_code}: {body[:120]!r}"
                    )

                    if key_id:
                        db.mark_key_failure(key_id)

                    continue

                if key_id:
                    db.mark_key_success(key_id)

                async for kind, data in _parse_sse(resp):

                    if kind == "usage":
                        try:
                            usage = json.loads(data)

                            # Track provider usage against free-tier limits.
                            check_and_track(
                                key_id=key_id,
                                provider="groq",
                                model_id=model_id,
                                tokens_in=int(
                                    usage.get("prompt_tokens", 0) or 0
                                ),
                                tokens_out=int(
                                    usage.get("completion_tokens", 0) or 0
                                ),
                            )

                            yield (
                                "usage_meta",
                                json.dumps({
                                    "api_key_id": key_id,
                                    "provider": "groq",
                                    "model": model_id,
                                    "usage": usage,
                                    "classification": classification,
                                }),
                            )

                        except Exception as e:
                            print(
                                f"[llm] groq usage tracking error: "
                                f"{type(e).__name__}: {e}"
                            )

                    yield (kind, data)

                return

        except httpx.ReadTimeout:
            print(
                f"[llm] groq key {label} → "
                "read timeout, trying next"
            )

            if key_id:
                db.mark_key_failure(key_id)

            continue

        except Exception as e:
            print(
                f"[llm] groq key {label} → "
                f"exception {type(e).__name__}: {e}"
            )

            if key_id:
                db.mark_key_failure(key_id)

            continue

    yield ("error", "all Groq keys failed")


# ---------------------------------------------------------------------------
# OpenRouter — Router-based model selection + API key rotation
# ---------------------------------------------------------------------------

async def _rotate_openrouter(
    question: str,
    context: str,
    is_code: bool,
    profile: dict | None,
    classification: dict | None = None,
) -> AsyncIterator[tuple[str, str]]:

    from . import db, router

    # Classify if not provided.
    if classification is None:
        from .classifier import classify
        classification = classify(question)

    chosen = router.select_model(
        classification,
        force_provider="openrouter",
    )

    if not chosen:
        yield (
            "error",
            "no OpenRouter model available for this tier",
        )
        return

    model_id = chosen["model_id"]

    print(
        f"[llm] openrouter → {model_id} ({chosen['reason']})"
    )

    # Load active API keys.
    keys = db.get_active_keys("openrouter")

    if not keys:
        env_key = _fallback_key("openrouter")

        if env_key:
            keys = [
                {
                    "id": None,
                    "key_value": env_key,
                    "label": ".env",
                }
            ]
        else:
            yield (
                "error",
                "no OpenRouter API keys configured",
            )
            return

    system = _build_system_prompt(is_code, profile)

    messages = [
        {"role": "system", "content": "/no_think"},
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"Conversation:\n{context}\n\nQuestion: {question}",
        },
    ]

    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 1200 if is_code else 350,
        "temperature": 0.3,
        "stream": True,
    }

    client = _get_openrouter()

    for k in keys:
        key_id = k["id"]
        key_val = k["key_value"]
        label = k.get("label") or (
            key_id[:8] if key_id else "env"
        )

        # Skip keys suspended for today.
        if key_id and db.is_key_suspended(key_id, "openrouter"):
            print(
                f"[llm] OR key {label} → "
                "suspended today, skipping"
            )
            continue

        try:
            async with client.stream(
                "POST",
                "/chat/completions",
                headers={
                    "Authorization": f"Bearer {key_val}"
                },
                json=payload,
            ) as resp:

                if resp.status_code == 429:
                    quota.note_rate_limit()

                    print(
                        f"[llm] OR key {label} → "
                        "429, trying next"
                    )

                    if key_id:
                        db.mark_key_failure(key_id)

                    continue

                if (
                    resp.status_code in (401, 403)
                    or resp.status_code >= 500
                ):
                    print(
                        f"[llm] OR key {label} → "
                        f"HTTP {resp.status_code}, trying next"
                    )

                    if key_id:
                        db.mark_key_failure(key_id)

                    continue

                if resp.status_code != 200:
                    body = await resp.aread()

                    print(
                        f"[llm] OR key {label} → "
                        f"HTTP {resp.status_code}: {body[:120]!r}"
                    )

                    if key_id:
                        db.mark_key_failure(key_id)

                    continue

                if key_id:
                    db.mark_key_success(key_id)

                async for kind, data in _parse_sse(resp):

                    if kind == "usage":
                        try:
                            usage = json.loads(data)

                            # Track provider usage against free-tier limits.
                            check_and_track(
                                key_id=key_id,
                                provider="openrouter",
                                model_id=model_id,
                                tokens_in=int(
                                    usage.get("prompt_tokens", 0) or 0
                                ),
                                tokens_out=int(
                                    usage.get("completion_tokens", 0) or 0
                                ),
                            )

                            yield (
                                "usage_meta",
                                json.dumps({
                                    "api_key_id": key_id,
                                    "provider": "openrouter",
                                    "model": model_id,
                                    "usage": usage,
                                    "classification": classification,
                                }),
                            )

                        except Exception as e:
                            print(
                                f"[llm] OpenRouter usage tracking error: "
                                f"{type(e).__name__}: {e}"
                            )

                    yield (kind, data)

                return

        except httpx.ReadTimeout:
            print(
                f"[llm] OR key {label} → "
                "read timeout, trying next"
            )

            if key_id:
                db.mark_key_failure(key_id)

            continue

        except Exception as e:
            print(
                f"[llm] OR key {label} → "
                f"exception {type(e).__name__}: {e}"
            )

            if key_id:
                db.mark_key_failure(key_id)

            continue

    yield ("error", "all OpenRouter keys failed")


# ---------------------------------------------------------------------------
# SSE parsing
# ---------------------------------------------------------------------------

async def _parse_sse(
    resp: httpx.Response,
) -> AsyncIterator[tuple[str, str]]:

    async for line in resp.aiter_lines():

        if not line.startswith("data: "):
            continue

        data = line[6:].strip()

        if data == "[DONE]":
            yield ("done", "")
            return

        try:
            j = json.loads(data)
        except json.JSONDecodeError:
            continue

        usage = j.get("usage")

        if usage:
            yield ("usage", json.dumps(usage))

        choices = j.get("choices") or []

        if not choices:
            if j.get("error"):
                yield ("error", str(j["error"])[:200])
            continue

        delta = choices[0].get("delta") or {}
        content = delta.get("content") or ""

        reasoning = (
            delta.get("reasoning")
            or delta.get("reasoning_content")
            or ""
        )

        if reasoning and not content:
            print(
                f"[llm] reasoning chunk (skipped): {reasoning[:40]!r}"
            )

        if content:
            yield ("delta", content)

    yield ("done", "")


# ---------------------------------------------------------------------------
# Public entry — classify once and pass classification to router
# ---------------------------------------------------------------------------

async def stream_answer(
    question: str,
    context: str,
    profile: dict | None,
) -> AsyncIterator[tuple[str, str]]:
    """Stream model output using router-based model selection."""

    from .classifier import classify

    classification = classify(question)

    is_code = classification["intent"] == "code"

    print(
        f"[llm] {classification['reason']} "
        f"→ tier {classification['required_tier']}"
    )

    last_kind = None

    if LLM_PROVIDER == "groq":

        async for kind, data in _rotate_groq(
            question,
            context,
            is_code,
            profile,
            classification,
        ):
            last_kind = kind
            yield (kind, data)

            if kind == "done":
                return

        if last_kind == "error":
            print(
                "[llm] groq exhausted, falling back to OpenRouter"
            )

            async for kind, data in _rotate_openrouter(
                question,
                context,
                is_code,
                profile,
                classification,
            ):
                yield (kind, data)

        return

    async for kind, data in _rotate_openrouter(
        question,
        context,
        is_code,
        profile,
        classification,
    ):
        yield (kind, data)
