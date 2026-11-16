"""Match spoken coding questions to curated reference solutions."""

import re

from .coding_database import CODING_PROBLEMS, pick_code


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9+#. ]+", " ", (text or "").lower()).strip()


def match_coding_question(text: str) -> dict | None:
    """Return the strongest coding problem match, if confidence is sufficient."""
    normalized = _normalize(text)
    if len(normalized) < 4:
        return None
    tokens = set(normalized.split())
    best = None
    best_score = 0
    for problem in CODING_PROBLEMS:
        for pattern in problem["patterns"]:
            candidate = _normalize(pattern)
            candidate_tokens = candidate.split()
            if normalized == candidate:
                score = 1000 + len(candidate)
            elif f" {candidate} " in f" {normalized} ":
                score = 500 + len(candidate)
            elif len(candidate_tokens) >= 3 and all(
                token in tokens for token in candidate_tokens
            ):
                score = 100 + len(candidate)
            elif len(candidate_tokens) == 2 and all(
                token in tokens for token in candidate_tokens
            ):
                score = 50 + len(candidate)
            else:
                continue
            if score > best_score:
                best, best_score = problem, score
    return best if best_score >= 50 else None


def build_coding_answer(
    problem: dict, user_languages: list[str] | None = None
) -> str:
    """Format a curated solution as an explanation, code block, and complexity."""
    language, code = pick_code(problem, user_languages or [])
    answer = problem.get("explanation", "")
    if code:
        answer += f"\n\n```{language}\n{code}\n```"
    return f"{answer}\n\n**Complexity:** {problem.get('complexity', '')}"
