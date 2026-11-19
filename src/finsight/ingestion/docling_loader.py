"""Docling: layout-aware PDF parsing (tables kept intact) + structure-aware chunking."""
import re

import tiktoken
from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.types.doc import DoclingDocument
from langchain_core.documents import Document

from finsight.config import ROOT_DIR
from finsight.ingestion.loaders import clean_text

PARSED_DIR = ROOT_DIR / "data" / "parsed"


def build_converter() -> DocumentConverter:
    """PDF -> DoclingDocument. OCR off: these are digital PDFs with real text."""
    options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def build_chunker(max_tokens: int = 512) -> HybridChunker:
    """Split by structure (sections, paragraphs, tables); only cut further above max_tokens."""
    tokenizer = OpenAITokenizer(tokenizer=tiktoken.get_encoding("cl100k_base"), max_tokens=max_tokens)
    return HybridChunker(tokenizer=tokenizer, merge_peers=True)

def signatures_page(doc: DoclingDocument) -> int | None:
    """1-based page of the 10-K 'SIGNATURES' heading. Everything after it is attached exhibits."""
    for item in doc.texts:
        compact = re.sub(r"\s", "", item.text or "").upper()  # handles 'SIGNATURE S' (3M 2018)
        if compact in ("SIGNATURE", "SIGNATURES") and item.prov:
            return item.prov[0].page_no  # first one = end of the main report
    return None

def load_filing_docling(row: dict, max_tokens: int = 512, drop_exhibits: bool = False) -> list[Document]:
    """Chunk one cached Docling document into LangChain Documents with our metadata."""
    doc = DoclingDocument.load_from_json(PARSED_DIR / f"{row['doc_name']}.json")
    chunker = build_chunker(max_tokens)
    cutoff = None
    if drop_exhibits:
        sig = signatures_page(doc)
        cutoff = sig + 1 if sig else None  # keep the signatures page and the one after it

    documents = []
    for i, chunk in enumerate(chunker.chunk(dl_doc=doc)):
        text = clean_text(chunker.contextualize(chunk=chunk))  # headings + chunk text
        if not text.strip():
            continue

        # Docling pages are 1-based; ours are 0-based. A chunk (e.g. a table) can span pages.
        pages = sorted({prov.page_no - 1 for item in chunk.meta.doc_items for prov in item.prov})
        if cutoff is not None and pages and pages[0] + 1 > cutoff:
            continue  # chunk starts after the signatures page: an exhibit
        documents.append(Document(
            page_content=text,
            metadata={
                "doc_name": row["doc_name"],
                "company": row["company"],
                "ticker": row["ticker"],
                "fiscal_year": row["fiscal_year"],
                "doc_type": row["doc_type"],
                "sector": row["sector"],
                "page": pages[0] if pages else 0,
                "pages": ",".join(str(p) for p in pages),
                "headings": " > ".join(chunk.meta.headings or []),
                "chunk_index": i,
                "source": f"{row['doc_name']}.pdf",
            },
        ))
    return documents