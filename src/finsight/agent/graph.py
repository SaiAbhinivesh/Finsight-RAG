"""M7 Part B: a fixed LangGraph workflow. Code decides the path; the LLM fills in each step."""

import ast
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from finsight.agent.tools import RESULTS_PER_SEARCH, _eval, _store  # reuse the agent's store + safe calculator
from finsight.config import settings
from finsight.generation.chain import source_label
from finsight.generation.models import chat_model
from finsight.generation.structured import REFUSAL, STRUCTURED_PROMPT, Answer, format_numbered, render, verify_citations
from finsight.retrieval.filters import QueryFilters, available_filings, to_pg_filter
from finsight.retrieval.keyword import doc_key

MAX_RETRIES = 2        # extra retrieve rounds after the first one
MAX_SEARCHES_PER_ROUND = 6


# ---------- what the LLM returns at each step ----------
class Search(BaseModel):
    query: str = Field(description="Search query in 10-K wording, e.g. 'total current liabilities'")
    company: str = Field(description="Company name exactly as in the filings list")
    fiscal_year: int


class Plan(BaseModel):
    facts: list[str] = Field(description="Each fact or number needed to answer, one per item")
    searches: list[Search] = Field(description="One search per fact, max 6")


class Grade(BaseModel):
    missing: list[str] = Field(default_factory=list, description="Needed facts NOT in the results")
    searches: list[Search] = Field(default_factory=list, description="New, more specific searches for missing facts")


class Calculation(BaseModel):
    label: str = Field(description="What is being calculated, e.g. 'EBITDA margin %'")
    expression: str = Field(description="Plain numbers only, e.g. '(11512 + 2763) / 86392 * 100'")


class Calculations(BaseModel):
    items: list[Calculation] = Field(default_factory=list, description="Empty if no arithmetic is needed")


# ---------- the shared state every node reads and updates ----------
class GraphState(TypedDict, total=False):
    question: str
    facts: list[str]
    pending: list[Search]      # searches waiting to run
    done: list[str]            # searches already run, so we never repeat one
    docs: list[Document]       # every chunk found so far (numbered [1], [2], ... in this order)
    retries: int
    calculations: list[str]
    structured: Answer
    answer: str
    citations: list[dict]
    steps: list[str]           # human-readable log
    llm_calls: int


# ---------- prompts ----------
PLAN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You plan searches over SEC 10-K filings.\n\nAvailable filings (company: fiscal years):\n{filings}\n\n"
               "List every fact needed to answer the question, and one search per fact. Write searches in 10-K "
               "wording (line items, statement names). Prefer the filing for the year asked; a filing for year N "
               "also reports year N-1. For comparisons, search each company or year. If the question says where a "
               "number comes from (e.g. 'from the cash flow statement'), put that statement or section in the "
               "search, e.g. 'cash flow statement depreciation and amortization'. Max 6 searches."),
    ("human", "{question}"),
])

GRADE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You check whether search results contain every fact needed to answer a question.\n\n"
               "Available filings (company: fiscal years):\n{filings}\n\n"
               "A fact counts as FOUND if its value appears under any equivalent name (e.g. 'operating profit' "
               "= 'operating income', 'net revenue' = 'net sales'). A fact is MISSING if it is not in the "
               "results, or if the question requires a specific source (e.g. the cash flow statement) and the "
               "value only appears somewhere else.\n"
               "List only the missing facts. For each one, write a new search that is different from the "
               "searches already run: use other 10-K wording or name the statement or note it appears in. "
               "If everything is present, return empty lists."),
    ("human", "Question: {question}\n\nFacts needed:\n{facts}\n\nSearches already run:\n{done}\n\n"
              "Search results:\n\n{context}"),
])

CALC_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "If answering the question needs arithmetic, write each calculation using plain numbers copied "
               "from the search results (no $ or commas). If no arithmetic is needed, return no items."),
    ("human", "Question: {question}\n\nSearch results:\n\n{context}"),
])


def _search_key(s: Search) -> str:
    return f"{s.company} {s.fiscal_year}: {s.query.strip().lower()}"


def _context(docs: list[Document]) -> str:
    return format_numbered([d.page_content for d in docs], [source_label(d) for d in docs])


