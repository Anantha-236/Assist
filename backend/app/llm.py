
"""LLM streaming client — Groq primary, OpenRouter fallback."""

import json
from typing import AsyncIterator

import httpx

from . import quota
from .config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODEL_FALLBACK,
    GROQ_MODEL_PRIMARY,
    LLM_PROVIDER,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODELS_CHEAP,
    OPENROUTER_MODELS_CODE,
    OPENROUTER_MODELS_FAST,
)

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
# Code detection — requires IMPERATIVE + NOUN (not just a keyword)
# ---------------------------------------------------------------------------

_CODE_STRONG_PHRASES = (
    "write a function", "write a program", "write code", "write me a",
    "write the code", "write a script", "write a method",
    "implement a", "implement the", "implement in",
    "code for", "program to", "function to", "method to",
    "solve this", "solve the", "leetcode", "hackerrank",
    "generate code", "give me code", "show me code",
    "code to", "algorithm to", "pseudo code", "pseudocode",
)

_CODE_IMPERATIVES = {
    "write", "implement", "create", "build", "develop", "generate",
    "design", "program", "solve", "compute", "calculate", "return",
    "print", "define", "code",
}

_CODE_NOUNS = (
    "function", "program", "algorithm", "code", "method", "class",
    "script", "solution", "implementation", "snippet", "regex",
    "pseudocode", "pseudo code", "query",
)

_CODE_ALGO_TERMS = (
    "prime", "fibonacci", "factorial", "palindrome", "fizzbuzz",
    "fizz buzz", "two sum", "linked list", "binary tree", "binary search",
    "hash map", "hashmap", "sort array", "sort list", "reverse string",
    "reverse array", "reverse linked list", "merge sort", "quick sort",
    "bubble sort", "quicksort", "merge sort", "bfs", "dfs",
    "greatest common divisor", " gcd", "lcm", "anagram",
)

_CODE_LANGS = (
    "python", "javascript", "typescript", "java ", "java,", "c++",
    "c#", "golang", "rust", "sql", "bash", "shell", "kotlin",
)


def _is_code_question(q: str) -> bool:
    """Return True only if the question asks for code, not just mentions code terms."""
    if not q:
        return False

    ql = q.lower().strip()

    if any(p in ql for p in _CODE_STRONG_PHRASES):
        return True

    words = set(ql.replace(",", " ").replace(".", " ").split())
    has_imperative = bool(words & _CODE_IMPERATIVES)
    has_noun = any(n in ql for n in _CODE_NOUNS)

    if has_imperative and has_noun:
        return True

    if has_imperative and any(a in ql for a in _CODE_ALGO_TERMS):
        return True

    if has_imperative:
        for verb in (
            "reverse", "sort", "search", "check", "find", "count",
            "compute", "calculate",
        ):
            if verb in words:
                return True

    return False


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
# Groq
# ---------------------------------------------------------------------------

