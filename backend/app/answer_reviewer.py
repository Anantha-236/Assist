"""LLM-based coaching review of a user's interview answer."""

import json

import httpx

from . import db
from .config import GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL_PRIMARY

PROMPT = """You are an interview coach. Analyze this answer objectively.

Question: {question}
Candidate's answer: {answer}
Response latency: {latency}s
Word count: {words}
Filler rate: {filler_pct}% (um, uh, like, you know, etc.)

Return ONLY valid JSON with these exact keys:
{{
  "addressed_question": true or false,
  "structure_ok": true or false,
  "specificity_score": 1 to 5,
  "length_ok": "appropriate" or "short" or "long",
  "improvements": ["specific improvement 1", "specific improvement 2"],
  "example_improvement": "one rewritten answer, 2-3 sentences, showing the better version"
}}"""


async def _call_groq(prompt, api_key):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": GROQ_MODEL_PRIMARY,
                    "messages": [
                        {"role": "system",
                         "content": "You are a JSON-only API. Return valid JSON, nothing else."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
            )
        if r.status_code != 200:
            return None
        text = r.json()["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()
        return json.loads(text)
    except Exception as e:
        print(f"[reviewer] error: {e}")
        return None


async def review_answer(ans_id):
    ans = db.get_answer(ans_id)
    if not ans:
        return None

    keys = db.get_active_keys("groq")
    if not keys:
        if GROQ_API_KEY and GROQ_API_KEY.startswith("gsk_"):
            keys = [{"id": None, "key_value": GROQ_API_KEY}]
        else:
            return None

    m = ans["metrics"]
    prompt = PROMPT.format(
        question=ans["question"], answer=ans["answer"],
        latency=m.get("response_latency_sec", "?"),
        words=m.get("word_count", "?"),
        filler_pct=m.get("filler_rate_pct", 0),
    )

    for k in keys:
        review = await _call_groq(prompt, k["key_value"])
        if review and "improvements" in review:
            db.save_answer_review(ans_id, review)
            return review
    return None