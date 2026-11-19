"""Model prices and cost arithmetic (M9)."""

import pytest

from finsight.observability.pricing import PRICES, cost_usd, price_for


@pytest.mark.parametrize("model, expected", [
    ("gpt-5-mini", "gpt-5-mini"),
    ("gpt-5-mini-2025-08-07", "gpt-5-mini"),          # dated snapshot names from the API
    ("openai:gpt-4o-mini", "gpt-4o-mini"),            # provider prefix from .env
    ("gpt-4.1-mini-2025-04-14", "gpt-4.1-mini"),
])
def test_price_lookup(model, expected):
    assert price_for(model) == PRICES[expected]


def test_unknown_model_costs_nothing():
    assert price_for("some-other-model") is None
    assert cost_usd("some-other-model", 1000, 1000) == 0.0


def test_cost_of_one_million_tokens():
    p = PRICES["gpt-5-mini"]
    assert cost_usd("gpt-5-mini", 1_000_000, 0) == pytest.approx(p["input"])
    assert cost_usd("gpt-5-mini", 0, 1_000_000) == pytest.approx(p["output"])


def test_cached_input_tokens_are_cheaper():
    full = cost_usd("gpt-5-mini", 10_000, 0, cached_tokens=0)
    cached = cost_usd("gpt-5-mini", 10_000, 0, cached_tokens=10_000)
    assert cached < full
