"""LLM streaming client — Groq primary, OpenRouter fallback, header-tracked."""

import json
from typing import AsyncIterator

import httpx

from . import quota
from .config import (
    GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL_FALLBACK, GROQ_MODEL_PRIMARY,
    LLM_PROVIDER, OPENROUTER_API_KEY, OPENROUTER_BASE_URL,
    OPENROUTER_MODELS_CHEAP, OPENROUTER_MODELS_CODE, OPENROUTER_MODELS_FAST,
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
    "RULES: (1) Never refuse. (2) Never apologize. "
    "(3) Output: one short sentence, then a fenced block. "
    "(4) Inside the block: working code. (5) If ambiguous, pick the common interpretation. "
    "Default to Python if unspecified."
)

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
    "bubble sort", "quicksort", "bfs", "dfs",
    "greatest common divisor", " gcd", "lcm", "anagram",
)


def _is_code_question(q: str) -> bool:
    if not q:
        return False
    ql = q.lower().strip()

    if any(t.startswith(p) for p in ("what is ", "what are ", "define ", "meaning of ")):
        words = ql.split()
        if not any(v in words[:3] for v in _CODE_IMPERATIVES):
            return False

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
        for verb in ("reverse", "sort", "search", "check", "find", "count",
                     "compute", "calculate"):
            if verb in words:
                return True
    return False


_groq_client: httpx.AsyncClient | None = None
_or_client: httpx.AsyncClient | None = None


def _get_groq() -> httpx.AsyncClient:
    global _groq_client
    if _groq_client is None:
        _groq_client = httpx.AsyncClient(
            base_url=GROQ_BASE_URL,
            timeout=httpx.Timeout(25.0, connect=5.0, read=15.0),
            http2=True,
        )
    return _groq_client


def _get_openrouter() -> httpx.AsyncClient:
    global _or_client
    if _or_client is None:
        _or_client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            timeout=httpx.Timeout(25.0, connect=5.0, read=15.0),
            headers={"HTTP-Referer": "https://assist.local", "X-Title": "Assist"},
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


def _fallback_key(provider):
    if provider == "groq" and GROQ_API_KEY and GROQ_API_KEY.startswith("gsk_"):
        return GROQ_API_KEY
    if provider == "openrouter" and OPENROUTER_API_KEY:
        return OPENROUTER_API_KEY
    return None


def _profile_to_natural(p):
    if not p:
        return "No profile set. Give a generic but safe answer."
    parts = []
    role = p.get("role") or p.get("target_role")
    exp = p.get("experience")
    if role and exp:
        parts.append(f"Interviewing as {role} with {exp} of experience.")
    elif role:
        parts.append(f"Interviewing as {role}.")
    if p.get("skills"):
        parts.append(f"Core skills: {p['skills']}.")
    if p.get("company"):
        parts.append(f"Currently at {p['company']}.")
    if p.get("achievements"):
        parts.append(f"Achievements: {p['achievements']}")
    if p.get("projects"):
        parts.append(f"Projects: {p['projects']}")
    if p.get("target_salary"):
        parts.append(f"Salary target: {p['target_salary']}")
    if p.get("notice_period"):
        parts.append(f"Notice period: {p['notice_period']}")
    style = (p.get("answer_style") or "").lower()
    if "star" in style:
        parts.append("Use STAR format for behavioral questions.")
    return "\n".join(parts) if parts else "No profile set."


def _build_system_prompt(is_code, profile):
    if is_code:
        base = SYSTEM_PROMPT_CODE
    else:
        base = (
            "You are a silent meeting assistant helping the user during a live interview. "
            "Answer in FIRST PERSON as the user. Reference their specific skills and "
            "achievements from the profile below. Max 2 sentences for factual, up to 4 "
            "for behavioral. Never refuse. Never invent facts not in the profile."
        )
    return base + "\n\nUSER PROFILE:\n" + _profile_to_natural(profile)


async def _parse_sse(resp):
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
        d = choices[0].get("delta") or {}
        content = d.get("content") or ""
        reasoning = d.get("reasoning") or d.get("reasoning_content") or ""
        if reasoning and not content:
            print(f"[llm] reasoning chunk (skipped): {reasoning[:40]!r}")
        if content:
            yield ("delta", content)
    yield ("done", "")


