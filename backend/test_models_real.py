"""Test models with the ACTUAL system prompt the app uses.

A model that passes this will work in production. A model that fails here
will leave the overlay empty no matter how fast it responds to 'Say OK'.
"""

import asyncio
import json

import httpx

from app.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL

# The exact system prompt the app sends
SYSTEM_PROMPT = (
    "You are a silent meeting assistant. Answer in first person as the user. "
    "Max 2 sentences. No preamble, no 'Sure', no markdown. "
    "If unclear, give a short best guess — never ask for clarification."
)

# A realistic interview question with context
CONTEXT = (
    "Q: Could you tell me about yourself?\n"
    "A: I'm a recent graduate in hospital management from Chennai.\n"
    "Q: Do you know your roles and responsibilities?"
)
QUESTION = "Yes ma'am, I do. What would you like me to walk through first?"

CANDIDATES = [
    "nvidia/nemotron-3.5-super-vl:free",
    "baidu/ernie-5.5-flash-preview:free",
    "cohere/north-mini-code:free",
    "dots-studio/dots-3-note-preview:free",
    "recursive/flint-v1.0:free",
]


async def test(client: httpx.AsyncClient, model: str) -> dict:
    r = {
        "model": model, "status": None,
        "content_tokens": 0, "reasoning_tokens": 0,
        "content": "", "first_content_s": None, "error": None,
    }
    t0 = asyncio.get_event_loop().time()
    try:
        async with client.stream(
            "POST",
            "/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",
                     "content": f"Context:\n{CONTEXT}\n\nQ: {QUESTION}"},
                ],
                "max_tokens": 300,
                "stream": True,
            },
        ) as resp:
            r["status"] = resp.status_code
            if resp.status_code != 200:
                body = await resp.aread()
                r["error"] = body[:200].decode("utf-8", "ignore")
                return r
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    j = json.loads(data)
                except Exception:
                    continue
                ch = (j.get("choices") or [{}])[0].get("delta") or {}
                c = ch.get("content") or ""
                rs = ch.get("reasoning") or ch.get("reasoning_content") or ""
                if rs:
                    r["reasoning_tokens"] += 1
                if c:
                    r["content_tokens"] += 1
                    if r["first_content_s"] is None:
                        r["first_content_s"] = asyncio.get_event_loop().time() - t0
                    if len(r["content"]) < 200:
                        r["content"] += c
    except Exception as e:
        r["error"] = f"{type(e).__name__}: {e}"
    return r


async def main():
    async with httpx.AsyncClient(
        base_url=OPENROUTER_BASE_URL,
        timeout=httpx.Timeout(45.0, connect=5.0),
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
    ) as client:
        winners = []
        for m in CANDIDATES:
            print(f"\n=== {m} ===")
            r = await test(client, m)
            if r["status"] != 200:
                print(f"  ❌ HTTP {r['status']}: {r['error'][:120]}")
                continue
            print(f"  content tokens:   {r['content_tokens']}")
            print(f"  reasoning tokens: {r['reasoning_tokens']}")
            if r["first_content_s"]:
                print(f"  first content:    {r['first_content_s']:.2f}s")
            if r["content"]:
                print(f"  reply: {r['content'][:150]!r}")
            if r["content_tokens"] > 0 and r["reasoning_tokens"] < r["content_tokens"] * 3:
                print(f"  ✅ USABLE — produces content without over-reasoning")
                winners.append((m, r["first_content_s"] or 999))
            elif r["content_tokens"] == 0:
                print(f"  ❌ UNUSABLE — reasoning only, no visible content")
            else:
                print(f"  ⚠️  MAYBE — produces content but reasons a lot")

        print("\n" + "=" * 60)
        print("RANKED WINNERS (usable models, fastest first):")
        print("=" * 60)
        winners.sort(key=lambda x: x[1])
        for m, t in winners:
            print(f"  {t:.2f}s  {m}")
        if not winners:
            print("  NONE — see notes below")


if __name__ == "__main__":
    asyncio.run(main())
    