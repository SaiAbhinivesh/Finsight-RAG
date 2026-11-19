"""Citation checks (M6): a quote is verified only if it really appears in the block it names."""

from finsight.generation.chain import source_label
from finsight.generation.structured import REFUSAL, Answer, Citation, render, verify_citations

TEXTS = [
    "Operating Profit, 2022 = 11,512. Net Revenue, 2022 = $ 86,392.",
    "Depreciation and amortization, 2022 = 2,763.",
]
LABELS = ["[PepsiCo 2022, p. 62]", "[PepsiCo 2022, p. 64]"]


def answer(citations, text="EBITDA = 11,512 [1] + 2,763 [2].", answerable=True):
    return Answer(answer=text, answerable=answerable, citations=[Citation(source=s, quote=q) for s, q in citations])


def test_exact_quote_is_verified():
    result = verify_citations(answer([(1, "Operating Profit, 2022 = 11,512.")]), TEXTS, LABELS)
    assert result[0]["verified"] is True
    assert result[0]["label"] == "[PepsiCo 2022, p. 62]"


def test_whitespace_and_case_do_not_matter():
    result = verify_citations(answer([(2, "depreciation   and AMORTIZATION, 2022 =\n2,763.")]), TEXTS, LABELS)
    assert result[0]["verified"] is True


def test_paraphrase_is_not_verified():
    result = verify_citations(answer([(1, "Operating profit was 11,512 in 2022")]), TEXTS, LABELS)
    assert result[0]["verified"] is False


def test_quote_from_the_wrong_block_is_not_verified():
    result = verify_citations(answer([(2, "Operating Profit, 2022 = 11,512.")]), TEXTS, LABELS)
    assert result[0]["verified"] is False


def test_block_number_out_of_range():
    result = verify_citations(answer([(5, "anything")]), TEXTS, LABELS)
    assert result[0]["verified"] is False
    assert result[0]["label"] is None


def test_render_replaces_markers_with_labels():
    text = render(answer([]), LABELS)
    assert text == "EBITDA = 11,512 [PepsiCo 2022, p. 62] + 2,763 [PepsiCo 2022, p. 64]."


def test_render_keeps_unknown_markers():
    assert render(answer([], text="See [7]."), LABELS) == "See [7]."


def test_render_not_answerable_gives_the_refusal():
    assert render(answer([], answerable=False), LABELS) == REFUSAL


def test_source_label_is_one_based(make_doc):
    assert source_label(make_doc(company="Boeing", fiscal_year=2022, page=8)) == "[Boeing 2022, p. 9]"
