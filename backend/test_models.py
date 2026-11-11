"""Diagnostic: which payload variations actually return streaming tokens?"""

import asyncio
import json

import httpx

from app.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODELS_FAST,
)


async def test(label: str, payload: dict):
    print(f"\n=== {label} ===")
    client = httpx.AsyncClient(
        base_url=OPENROUTER_BASE_URL,
        timeout=httpx.Timeout(30.0, connect=5.0),
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
        http2=True,
    )
    try:
        async with client.stream("POST", "/chat/completions", json=payload) as resp:
            print(f"  status: {resp.status_code}")
            if resp.status_code != 200:
                body = await resp.aread()
                print(f"  body: {body[:300]!r}")
                return
            lines = 0
            deltas = 0
            async for line in resp.aiter_lines():
                lines += 1
                if lines <= 2:
                    print(f"  raw line: {line[:150]!r}")
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    j = json.loads(data)
                except Exception:
                    continue
                usage = j.get("usage")
                if usage:
                    print("  usage:", usage)
                choices = j.get("choices") or [{}]
                delta = (choices[0].get("delta") or {}).get("content", "")
                if delta:
                    deltas += 1
                    if deltas <= 3:
                        print(f"  delta: {delta!r}")
            print(f"  total lines={lines}, deltas={deltas}")
    finally:
        await client.aclose()


async def main():
    model = OPENROUTER_MODELS_FAST[0]
    print(f"Testing model: {model}")

    await test("1. SINGLE model, no system", {
        "model": model,
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 10,
        "stream": True,
    })

    await test("2. MODELS array, no system", {
        "models": OPENROUTER_MODELS_FAST,
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 10,
        "stream": True,
    })

    await test("3. MODELS array + provider params", {
        "models": OPENROUTER_MODELS_FAST,
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 10,
        "stream": True,
        "provider": {"sort": "latency", "preferred_max_latency": 2},
    })

    await test("4. EXACT backend payload", {
        "models": OPENROUTER_MODELS_FAST,
        "messages": [
            {"role": "system", "content": "You are a silent meeting assistant. Answer in first person. Max 2 sentences."},
            {"role": "user", "content": "Context:\n\nQ: Say OK and nothing else"},
        ],
        "max_tokens": 80,
        "temperature": 0.2,
        "stream": True,
        "provider": {"sort": "latency", "preferred_max_latency": 2},
    })


if __name__ == "__main__":
    asyncio.run(main())