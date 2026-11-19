"""Structured answers: the model returns an Answer object; code verifies every citation."""

import re

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from finsight.generation.prompts import SYSTEM_PROMPT_V3

REFUSAL = "I could not find this in the provided filings."


class Citation(BaseModel):
    source: int = Field(description="Number of the context block, e.g. 1 for [1]")
    quote: str = Field(description="Short exact quote (max ~25 words) copied word for word from that block")


class Answer(BaseModel):
    answer: str = Field(description="The answer, with [n] markers after the facts they support")
    answerable: bool = Field(description="False only if nothing relevant is in the context")
    citations: list[Citation] = Field(default_factory=list)


STRUCTURED_SYSTEM = SYSTEM_PROMPT_V3 + """
Output format:
- Context blocks are numbered [1], [2], ... Put [n] markers in the answer after the facts they support.
- For every [n] you use, add a citation with that block number and a short quote copied
  word for word from the block (numbers included) that supports the claim.
- If nothing relevant is in the context: answerable = false, answer = "%s", no citations.
""" % REFUSAL

STRUCTURED_PROMPT = ChatPromptTemplate.from_messages(
    [("system", STRUCTURED_SYSTEM), ("human", "Context:\n\n{context}\n\nQuestion: {question}")]
)


def format_numbered(texts: list[str], labels: list[str]) -> str:
    """'[1] [3M 2018, p. 48]' + chunk text, for each retrieved chunk."""
    return "\n\n---\n\n".join(f"[{i}] {label}\n{text}" for i, (text, label) in enumerate(zip(texts, labels), 1))


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def verify_citations(answer: Answer, texts: list[str], labels: list[str]) -> list[dict]:
    """A citation is verified if its block exists and the quote appears in that block's text."""
    results = []
    for c in answer.citations:
        valid_block = 1 <= c.source <= len(texts)
        found = valid_block and _normalize(c.quote) in _normalize(texts[c.source - 1])
        results.append({
            "source": c.source,
            "label": labels[c.source - 1] if valid_block else None,
            "quote": c.quote,
            "verified": bool(found),
        })
    return results


def render(answer: Answer, labels: list[str]) -> str:
    """Replace [n] markers with human-readable source labels for display and judging."""
    if not answer.answerable:
        return REFUSAL
    return re.sub(r"\[(\d+)\]",
                  lambda m: labels[int(m.group(1)) - 1] if 1 <= int(m.group(1)) <= len(labels) else m.group(0),
                  answer.answer)