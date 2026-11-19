"""Query rewriting: HyDE (Hypothetical Document Embeddings)."""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from finsight.config import settings

HYDE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system",
         "Write a short passage (3-5 sentences) in the style of an SEC 10-K annual report that would "
         "answer the question. Use the section names and line-item wording a 10-K would use "
         "(e.g. 'Purchases of property, plant and equipment', 'Total current liabilities', "
         "'Item 3. Legal Proceedings'). Invent plausible figures if needed; the passage is only used "
         "for search. Reply with the passage only."),
        ("human", "{question}"),
    ]
)


@lru_cache
def _hyde_chain():
    model = init_chat_model(settings.chat_model, temperature=0)
    return HYDE_PROMPT | model | StrOutputParser()


def hyde(question: str) -> str:
    """Return a hypothetical 10-K-style passage to search with instead of the question."""
    return _hyde_chain().invoke({"question": question})