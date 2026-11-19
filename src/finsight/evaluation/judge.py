"""LLM-as-judge: grade a FinSight answer against the FinanceBench reference answer."""

from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from finsight.config import settings


class Verdict(BaseModel):
    verdict: Literal["correct", "partial", "wrong", "refused"]
    reason: str = Field(description="One sentence explaining the verdict")


JUDGE_SYSTEM = """You grade answers from a financial question-answering system \
against a reference answer written by finance experts.

Verdicts:
- correct: same key facts, numbers or conclusion as the reference. Ignore wording,
  formatting and small rounding differences ($1,577 million = $1.58 billion).
  For yes/no style questions the answer must reach the same conclusion.
- partial: on the right track but incomplete, a key number noticeably off,
  or the right conclusion with wrong supporting numbers.
- wrong: different facts, numbers or conclusion, or invented information.
- refused: the answer says it could not find the information.

Special case: if the REFERENCE says the information cannot be found in the filings,
then a refusal is "correct" and any concrete answer is "wrong".
"""

JUDGE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", JUDGE_SYSTEM),
        ("human", "Question:\n{question}\n\nReference answer:\n{reference}\n\nSystem answer:\n{answer}"),
    ]
)


def build_judge():
    model = init_chat_model(settings.judge_model, temperature=0)
    return JUDGE_PROMPT | model.with_structured_output(Verdict)