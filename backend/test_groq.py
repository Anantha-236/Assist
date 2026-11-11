"""Test Groq directly."""

import asyncio
import json

import httpx

from app.config import GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL_PRIMARY


async def main():
    async with httpx.AsyncClient(
        base_url=GROQ_BASE_URL,
        timeout=httpx.Timeout(30.0, connect=5.0),
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
    ) as client:
        print(f"Model: {GROQ_MODEL_PRIMARY}")
        async with client.stream(
            "POST",
            "/chat/completions",
            json={
                "model": GROQ_MODEL_PRIMARY,
                "messages": [
                    {"role": "system", "content": "Answer in one short sentence."},
                    {"role": "user", "content": "Say OK and nothing else"},
                ],
                "max_tokens": 20,
                "stream": True,
            },
        ) as resp:
            print("status:", resp.status_code)
            content_count = 0
            reasoning_count = 0
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                d = line[6:].strip()
                if d == "[DONE]":
                    print(f"done — content={content_count} reasoning={reasoning_count}")
                    break
                try:
                    j = json.loads(d)
                except Exception:
                    continue
                ch = (j.get("choices") or [{}])[0].get("delta") or {}
                c = ch.get("content") or ""
                r = ch.get("reasoning") or ch.get("reasoning_content") or ""
                if r:
                    reasoning_count += 1
                if c:
                    content_count += 1
                    if content_count <= 5:
                        print(f"  + {c!r}")


asyncio.run(main())