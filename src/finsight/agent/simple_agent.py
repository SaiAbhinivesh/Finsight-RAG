"""A tool-using RAG agent (ReAct loop) built with LangChain's create_agent."""

from langchain.agents import create_agent
from langchain.agents.structured_output import StructuredOutputError, ToolStrategy
from langgraph.errors import GraphRecursionError

from finsight.agent.tools import make_tools
from finsight.config import settings
from finsight.generation.chain import source_label
from finsight.generation.models import chat_model
from finsight.generation.structured import REFUSAL, Answer, render, verify_citations
from finsight.retrieval.filters import available_filings

AGENT_PROMPT = """You are FinSight, a financial analyst agent answering questions about companies' \
annual reports (SEC 10-K filings).

Available filings (company: fiscal years):
{filings}

Tools:
- search_filings(query, company, fiscal_year): search one filing. Write the query in 10-K wording.
  Each result has a number like [3].
- calculator(expression): exact arithmetic. Use it for EVERY calculation.

Method:
1. Work out which filings and which facts the question needs. A filing for year N also reports year N-1.
2. Search for each fact. If an input is missing from the results (e.g. depreciation and amortization in the
   cash flow statement, total current liabilities in the balance sheet), search again for exactly that input.
3. For comparisons across companies or years, search each one.
4. Compute with the calculator, then answer. Use at most 6 searches.

Answer rules: start with the direct answer. For calculations show the formula and the inputs. For judgements
give a clear conclusion and a short reason. If something does not exist or is not material, say so plainly.
Cite every fact with its result number [n] and give a short exact quote copied from that result.
If nothing relevant was found: answerable = false and answer = "{refusal}".
"""


def answer_with_agent(question: str, model_name: str | None = None, max_steps: int = 40, config: dict | None = None):
    """Run the agent on one question. Returns answer text, verified citations, the chunks it saw, its tool calls."""
    registry, log = [], []
    filings = "\n".join(f"- {c}: {', '.join(map(str, ys))}" for c, ys in available_filings().items())
    agent = create_agent(
        chat_model(model_name or settings.answer_model),
        tools=make_tools(registry, log),
        system_prompt=AGENT_PROMPT.format(filings=filings, refusal=REFUSAL),
        # Final answer = our M6 Answer object. ToolStrategy returns it as a tool call; if a field is
        # missing, the error goes back to the model and it tries again (handle_errors=True).
        response_format=ToolStrategy(Answer, handle_errors=True),
    )

    try:
        result = agent.invoke({"messages": [{"role": "user", "content": question}]},
                              config={**(config or {}), "recursion_limit": max_steps})
    except GraphRecursionError:
        return {"answer": REFUSAL, "citations": [], "docs": registry, "tool_calls": log, "stopped": "too many steps"}
    except StructuredOutputError as e:
        return {"answer": REFUSAL, "citations": [], "docs": registry, "tool_calls": log, "stopped": f"bad output: {e}"}

    answer = result["structured_response"]
    texts = [d.page_content for d in registry]
    labels = [source_label(d) for d in registry]
    return {
        "answer": render(answer, labels),
        "citations": verify_citations(answer, texts, labels),
        "docs": registry,
        "tool_calls": log,
    }