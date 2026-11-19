"""Two-step RAG: retrieve chunks, then generate an answer from them."""

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough

from finsight.config import settings
from finsight.generation.models import chat_model
from finsight.generation.prompts import PROMPTS
from finsight.generation.structured import (
    STRUCTURED_PROMPT,
    Answer,
    format_numbered,
    render,
    verify_citations,
)
from finsight.retrieval.retrievers import build_retriever


def source_label(doc: Document) -> str:
    m = doc.metadata
    return f"[{m['company']} {m['fiscal_year']}, p. {m['page'] + 1}]"  # 1-based for humans


def format_docs(docs: list[Document]) -> str:
    return "\n\n---\n\n".join(f"{source_label(d)}\n{d.page_content}" for d in docs)


def build_rag_chain(table_name: str = "chunks_live", k: int = 5, use_filters: bool = True,
                    hybrid: bool = False, use_hyde: bool = True, rerank_with: str | None = None,
                    candidates: int = 20, prompt: str = "v2", answer_model: str | None = None,
                    structured: bool = True):
    retriever = build_retriever(table_name, k=k, use_filters=use_filters, hybrid=hybrid, use_hyde=use_hyde,
                                rerank_with=rerank_with, candidates=candidates)
    model = chat_model(answer_model or settings.answer_model)

    # Step A: run retrieval, keep the question alongside the docs
    retrieve = RunnableParallel(docs=retriever, question=RunnablePassthrough())

    if structured:
        # Step B (structured): numbered context -> Answer object -> render text + verify citations in code
        def to_inputs(x):
            texts, labels = [d.page_content for d in x["docs"]], [source_label(d) for d in x["docs"]]
            return {"context": format_numbered(texts, labels), "question": x["question"]}

        def finish(x):
            texts, labels = [d.page_content for d in x["docs"]], [source_label(d) for d in x["docs"]]
            return {"answer": render(x["structured"], labels),
                    "citations": verify_citations(x["structured"], texts, labels)}

        generate_structured = RunnableLambda(to_inputs) | STRUCTURED_PROMPT | model.with_structured_output(Answer)
        # Output: {"question", "docs", "structured", "answer", "citations"}
        return retrieve.assign(structured=generate_structured) | RunnableLambda(lambda x: {**x, **finish(x)})

    # Step B: docs -> context string -> prompt -> model -> plain text
    generate = (
        RunnableLambda(lambda x: {"context": format_docs(x["docs"]), "question": x["question"]})
        | PROMPTS[prompt]
        | model
        | StrOutputParser()
    )

    # Output: {"question": ..., "docs": [...], "answer": "..."}
    return retrieve.assign(answer=generate)