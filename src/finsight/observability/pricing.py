"""OpenAI list prices in USD per 1M tokens (standard tier).

Prices change: check https://openai.com/api/pricing and update PRICES_AS_OF when you edit them.
"""

PRICES_AS_OF = "2026-11-18"

PRICES = {
    "gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.00},
    "gpt-4.1-mini": {"input": 0.40, "cached_input": 0.10, "output": 1.60},
    "gpt-4o-mini": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
    "text-embedding-3-small": {"input": 0.02, "cached_input": 0.02, "output": 0.0},
}


def price_for(model: str) -> dict | None:
    """'gpt-5-mini-2025-08-07' -> prices of 'gpt-5-mini' (longest matching prefix)."""
    model = model.removeprefix("openai:")
    matches = [k for k in PRICES if model.startswith(k)]
    return PRICES[max(matches, key=len)] if matches else None


def cost_usd(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    p = price_for(model)
    if not p:
        return 0.0
    fresh = max(input_tokens - cached_tokens, 0)
    return (fresh * p["input"] + cached_tokens * p["cached_input"] + output_tokens * p["output"]) / 1_000_000