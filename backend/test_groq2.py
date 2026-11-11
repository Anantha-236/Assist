"""Test the two real chat models on Groq, including Qwen3 thinking-off mode."""

import asyncio
import json

import httpx

from app.config import GROQ_API_KEY, GROQ_BASE_URL

SYSTEM = (
    "You are a silent meeting assistant. Answer in first person as the user. "
    "Max 2 sentences. No preamble."
)
CTX = "Q: Could you tell me about yourself?\nA: I'm a recent graduate."
QUESTION = "What would you like me to walk through first?"


async def test(label, model, extra_messages=None, extra_body=None):
    print(f"\n=== {label} ===")
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Context:\n{CTX}\n\nQ: {QUESTION}"},
    ]
    if extra_messages:
        messages = extra_messages + messages

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 300,
        "stream": True,
    }
    if extra_body:
        payload.update(extra_body)

    async with httpx.AsyncClient(
        base_url=GROQ_BASE_URL,
        timeout=httpx.Timeout(30.0, connect=5.0),
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
    ) as client:
        try:
            async with client.stream(
                "POST", "/chat/completions", json=payload
            ) as resp:
                print(f"  status: {resp.status_code}")
                if resp.status_code != 200:
                    body = await resp.aread()
                    print(f"  error: {body[:300]!r}")
                    return
                content = 0
                reasoning = 0
                out = ""
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    d = line[6:].strip()
                    if d == "[DONE]":
                        break
                    try:
                        j = json.loads(d)
                    except Exception:
                        continue
                    ch = (j.get("choices") or [{}])[0].get("delta") or {}
                    c = ch.get("content") or ""
                    r = ch.get("reasoning") or ch.get("reasoning_content") or ""
                    if r:
                        reasoning += 1
                    if c:
                        content += 1
                        out += c
                print(f"  content tokens:   {content}")
                print(f"  reasoning tokens: {reasoning}")
                if out:
                    print(f"  reply: {out[:150]!r}")
                if content > 0 and reasoning < content * 2:
                    print(f"  ✅ USABLE")
                elif content > 0:
                    print(f"  ⚠️  Content but heavy reasoning")
                else:
                    print(f"  ❌ No content")
        except Exception as e:
            print(f"  EXCEPTION: {type(e).__name__}: {e}")


async def main():
    # Qwen3 — test with thinking explicitly disabled
    await test(
        "Qwen3.8-27b (thinking off via /no_think)",
        "qwen/qwen3.8-27b",
        extra_messages=[
            {"role": "system", "content": "/no_think"},
        ],
    )

    # Qwen3 — try with chat_template_kwargs (alternative way)
    await test(
        "Qwen3.8-27b (enable_thinking=false)",
        "qwen/qwen3.8-27b",
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    # Qwen3 — plain, no changes (baseline)
    await test("Qwen3.8-27b (default)", "qwen/qwen3.8-27b")

    # Allam 2 7B — Saudi instruction model, might just work
    await test("Allam 2 7B", "allam-2-7b")


asyncio.run(main())