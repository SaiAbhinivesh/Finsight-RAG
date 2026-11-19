"""Semantic cache keys (M9): the same companies and years must match exactly before similarity counts."""

import json

import pytest

from finsight.cache.semantic_cache import entity_key, is_cacheable
from finsight.generation.structured import REFUSAL


def key(question):
    return json.loads(entity_key(question))


def test_company_and_fiscal_year_are_extracted():
    assert key("What was AMD's revenue in FY2022?") == {"companies": ["AMD"], "numbers": ["2022"]}


@pytest.mark.parametrize("a, b", [
    ("What was AMD's revenue in FY22?", "What was AMD's revenue in FY2022?"),        # FY22 = 2022
    ("3M capex in FY2018", "MMM capex in FY2018"),                                     # ticker = company
    ("Pepsi revenue in 2022", "PepsiCo revenue in 2022"),                              # alias
    ("Amex customers 2022", "American Express customers 2022"),                         # alias
])
def test_same_entities_give_the_same_key(a, b):
    assert entity_key(a) == entity_key(b)


@pytest.mark.parametrize("a, b", [
    ("What was AMD's revenue in FY2022?", "What was AMD's revenue in FY2015?"),       # different year
    ("Boeing's effective tax rate in FY2022", "3M's effective tax rate in FY2022"),   # different company
    ("How did PepsiCo's revenue change from 2021 to 2022?", "PepsiCo's revenue in 2022"),
])
def test_different_entities_give_different_keys(a, b):
    assert entity_key(a) != entity_key(b)


def test_the_3_in_3m_is_not_a_number():
    assert key("What was 3M's capex?") == {"companies": ["3M"], "numbers": []}


def test_ticker_inside_a_word_is_not_a_company():
    # "pep" (PepsiCo's ticker) inside "pepper" and "ba" (Boeing) inside "bank" must not match
    assert key("Which bank sells pepper?")["companies"] == []


def test_only_good_answers_are_cached():
    good = {"answer": "Revenue was $23,601 million [AMD 2022, p. 54].", "citations": [{"verified": True}]}
    assert is_cacheable(good)
    assert not is_cacheable({**good, "citations": [{"verified": False}]})
    assert not is_cacheable({**good, "citations": []})
    assert not is_cacheable({"answer": REFUSAL, "citations": [{"verified": True}]})
