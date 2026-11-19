"""Retrieval helpers (M4): chunk identity and Reciprocal Rank Fusion."""

from finsight.retrieval.keyword import doc_key, rrf


def test_doc_key_identifies_a_chunk(make_doc):
    assert doc_key(make_doc(page=10, chunk_index=3)) == ("AMD_2022_10K", 3, 10)
    assert doc_key(make_doc(page=10, chunk_index=3)) == doc_key(make_doc(text="other text", page=10, chunk_index=3))


def test_rrf_puts_chunks_found_by_both_lists_first(make_doc):
    a, b, c, d = (make_doc(chunk_index=i) for i in range(4))
    fused = rrf([[a, b, c], [d, c, a]])
    assert [doc_key(x) for x in fused[:2]] == [doc_key(a), doc_key(c)]   # in both lists
    assert len(fused) == 4                                                 # no duplicates


def test_rrf_single_list_keeps_order(make_doc):
    docs = [make_doc(chunk_index=i) for i in range(3)]
    assert rrf([docs]) == docs
