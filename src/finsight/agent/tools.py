"""Tools the agent can call: search one filing, and exact arithmetic."""

import ast
import operator
from functools import lru_cache

from langchain_core.documents import Document
from langchain_core.tools import tool

from finsight.generation.chain import source_label
from finsight.indexing.store import get_vector_store
from finsight.retrieval.filters import QueryFilters, available_filings, to_pg_filter
from finsight.retrieval.keyword import doc_key

RESULTS_PER_SEARCH = 5
MAX_SEARCHES = 6  # hard budget per question, enforced in code (the prompt alone was ignored)


@lru_cache
def _store():
    return get_vector_store("chunks_live")


# --- calculator: a tiny safe evaluator (never use Python's eval on model output) ---
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


MAX_EXPONENT = 100   # "9**9**9" would freeze the process: no financial formula needs a bigger power


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ValueError(f"exponent larger than {MAX_EXPONENT}")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("only numbers and + - * / ** ( ) are allowed")


def make_tools(registry: list[Document], log: list[dict], max_searches: int = MAX_SEARCHES):
    """Build the tools for ONE question. Every chunk the agent sees is added to `registry`,
    numbered across all searches, so the final answer's [n] citations can be verified.
    Every tool call is appended to `log`, so we keep the steps even if the agent is stopped."""

    @tool
    def search_filings(query: str, company: str, fiscal_year: int) -> str:
        """Search ONE company's 10-K for ONE fiscal year. Write the query in 10-K wording
        (line items, section names). Returns numbered results like [3] [Company Year, p. N]."""
        n_done = sum(c["name"] == "search_filings" for c in log)
        log.append({"name": "search_filings", "args": {"query": query, "company": company, "fiscal_year": fiscal_year}})
        if n_done >= max_searches:
            return (f"Search limit reached ({max_searches} searches). Do not search again. "
                    "Answer now with the results you already have, or refuse if they are not enough.")
        filings = available_filings()
        if company not in filings or fiscal_year not in filings[company]:
            return f"No such filing. Available filings: {filings}"
        flt = to_pg_filter(QueryFilters(company=company, fiscal_year=fiscal_year))
        docs = _store().similarity_search(query, k=RESULTS_PER_SEARCH, filter=flt)

        lines = []
        for d in docs:
            seen = [doc_key(r) for r in registry]
            if doc_key(d) in seen:                      # already returned earlier: reuse its number
                n = seen.index(doc_key(d)) + 1
            else:
                registry.append(d)
                n = len(registry)
            lines.append(f"[{n}] {source_label(d)}\n{d.page_content}")
        return "\n\n---\n\n".join(lines) if lines else "No results."

    @tool
    def calculator(expression: str) -> str:
        """Exact arithmetic, e.g. '(11512 + 2763) / 86392'. Numbers without commas or $ signs."""
        log.append({"name": "calculator", "args": {"expression": expression}})
        try:
            value = _eval(ast.parse(expression.replace(",", ""), mode="eval").body)
            return str(round(value, 6))
        except Exception as e:
            return f"Error: {e}"

    return [search_filings, calculator]