async def _stream_groq(
    question: str, context: str, is_code: bool, profile: dict | None
) -> AsyncIterator[tuple[str, str]]:

    system = SYSTEM_PROMPT_CODE if is_code else SYSTEM_PROMPT_PROSE
    profile_str = json.dumps(profile) if profile else "none"

    messages = [
        {"role": "system", "content": "/no_think"},
        {"role": "system", "content": system + f"\nUser profile: {profile_str}"},
        {"role": "user", "content": f"Context:\n{context}\n\nQ: {question}"},
    ]

    model = GROQ_MODEL_PRIMARY

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 1200 if is_code else 300,
        "temperature": 0.2,
        "stream": True,
    }

    client = _get_groq()

    try:
        async with client.stream(
            "POST", "/chat/completions", json=payload
        ) as resp:

            if resp.status_code != 200:
                body = await resp.aread()

                print(
                    f"[llm] groq {model} HTTP "
                    f"{resp.status_code}: {body[:120]!r}"
                )

                if GROQ_MODEL_FALLBACK and GROQ_MODEL_FALLBACK != model:
                    payload["model"] = GROQ_MODEL_FALLBACK

                    print(
                        f"[llm] groq fallback → {GROQ_MODEL_FALLBACK}"
                    )

                    async with client.stream(
                        "POST", "/chat/completions", json=payload
                    ) as r2:

                        if r2.status_code != 200:
                            b2 = await r2.aread()

                            yield (
                                "error",
                                f"groq fallback HTTP "
                                f"{r2.status_code}: {b2[:160]!r}",
                            )
                            return

                        async for kind, data in _parse_sse(r2):
                            yield (kind, data)

                    return

                yield (
                    "error",
                    f"groq HTTP {resp.status_code}: {body[:160]!r}",
                )
                return

            async for kind, data in _parse_sse(resp):
                yield (kind, data)

    except httpx.ReadTimeout:
        print("[llm] groq READ TIMEOUT — no data in 15s")
        yield ("error", "model stalled on Groq")

    except Exception as e:
        print(f"[llm] groq EXCEPTION {type(e).__name__}: {e}")
        yield ("error", f"{type(e).__name__}")


# ---------------------------------------------------------------------------
# OpenRouter
# ---------------------------------------------------------------------------

async def _stream_openrouter(
    question: str, context: str, is_code: bool, profile: dict | None
) -> AsyncIterator[tuple[str, str]]:

    st = quota.status()

    models = (
        OPENROUTER_MODELS_CHEAP
        if st.get("low")
        else OPENROUTER_MODELS_FAST
    )

    if is_code and OPENROUTER_MODELS_CODE:
        models = OPENROUTER_MODELS_CODE

    if not models:
        yield ("error", "no OpenRouter models configured")
        return

    system = SYSTEM_PROMPT_CODE if is_code else SYSTEM_PROMPT_PROSE
    profile_str = json.dumps(profile) if profile else "none"

    messages = [
        {"role": "system", "content": "/no_think"},
        {"role": "system", "content": system + f"\nUser profile: {profile_str}"},
        {"role": "user", "content": f"Context:\n{context}\n\nQ: {question}"},
    ]

    payload = {
        "models": models,
        "messages": messages,
        "max_tokens": 1200 if is_code else 300,
        "temperature": 0.2,
        "stream": True,
        "provider": {"sort": "latency", "preferred_max_latency": 2},
    }

    client = _get_openrouter()

    async with client.stream(
        "POST", "/chat/completions", json=payload
    ) as resp:

        if resp.status_code == 429:
            quota.note_rate_limit()
            yield ("error", "rate limited (429)")
            return

        if resp.status_code != 200:
            body = await resp.aread()
            yield ("error", f"HTTP {resp.status_code}: {body[:160]!r}")
            return

        async for kind, data in _parse_sse(resp):
            yield (kind, data)


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
# Public entry
# ---------------------------------------------------------------------------

async def stream_answer(
    question: str, context: str, profile: dict | None
) -> AsyncIterator[tuple[str, str]]:
    """Yields ('delta', text) | ('usage', json) | ('done', '') | ('error', msg)."""

    is_code = _is_code_question(question)

    if is_code:
        print(f"[llm] CODE mode: {question[:80]!r}")
    else:
        print(f"[llm] PROSE mode: {question[:80]!r}")

    if (
        LLM_PROVIDER == "groq"
        and GROQ_API_KEY
        and GROQ_API_KEY.startswith("gsk_")
    ):
        last_kind = None

        async for kind, data in _stream_groq(
            question, context, is_code, profile
        ):
            last_kind = kind
            yield (kind, data)

            if kind == "done":
                return

        if last_kind == "error" and OPENROUTER_API_KEY:
            print("[llm] groq failed, falling back to OpenRouter")

            async for kind, data in _stream_openrouter(
                question, context, is_code, profile
            ):
                yield (kind, data)

        return

    async for kind, data in _stream_openrouter(
        question, context, is_code, profile
    ):
        yield (kind, data)
