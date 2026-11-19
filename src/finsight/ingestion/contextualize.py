"""Contextual retrieval: prefix each chunk with a short note saying where it sits in the filing."""

import json

from langchain.chat_models import init_chat_model
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from finsight.config import ROOT_DIR, settings

CONTEXT_DIR = ROOT_DIR / "data" / "parsed" / "contexts"

CONTEXT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system",
         "You write short search context for chunks of SEC 10-K filings. "
         "In 1-2 sentences, say which company and fiscal year the chunk is from and what it is "
         "(e.g. consolidated balance sheet, cash flow statement, risk factor about supply chain). "
         "If it is a table, name the key line items and the financial concepts it can be used for "
         "(e.g. liquidity, capital expenditure, operating margin, debt). "
         "Do not repeat numbers. Reply with the sentences only."),
        ("human",
         "Company: {company} ({ticker})\nFiling: Form 10-K, fiscal year {fiscal_year}\n"
         "Section: {section}\n\nChunk:\n{chunk}"),
    ]
)


def template_context(doc: Document) -> str:
    """Free version: a fixed sentence built from metadata."""
    m = doc.metadata
    return (f"From {m['company']} ({m['ticker']}) Form {m['doc_type']} annual report, "
            f"fiscal year {m['fiscal_year']}, section: {m.get('headings') or 'unknown'}.")


def llm_contexts(docs: list[Document], cache_name: str) -> list[str]:
    """LLM version, cached per filing so re-runs cost nothing."""
    path = CONTEXT_DIR / f"{cache_name}.jsonl"
    cached = {}
    if path.exists():
        with path.open() as f:
            cached = {r["chunk_index"]: r["context"] for r in map(json.loads, f)}

    todo = [d for d in docs if d.metadata["chunk_index"] not in cached]
    if todo:
        CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        model = init_chat_model(settings.chat_model, temperature=0, max_retries=6)
        chain = CONTEXT_PROMPT | model | StrOutputParser()
        for start in range(0, len(todo), 100):  # save every 100, so a crash loses little
            batch = todo[start : start + 100]
            inputs = [
                {"company": d.metadata["company"], "ticker": d.metadata["ticker"],
                 "fiscal_year": d.metadata["fiscal_year"],
                 "section": d.metadata.get("headings") or "unknown", "chunk": d.page_content[:6000]}
                for d in batch
            ]
            outputs = chain.batch(inputs, config={"max_concurrency": 8})
            with path.open("a") as f:
                for d, ctx in zip(batch, outputs):
                    cached[d.metadata["chunk_index"]] = ctx.strip()
                    f.write(json.dumps({"chunk_index": d.metadata["chunk_index"], "context": ctx.strip()}) + "\n")
            print(f"    contexts {min(start + 100, len(todo))}/{len(todo)}", flush=True)

    return [cached[d.metadata["chunk_index"]] for d in docs]


def add_context(docs: list[Document], mode: str, cache_name: str) -> list[Document]:
    """mode: 'template' or 'llm'. The context goes in front of the chunk text (that is what gets embedded)."""
    contexts = [template_context(d) for d in docs] if mode == "template" else llm_contexts(docs, cache_name)
    for d, ctx in zip(docs, contexts):
        d.metadata["context"] = ctx
        d.page_content = f"{ctx}\n\n{d.page_content}"
    return docs