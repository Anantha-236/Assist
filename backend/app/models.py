"""Static model registry — cost + capability metadata for routing."""

# Tiers (higher = more capable + more expensive)
TIER_FAST = 1          # simple extraction, classification, short factual
TIER_BALANCED = 2      # general Q&A, summaries, light reasoning
TIER_REASONING = 3     # multi-step reasoning, complex analysis
TIER_CODE = 4          # coding, algorithms, debugging
TIER_FRONTIER = 5      # hardest reasoning + coding (rarely used)

# Capability flags used by the router
CAP_GENERAL = "general"
CAP_CODE = "code"
CAP_REASONING = "reasoning"
CAP_FAST = "fast"
CAP_LONG_CONTEXT = "long_context"

# Provider → model catalog
# Prices are $ per 1M tokens (input, output) as of late 2026.
MODEL_REGISTRY = {
    "groq": {
        "llama-3.1-8b-instant": {
            "tier": TIER_FAST,
            "caps": [CAP_GENERAL, CAP_FAST],
            "input_per_mtok": 0.05,
            "output_per_mtok": 0.08,
            "context": 131_072,
            "speed_tok_s": 1000,
            "best_for": "classification, extraction, short factual answers",
        },
        "openai/gpt-oss-20b": {
            "tier": TIER_FAST,
            "caps": [CAP_GENERAL, CAP_FAST],
            "input_per_mtok": 0.075,
            "output_per_mtok": 0.30,
            "context": 131_072,
            "speed_tok_s": 1000,
            "best_for": "general Q&A, meeting transcripts",
        },
        "openai/gpt-oss-120b": {
            "tier": TIER_BALANCED,
            "caps": [CAP_GENERAL, CAP_REASONING],
            "input_per_mtok": 0.15,
            "output_per_mtok": 0.60,
            "context": 131_072,
            "speed_tok_s": 500,
            "best_for": "multi-step reasoning, nuanced answers",
        },
        "qwen/qwen3.8-27b": {
            "tier": TIER_REASONING,
            "caps": [CAP_REASONING, CAP_CODE, CAP_LONG_CONTEXT],
            "input_per_mtok": 0.80,
            "output_per_mtok": 4.00,
            "context": 131_072,
            "speed_tok_s": 450,
            "best_for": "hard reasoning, coding, long context",
        },
    },
    "openrouter": {
        "meta-llama/llama-3.1-8b-instruct:free": {
            "tier": TIER_FAST,
            "caps": [CAP_GENERAL, CAP_FAST],
            "input_per_mtok": 0.0,
            "output_per_mtok": 0.0,
            "context": 131_072,
            "speed_tok_s": 500,
            "best_for": "free tier general Q&A",
        },
        "qwen/qwen3-8b:free": {
            "tier": TIER_FAST,
            "caps": [CAP_GENERAL, CAP_FAST],
            "input_per_mtok": 0.0,
            "output_per_mtok": 0.0,
            "context": 131_072,
            "speed_tok_s": 400,
            "best_for": "free tier general + light code",
        },
        "google/gemma-2-9b-it:free": {
            "tier": TIER_BALANCED,
            "caps": [CAP_GENERAL, CAP_REASONING],
            "input_per_mtok": 0.0,
            "output_per_mtok": 0.0,
            "context": 131_072,
            "speed_tok_s": 400,
            "best_for": "free tier reasoning",
        },
        "anthropic/claude-haiku-5.5": {
            "tier": TIER_FAST,
            "caps": [CAP_GENERAL, CAP_FAST],
            "input_per_mtok": 0.10,
            "output_per_mtok": 0.40,
            "context": 200_000,
            "speed_tok_s": 300,
            "best_for": "cheap fast general",
        },
        "anthropic/claude-sonnet-5.5": {
            "tier": TIER_BALANCED,
            "caps": [CAP_GENERAL, CAP_REASONING, CAP_CODE],
            "input_per_mtok": 2.00,
            "output_per_mtok": 8.00,
            "context": 200_000,
            "speed_tok_s": 150,
            "best_for": "balanced reasoning + code",
        },
        "anthropic/claude-opus-5.5": {
            "tier": TIER_FRONTIER,
            "caps": [CAP_REASONING, CAP_CODE, CAP_LONG_CONTEXT],
            "input_per_mtok": 15.00,
            "output_per_mtok": 30.00,
            "context": 400_000,
            "speed_tok_s": 80,
            "best_for": "hardest reasoning, large codebases",
        },
    },
}


def models_for_provider(provider: str) -> dict:
    return MODEL_REGISTRY.get(provider, {})


def get_model(provider: str, model_id: str) -> dict | None:
    return MODEL_REGISTRY.get(provider, {}).get(model_id)


def estimate_cost(provider: str, model_id: str, in_tok: int, out_tok: int) -> float:
    m = get_model(provider, model_id)
    if not m:
        return 0.0
    return (in_tok / 1_000_000) * m["input_per_mtok"] + \
           (out_tok / 1_000_000) * m["output_per_mtok"]