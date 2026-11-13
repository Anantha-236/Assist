"""Parse a pasted resume into structured profile fields via Groq."""

import json

import httpx

from . import db
from .config import GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL_FALLBACK, GROQ_MODEL_PRIMARY

SYSTEM_PROMPT = (
    "You extract structured data from resumes. "
    "Return ONLY valid JSON, no explanation, no markdown fences. "
    "If a field is missing from the resume, use null."
)

USER_PROMPT = """Extract the following fields from this resume.
Return JSON with exactly these keys:
{{
  "role": "current or most recent job title",
  "experience": "X years (estimate from work history dates)",
  "skills": "comma-separated top 8-12 skills",
  "company": "current or most recent employer name",
  "education": "highest degree and institution",
  "achievements": "2-3 measurable wins, semicolon-separated, or null",
  "projects": "1-2 named projects with one-line description, or null"
}}

Resume:
---
{resume}
---"""


async def _call_groq(prompt, model, api_key):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 600,
                },
            )
        if r.status_code != 200:
            print(f"[resume] groq HTTP {r.status_code}: {r.text[:150]}")
            return None
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[resume] groq error: {e}")
        return None


def _extract_json(text):
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None


async def parse_resume(resume_text):
    if not resume_text or len(resume_text.strip()) < 100:
        return None
    trimmed = resume_text.strip()[:8000]

    keys = db.get_active_keys("groq")
    key_values = [k["key_value"] for k in keys] if keys else []
    if not key_values:
        if GROQ_API_KEY and GROQ_API_KEY.startswith("gsk_"):
            key_values = [GROQ_API_KEY]
    if not key_values:
        print("[resume] no Groq key available")
        return None

    prompt = USER_PROMPT.format(resume=trimmed)

    for model in (GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK):
        if not model:
            continue
        for key in key_values:
            raw = await _call_groq(prompt, model, key)
            parsed = _extract_json(raw) if raw else None
            if parsed:
                print(f"[resume] parsed: role={parsed.get('role')}, exp={parsed.get('experience')}")
                return parsed

    print("[resume] parse failed")
    return None


def save_parsed_profile(key_id, parsed):
    if not parsed:
        return
    with db._conn() as c:
        c.execute(
            "UPDATE activation_keys SET "
            "role = COALESCE(?, role), "
            "experience = COALESCE(?, experience), "
            "skills = COALESCE(?, skills), "
            "company = COALESCE(?, company), "
            "achievements = COALESCE(?, achievements), "
            "projects = COALESCE(?, projects) "
            "WHERE key_id = ?",
            (parsed.get("role"), parsed.get("experience"), parsed.get("skills"),
             parsed.get("company"), parsed.get("achievements"),
             parsed.get("projects"), key_id),
        )