"""Fast heuristic classifier: intent (code/reasoning/general) + complexity."""

import re

from .models import (
    TIER_FAST, TIER_BALANCED, TIER_REASONING, TIER_CODE, TIER_FRONTIER,
)

# ---- intent signals ----

_CODE_VERBS = {
    "write", "implement", "create", "build", "code", "program", "debug",
    "fix", "refactor", "optimize", "convert", "generate",
}
_CODE_NOUNS = {
    "function", "program", "algorithm", "code", "method", "class",
    "script", "snippet", "query", "regex", "solution", "implementation",
}
_CODE_LANGS = {
    "python", "javascript", "typescript", "java", "c++", "c#", "go",
    "rust", "sql", "bash", "kotlin", "swift", "php",
}
_CODE_ALGO = {
    "prime", "fibonacci", "factorial", "palindrome", "fizzbuzz",
    "two sum", "linked list", "binary tree", "binary search",
    "hash map", "hashmap", "sort", "reverse", "merge sort", "quick sort",
    "bfs", "dfs", "dynamic programming", "recursion", "time complexity",
    "space complexity", "big o",
}
_CODE_PHRASES = (
    "write a function", "write code", "write a program", "implement a",
    "implement the", "code for", "program to", "function to", "solve this",
    "leetcode", "hackerrank", "generate code", "pseudo code", "pseudocode",
)

_REASONING_SIGNALS = (
    "why", "explain how", "compare", "trade-off", "tradeoff", "pros and cons",
    "analyze", "analysis", "evaluate", "reason", "implications", "impact",
    "step by step", "multi-step", "design", "architect", "strategy",
    "difference between", "which is better", "should i",
)

_FACTUAL_SIGNALS = (
    "what is", "who is", "when did", "where is", "how many", "how much",
    "define", "definition of", "meaning of",
)

# ---- complexity signals ----

_COMPLEX_MARKERS = (
    "and then", "after that", "also", "additionally", "furthermore",
    "step 1", "step 2", "first", "second", "third",
    "multiple", "several", "various", "complex", "intricate",
    "in detail", "thoroughly", "comprehensive",
)

_CODE_COMPLEX = (
    "optimize", "refactor", "concurrent", "parallel", "distributed",
    "dynamic programming", "memoization", "recursion", "time complexity",
    "space complexity", "big o", "edge case", "large scale",
)


def classify(text: str) -> dict:
    """Returns {intent, complexity, required_tier, reason, signals}."""
    if not text:
        return {
            "intent": "general",
            "complexity": "low",
            "required_tier": TIER_FAST,
            "reason": "empty input",
            "signals": [],
        }

    t = text.lower().strip()
    words = t.split()
    signals = []

    # ---------- intent ----------
    is_code = False
    strong_code = any(p in t for p in _CODE_PHRASES)
    has_verb = bool(set(words) & _CODE_VERBS)
    has_noun = bool(set(words) & _CODE_NOUNS)
    has_lang = bool(set(words) & _CODE_LANGS)
    has_algo = any(a in t for a in _CODE_ALGO)

    if strong_code:
        is_code = True
        signals.append("strong_code_phrase")
    elif has_verb and (has_noun or has_algo):
        is_code = True
        signals.append("imperative+noun")
    elif has_lang and has_algo:
        is_code = True
        signals.append("language+algorithm")
    elif has_verb and has_lang:
        is_code = True
        signals.append("imperative+language")

    is_reasoning = any(s in t for s in _REASONING_SIGNALS)
    is_factual = any(s in t for s in _FACTUAL_SIGNALS)

    if is_code:
        intent = "code"
    elif is_reasoning:
        intent = "reasoning"
    else:
        intent = "general"

    # ---------- complexity ----------
    word_count = len(words)
    complex_hits = sum(1 for c in _COMPLEX_MARKERS if c in t)
    code_complex_hits = sum(1 for c in _CODE_COMPLEX if c in t)

    if word_count < 10 and complex_hits == 0:
        complexity = "low"
    elif word_count < 30 and complex_hits <= 1 and code_complex_hits <= 1:
        complexity = "medium"
    else:
        complexity = "high"

    # ---------- required tier ----------
    if intent == "code":
        required = TIER_CODE
        if complexity == "high":
            required = TIER_FRONTIER
        elif complexity == "low":
            # simple code (reverse string) doesn't need frontier
            required = TIER_REASONING
    elif intent == "reasoning":
        required = TIER_REASONING if complexity != "low" else TIER_BALANCED
    else:
        if complexity == "low" or is_factual:
            required = TIER_FAST
        elif complexity == "medium":
            required = TIER_BALANCED
        else:
            required = TIER_REASONING

    reason = f"{intent}/{complexity}"
    if is_code:
        reason += f" ({'+'.join(signals)})"

    return {
        "intent": intent,
        "complexity": complexity,
        "required_tier": required,
        "reason": reason,
        "signals": signals,
    }


def required_model_tier(intent: str, complexity: str) -> int:
    return classify(f"{intent} {complexity}")["required_tier"]