async def _rotate_groq(question, context, is_code, profile, classification=None):
    from . import db, router

    if classification is None:
        from .classifier import classify
        classification = classify(question)

    chosen = router.select_model(classification, force_provider="groq")
    if not chosen:
        yield ("error", "no Groq model for this tier")
        return
    model_id = chosen["model_id"]

    keys = db.get_active_keys("groq")
    if not keys:
        env = _fallback_key("groq")
        if env:
            keys = [{"id": None, "key_value": env, "label": ".env"}]
        else:
            yield ("error", "no Groq keys")
            return

    system = _build_system_prompt(is_code, profile)
    messages = [
        {"role": "system", "content": "/no_think"},
        {"role": "system", "content": system},
        {"role": "user", "content": f"Conversation:\n{context}\n\nQuestion: {question}"},
    ]
    payload = {"model": model_id, "messages": messages,
               "max_tokens": 1200 if is_code else 350,
               "temperature": 0.3, "stream": True}
    client = _get_groq()

    for k in keys:
        key_id = k["id"]
        key_val = k["key_value"]
        label = k.get("label") or (key_id[:8] if key_id else "env")

        if key_id and db.is_key_suspended(key_id, "groq"):
            print(f"[llm] groq {label} suspended, skipping")
            continue

        try:
            async with client.stream(
                "POST", "/chat/completions",
                headers={"Authorization": f"Bearer {key_val}"},
                json=payload,
            ) as resp:
                if resp.status_code in (401, 403, 429) or resp.status_code >= 500:
                    print(f"[llm] groq {label} → HTTP {resp.status_code}")
                    if key_id:
                        db.mark_key_failure(key_id)
                    continue
                if resp.status_code != 200:
                    body = await resp.aread()
                    print(f"[llm] groq {label}: {body[:120]!r}")
                    if key_id:
                        db.mark_key_failure(key_id)
                    continue

                if key_id:
                    db.mark_key_success(key_id)
                    db.update_live_quota(key_id, "groq", dict(resp.headers))

                async for kind, data in _parse_sse(resp):
                    if kind == "usage":
                        try:
                            u = json.loads(data)
                            from .usage_tracker import check_and_track
                            check_and_track(
                                key_id=key_id, provider="groq", model_id=model_id,
                                tokens_in=int(u.get("prompt_tokens", 0) or 0),
                                tokens_out=int(u.get("completion_tokens", 0) or 0),
                            )
                            yield ("usage_meta", json.dumps({
                                "api_key_id": key_id, "provider": "groq",
                                "model": model_id, "usage": u,
                                "classification": classification,
                            }))
                        except Exception:
                            pass
                    yield (kind, data)
                return
        except httpx.ReadTimeout:
            print(f"[llm] groq {label} read timeout")
            if key_id:
                db.mark_key_failure(key_id)
            continue
        except Exception as e:
            print(f"[llm] groq {label}: {type(e).__name__}: {e}")
            if key_id:
                db.mark_key_failure(key_id)
            continue

    yield ("error", "all Groq keys failed")


async def _rotate_openrouter(question, context, is_code, profile, classification=None):
    from . import db, router

    if classification is None:
        from .classifier import classify
        classification = classify(question)

    chosen = router.select_model(classification, force_provider="openrouter")
    if not chosen:
        yield ("error", "no OpenRouter model for this tier")
        return
    model_id = chosen["model_id"]

    keys = db.get_active_keys("openrouter")
    if not keys:
        env = _fallback_key("openrouter")
        if env:
            keys = [{"id": None, "key_value": env, "label": ".env"}]
        else:
            yield ("error", "no OpenRouter keys")
            return

    system = _build_system_prompt(is_code, profile)
    messages = [
        {"role": "system", "content": "/no_think"},
        {"role": "system", "content": system},
        {"role": "user", "content": f"Conversation:\n{context}\n\nQuestion: {question}"},
    ]
    payload = {"model": model_id, "messages": messages,
               "max_tokens": 1200 if is_code else 350,
               "temperature": 0.3, "stream": True}
    client = _get_openrouter()

    for k in keys:
        key_id = k["id"]
        key_val = k["key_value"]
        label = k.get("label") or (key_id[:8] if key_id else "env")

        if key_id and db.is_key_suspended(key_id, "openrouter"):
            print(f"[llm] OR {label} suspended, skipping")
            continue

        try:
            async with client.stream(
                "POST", "/chat/completions",
                headers={"Authorization": f"Bearer {key_val}"},
                json=payload,
            ) as resp:
                if resp.status_code == 429:
                    quota.note_rate_limit()
                    print(f"[llm] OR {label} → 429")
                    if key_id:
                        db.mark_key_failure(key_id)
                    continue
                if resp.status_code in (401, 403) or resp.status_code >= 500:
                    print(f"[llm] OR {label} → HTTP {resp.status_code}")
                    if key_id:
                        db.mark_key_failure(key_id)
                    continue
                if resp.status_code != 200:
                    body = await resp.aread()
                    print(f"[llm] OR {label}: {body[:120]!r}")
                    if key_id:
                        db.mark_key_failure(key_id)
                    continue

                if key_id:
                    db.mark_key_success(key_id)
                    db.update_live_quota(key_id, "openrouter", dict(resp.headers))

                async for kind, data in _parse_sse(resp):
                    if kind == "usage":
                        try:
                            u = json.loads(data)
                            from .usage_tracker import check_and_track
                            check_and_track(
                                key_id=key_id, provider="openrouter", model_id=model_id,
                                tokens_in=int(u.get("prompt_tokens", 0) or 0),
                                tokens_out=int(u.get("completion_tokens", 0) or 0),
                            )
                            yield ("usage_meta", json.dumps({
                                "api_key_id": key_id, "provider": "openrouter",
                                "model": model_id, "usage": u,
                                "classification": classification,
                            }))
                        except Exception:
                            pass
                    yield (kind, data)
                return
        except httpx.ReadTimeout:
            print(f"[llm] OR {label} read timeout")
            if key_id:
                db.mark_key_failure(key_id)
            continue
        except Exception as e:
            print(f"[llm] OR {label}: {type(e).__name__}: {e}")
            if key_id:
                db.mark_key_failure(key_id)
            continue

    yield ("error", "all OpenRouter keys failed")


async def stream_answer(question, context, profile):
    from .classifier import classify
    classification = classify(question)
    is_code = classification["intent"] == "code"
    print(f"[llm] {classification['reason']} → tier {classification['required_tier']}")

    last = None
    if LLM_PROVIDER == "groq":
        async for kind, data in _rotate_groq(question, context, is_code, profile, classification):
            last = kind
            yield (kind, data)
            if kind == "done":
                return
        if last == "error":
            print("[llm] groq exhausted, falling back to OpenRouter")
            async for kind, data in _rotate_openrouter(question, context, is_code, profile, classification):
                yield (kind, data)
        return

    async for kind, data in _rotate_openrouter(question, context, is_code, profile, classification):
        yield (kind, data)