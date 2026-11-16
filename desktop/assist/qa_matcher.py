"""Match interview questions against the local Q&A database."""

import re
from difflib import SequenceMatcher

from .qa_database import QA_DATABASE
from .coding_matcher import build_coding_answer, match_coding_question


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", (text or "").lower()).strip()


def _user_languages(profile: dict | None) -> list[str]:
    skills = (profile or {}).get("skills", "").lower()
    known = ["python", "javascript", "java", "c++", "c#", "go", "rust",
             "typescript", "kotlin", "swift", "c"]
    return [language for language in known if language in skills]


def match_question(
    text: str,
    role_slug: str | None = None,
    profile: dict | None = None,
    threshold: float = 0.75,
) -> dict | None:
    """Find the best matching Q&A entry. Returns entry + score, or None."""
    if not text:
        return None
    coding = match_coding_question(text)
    if coding:
        return {
            "patterns": coding["patterns"],
            "theme": "coding",
            "answer": build_coding_answer(coding, _user_languages(profile)),
            "score": 0.95,
            "source": "coding_database",
            "problem_id": coding["id"],
        }

    t = _normalize(text)
    if not t:
        return None

    best_entry = None
    best_score = 0.0

    for entry in QA_DATABASE:
        for pat in entry["patterns"]:
            p = _normalize(pat)
            if not p:
                continue
            if p in t:
                score = 0.95
            elif t in p and len(t) > 8:
                score = 0.85
            else:
                score = SequenceMatcher(None, p, t).ratio()
            if score > best_score:
                best_score = score
                best_entry = entry

    if best_entry is not None and best_score >= threshold:
        return {**best_entry, "score": round(best_score, 2)}
    return None


def format_answer(entry: dict, profile: dict | None = None) -> str:
    """Fill template placeholders from profile; append code if present."""
    profile = profile or {}
    subs = {
        "role": profile.get("role") or "a professional",
        "experience": profile.get("experience") or "a few years",
        "skills": profile.get("skills") or "my core skill areas",
    }

    if entry.get("source") == "coding_database":
        return entry.get("answer", "")

    answer = entry.get("answer", "")
    try:
        answer = answer.format(**subs)
    except (KeyError, IndexError):
        pass

    code = entry.get("code", "")
    if code:
        return f"{answer}\n\n{code}"
    return answer