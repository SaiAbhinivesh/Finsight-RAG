"""Self-query: pull company and fiscal year out of the question, to filter the search."""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from finsight.config import settings
from finsight.ingestion.loaders import load_manifest


class QueryFilters(BaseModel):
    company: str | None = Field(None, description="Company name exactly as listed, or null")
    fiscal_year: int | None = Field(None, description="Fiscal year of the filing to search, or null")


FILTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system",
         "You route questions about company annual reports (10-K filings) to the right filing.\n\n"
         "Available filings (company: fiscal years):\n{filings}\n\n"
         "Return the company and fiscal year of the ONE filing most likely to contain the answer.\n"
         "Rules:\n"
         "- Prefer the filing whose fiscal year matches the year the question is about\n"
         "  ('FY2021', 'as of 2021', 'in 2021' -> 2021).\n"
         "- Choose a later filing only when the question compares two years ('FY2022 vs FY2021' -> 2022)\n"
         "  or asks about a forecast ('forecast for 2023' -> 2022), or when the asked year has no filing.\n"
         "  So for 'FY2022 vs FY2021' choose 2022; for a forecast for 2023 choose 2022.\n"
         "- fiscal_year must be one of that company's listed years, or null if none fits or no year is implied."),
        ("human", "{question}"),
    ]
)


@lru_cache
def available_filings() -> dict[str, list[int]]:
    filings: dict[str, list[int]] = {}
    for row in load_manifest():
        filings.setdefault(row["company"], []).append(row["fiscal_year"])
    return {c: sorted(years) for c, years in filings.items()}


@lru_cache
def _extractor():
    listing = "\n".join(f"- {c}: {', '.join(map(str, ys))}" for c, ys in available_filings().items())
    model = init_chat_model(settings.chat_model, temperature=0)
    return FILTER_PROMPT.partial(filings=listing) | model.with_structured_output(QueryFilters)


def extract_filters(question: str) -> QueryFilters:
    f = _extractor().invoke({"question": question})
    filings = available_filings()
    # Guardrails: never trust an LLM to invent a company or year that doesn't exist
    if f.company not in filings:
        f.company = None
    if f.company and f.fiscal_year not in filings[f.company]:
        f.fiscal_year = None
    return f


def to_pg_filter(f: QueryFilters) -> dict | None:
    """QueryFilters -> PGVectorStore filter syntax."""
    clauses = []
    if f.company:
        clauses.append({"company": {"$eq": f.company}})
    if f.fiscal_year:
        clauses.append({"fiscal_year": {"$eq": f.fiscal_year}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}