def build_graph(helper_model: str | None = None, answer_model: str | None = None):
    helper = chat_model(helper_model or settings.chat_model)        # cheap: plan
    answerer = chat_model(answer_model or settings.answer_model)    # strong: grade + calculate + answer
    filings = "\n".join(f"- {c}: {', '.join(map(str, ys))}" for c, ys in available_filings().items())

    def plan(state: GraphState) -> GraphState:
        p = (PLAN_PROMPT | helper.with_structured_output(Plan)).invoke(
            {"filings": filings, "question": state["question"]})
        return {"facts": p.facts, "pending": p.searches, "docs": [], "done": [], "retries": 0,
                "steps": [f"plan: {len(p.facts)} facts, {len(p.searches)} searches"], "llm_calls": 1}

    def retrieve(state: GraphState) -> GraphState:
        docs, steps, available = list(state["docs"]), list(state["steps"]), available_filings()
        done = list(state["done"])
        seen = {doc_key(d) for d in docs}
        for s in state["pending"][:MAX_SEARCHES_PER_ROUND]:
            key = _search_key(s)
            if key in done:                       # never run the same search twice
                steps.append(f"skip (already searched): {key}")
                continue
            done.append(key)
            if s.company not in available or s.fiscal_year not in available[s.company]:
                steps.append(f"skip (no such filing): {s.company} {s.fiscal_year}")
                continue
            flt = to_pg_filter(QueryFilters(company=s.company, fiscal_year=s.fiscal_year))
            for d in _store().similarity_search(s.query, k=RESULTS_PER_SEARCH, filter=flt):
                if doc_key(d) not in seen:
                    seen.add(doc_key(d))
                    docs.append(d)
            steps.append(f"search: {s.company} {s.fiscal_year} - {s.query!r}")
        return {"docs": docs, "done": done, "pending": [], "steps": steps}

    def grade(state: GraphState) -> GraphState:
        g = (GRADE_PROMPT | answerer.with_structured_output(Grade)).invoke({
            "filings": filings, "question": state["question"],
            "facts": "\n".join(f"- {f}" for f in state["facts"]),
            "done": "\n".join(f"- {d}" for d in state["done"]), "context": _context(state["docs"])})
        new = [x for x in g.searches if _search_key(x) not in state["done"]]   # drop repeats before retrying
        steps = state["steps"] + [f"grade: missing {g.missing}" if g.missing else "grade: all facts found"]
        retry = bool(g.missing and new) and state["retries"] < MAX_RETRIES
        return {"pending": new if retry else [], "retries": state["retries"] + int(retry),
                "steps": steps, "llm_calls": state["llm_calls"] + 1}

    def calculate(state: GraphState) -> GraphState:
        c = (CALC_PROMPT | answerer.with_structured_output(Calculations)).invoke(
            {"question": state["question"], "context": _context(state["docs"])})
        results, steps = [], list(state["steps"])
        for item in c.items:
            try:
                value = round(_eval(ast.parse(item.expression.replace(",", ""), mode="eval").body), 6)
                results.append(f"{item.label}: {item.expression} = {value}")
            except Exception as e:
                results.append(f"{item.label}: {item.expression} = error ({e})")
            steps.append(f"calculator: {results[-1]}")
        return {"calculations": results, "steps": steps, "llm_calls": state["llm_calls"] + 1}

    def generate(state: GraphState) -> GraphState:
        question = state["question"]
        if state["calculations"]:
            question += "\n\nCalculator results (exact; use these numbers):\n" + "\n".join(state["calculations"])
        ans = (STRUCTURED_PROMPT | answerer.with_structured_output(Answer)).invoke(
            {"context": _context(state["docs"]), "question": question})
        return {"structured": ans, "llm_calls": state["llm_calls"] + 1}

    def check(state: GraphState) -> GraphState:
        """Grounding check in code: an 'answerable' answer must have at least one verified quote."""
        docs, ans = state["docs"], state["structured"]
        labels = [source_label(d) for d in docs]
        citations = verify_citations(ans, [d.page_content for d in docs], labels)
        if ans.answerable and not any(c["verified"] for c in citations):
            return {"answer": REFUSAL, "citations": citations,
                    "steps": state["steps"] + ["check: no verified citation -> refuse"]}
        return {"answer": render(ans, labels), "citations": citations,
                "steps": state["steps"] + [f"check: {sum(c['verified'] for c in citations)}/{len(citations)} verified"]}

    def after_grade(state: GraphState) -> str:
        return "retrieve" if state["pending"] else "calculate"

    g = StateGraph(GraphState)
    for name, fn in [("plan", plan), ("retrieve", retrieve), ("grade", grade),
                     ("calculate", calculate), ("generate", generate), ("check", check)]:
        g.add_node(name, fn)
    g.add_edge(START, "plan")
    g.add_edge("plan", "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", after_grade, {"retrieve": "retrieve", "calculate": "calculate"})
    g.add_edge("calculate", "generate")
    g.add_edge("generate", "check")
    g.add_edge("check", END)
    return g.compile()


def answer_with_graph(question: str, config: dict | None = None, **models) -> dict:
    out = build_graph(**models).invoke({"question": question}, config=config)
    return {
        "answer": out["answer"],
        "citations": out["citations"],
        "docs": out["docs"],
        "steps": out["steps"],
        "n_searches": sum(s.startswith("search:") for s in out["steps"]),
        "n_calculations": len(out["calculations"]),
        "llm_calls": out["llm_calls"],
    }