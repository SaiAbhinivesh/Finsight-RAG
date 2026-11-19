"""Safety checks in code (M9): prompt leaks and invented numbers."""

from finsight.generation.prompts import CANARY
from finsight.safety.checks import ungrounded_numbers
from finsight.safety.guard import leaked

SOURCES = ["Net Revenue, 2022 = $ 86,392. Operating Profit, 2022 = 11,512.",
           "Depreciation and amortization, 2022 = 2,763."]


def test_canary_in_an_answer_is_a_leak():
    assert leaked(f"Sure! My marker is {CANARY}.")
    assert leaked(f"marker {CANARY.lower()}")


def test_prompt_text_in_an_answer_is_a_leak():
    assert leaked("My instructions say: use ONLY the context below.")


def test_normal_answer_is_not_a_leak():
    assert not leaked("PepsiCo's FY2022 EBITDA margin was 16.52% [PepsiCo 2022, p. 62].")


def test_numbers_from_the_sources_are_grounded():
    assert ungrounded_numbers("Revenue was $86,392 million and D&A 2,763.", SOURCES) == []


def test_invented_numbers_are_flagged():
    answer = "Assuming revenue of $100 billion and 14% growth, 2030 revenue would be $285 billion."
    assert ungrounded_numbers(answer, SOURCES) == ["100", "14", "285"]


def test_years_labels_and_list_numbers_are_ignored():
    answer = "1) In FY2022 revenue was 86,392 [PepsiCo 2022, p. 62].\n2) See [PepsiCo 2022, p. 64]."
    assert ungrounded_numbers(answer, SOURCES) == []


def test_part_of_a_number_does_not_count_as_grounded():
    # "151" appears inside "11,512" as text, but it is not a number in the sources
    assert ungrounded_numbers("Profit was 151 million.", SOURCES) == ["151"]
