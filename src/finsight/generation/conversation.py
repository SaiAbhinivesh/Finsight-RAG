"""Conversations: rewrite follow-ups into standalone questions; keep history in Postgres."""

import uuid
from functools import lru_cache

import psycopg
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_postgres import PostgresChatMessageHistory

from finsight.config import settings
from finsight.generation.models import chat_model

HISTORY_TABLE = "chat_history"
MAX_HISTORY_MESSAGES = 6  # last 3 question/answer pairs are enough context to resolve a follow-up

CONDENSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system",
         "Rewrite the user's latest message as a standalone question that can be understood without "
         "the conversation. Make the company, fiscal year and metric explicit, carrying them over from "
         "the conversation when the user refers to them implicitly (e.g. 'and in 2021?', 'what about Boeing?'). "
         "If the message is already standalone, return it unchanged. Reply with the question only."),
        MessagesPlaceholder("history"),
        ("human", "{question}"),
    ]
)


@lru_cache
def _condenser():
    return CONDENSE_PROMPT | chat_model(settings.chat_model) | StrOutputParser()


def condense(question: str, history: list[BaseMessage], config: dict | None = None) -> str:
    """Standalone version of the question. First turn (no history): returned unchanged, no LLM call.
    `config` passes callbacks (e.g. usage tracking) and tracing settings to the LLM call."""
    if not history:
        return question
    return _condenser().invoke({"history": history[-MAX_HISTORY_MESSAGES:], "question": question},
                               config=config).strip()


def open_history(session_id: str | None = None) -> tuple[PostgresChatMessageHistory, str]:
    """Open (or start) a conversation stored in Postgres. Returns (history, session_id)."""
    session_id = session_id or str(uuid.uuid4())
    conn = psycopg.connect(settings.psycopg_url)
    PostgresChatMessageHistory.create_tables(conn, HISTORY_TABLE)  # no-op if it exists
    return PostgresChatMessageHistory(HISTORY_TABLE, session_id, sync_connection=conn), session_id