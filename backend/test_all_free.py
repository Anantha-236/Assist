"""Test every free model — report which produce visible streaming content."""

import asyncio
import json

import httpx

from app.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL


async def test_model(client: httpx.AsyncClient, model: str) -> dict:
    result = {
        "model": model,
        "status": None,
        "deltas": 0,
        "first_token_s": None,
        "answer": "",
        "error": None,
    }
    t0 = asyncio.get_event_loop().time()
    try:
        async with client.stream(
            "POST",
            "/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with just: OK"}],
                "max_tokens": 600,
                "stream": True,
            },
        ) as resp:
            result["status"] = resp.status_code
            if resp.status_code != 200:
                body = await resp.aread()
                result["error"] = body[:200].decode("utf-8", "ignore")
                return result
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
                choices = j.get("choices") or [{}]
                delta = (choices[0].get("delta") or {}).get("content", "")
                if delta:
                    if result["first_token_s"] is None:
                        result["first_token_s"] = asyncio.get_event_loop().time() - t0
                    result["deltas"] += 1
                    if len(result["answer"]) < 100:
                        result["answer"] += delta
    except asyncio.TimeoutError:
        result["error"] = "timeout"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result


async def main():
    # Get all free models
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(f"{OPENROUTER_BASE_URL}/models")
        free = sorted([
            m["id"] for m in r.json()["data"]
            if m["id"].endswith(":free")
        ])

    print(f"Testing {len(free)} free models...\n")

    async with httpx.AsyncClient(
        base_url=OPENROUTER_BASE_URL,
        timeout=httpx.Timeout(30.0, connect=5.0),
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
    ) as client:
        results = []
        for m in free:
            print(f"  {m} ...", end=" ", flush=True)
            r = await test_model(client, m)
            results.append(r)
            if r["status"] == 200 and r["deltas"] > 0:
                print(f"✅ {r['deltas']} tokens, first in {r['first_token_s']:.1f}s")
            elif r["status"] == 200:
                print("⚠️  200 but 0 visible tokens (reasoning or empty)")
            else:
                err = (r["error"] or "")[:60]
                print(f"❌ {r['status']} {err}")

    print("\n=== WORKING MODELS (ranked by first token) ===\n")
    working = [r for r in results if r["status"] == 200 and r["deltas"] > 0]
    working.sort(key=lambda r: r["first_token_s"] or 999)

    if not working:
        print("  NONE — all free models failed. This may be your account or network.")
        print("  Try adding $10 credit at https://openrouter.ai/settings/credits")
        return

    for r in working:
        print(f"  ✅ {r['model']}")
        print(f"      first token: {r['first_token_s']:.2f}s")
        print(f"      tokens: {r['deltas']}")
        print(f"      reply: {r['answer'][:80]!r}\n")


if __name__ == "__main__":
    asyncio.run(main())