"""Cost-aware model router: cheapest model that meets required tier."""

import os

from .models import MODEL_REGISTRY, estimate_cost


def _rank_candidates(provider: str, required_tier: int) -> list[dict]:
    """Return models in this provider that meet the tier, cheapest first."""
    catalog = MODEL_REGISTRY.get(provider, {})
    candidates = []
    for model_id, m in catalog.items():
        if m["tier"] < required_tier:
            continue
        # cost proxy: average per-token price (input+output)
        cost = (m["input_per_mtok"] + m["output_per_mtok"]) / 2
        candidates.append({
            "provider": provider,
            "model_id": model_id,
            "tier": m["tier"],
            "caps": m["caps"],
            "cost": cost,
            "speed": m.get("speed_tok_s", 0),
            "input_per_mtok": m["input_per_mtok"],
            "output_per_mtok": m["output_per_mtok"],
        })
    # Sort by cost ASC, then speed DESC as tiebreaker
    candidates.sort(key=lambda c: (c["cost"], -c["speed"]))
    return candidates


def _provider_priority() -> list[str]:
    """Order of providers to try. Override via env var."""
    default = os.environ.get("ROUTER_PROVIDER_ORDER", "groq,openrouter")
    return [p.strip() for p in default.split(",") if p.strip()]


def select_model(classification: dict, force_provider: str | None = None) -> dict | None:
    """
    Pick the cheapest model meeting the required tier.
    Returns {provider, model_id, tier, cost, input_per_mtok, output_per_mtok,
             reason}.
    Returns None if no candidate fits.
    """
    required_tier = classification["required_tier"]
    intent = classification["intent"]
    complexity = classification["complexity"]

    providers = [force_provider] if force_provider else _provider_priority()

    all_candidates = []
    for provider in providers:
        all_candidates.extend(_rank_candidates(provider, required_tier))

    if not all_candidates:
        # Escalate: no model meets tier → fall back to highest tier available
        for provider in providers:
            catalog = MODEL_REGISTRY.get(provider, {})
            if not catalog:
                continue
            # highest-tier model in this provider
            top = max(
                catalog.items(),
                key=lambda kv: kv[1]["tier"],
            )
            m = top[1]
            return {
                "provider": provider,
                "model_id": top[0],
                "tier": m["tier"],
                "cost": (m["input_per_mtok"] + m["output_per_mtok"]) / 2,
                "input_per_mtok": m["input_per_mtok"],
                "output_per_mtok": m["output_per_mtok"],
                "reason": f"escalated (no tier-{required_tier} model available)",
            }

    # Prefer candidates that explicitly support the intent capability
    def cap_match(c):
        if intent == "code" and "code" in c["caps"]:
            return 0
        if intent == "reasoning" and "reasoning" in c["caps"]:
            return 0
        return 1

    # Stable sort: cost first, then capability match
    all_candidates.sort(key=lambda c: (cap_match(c), c["cost"], -c["speed"]))

    best = all_candidates[0]
    return {
        "provider": best["provider"],
        "model_id": best["model_id"],
        "tier": best["tier"],
        "cost": best["cost"],
        "input_per_mtok": best["input_per_mtok"],
        "output_per_mtok": best["output_per_mtok"],
        "reason": f"{intent}/{complexity} → tier {required_tier} → {best['model_id']} "
                  f"(${best['cost']:.3f}/M avg)",
    }


def dry_run(text: str) -> dict:
    """Test the full pipeline without an LLM call."""
    from .classifier import classify
    cls = classify(text)
    model = select_model(cls)
    return {"classification": cls, "selected_model": model}