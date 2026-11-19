"""Create chat models, handling settings that differ between model families."""

from langchain.chat_models import init_chat_model


def chat_model(name: str):
    """temperature=0 for repeatable answers; reasoning models (gpt-5 family) don't accept it."""
    if "gpt-5" in name:
        return init_chat_model(name)
    return init_chat_model(name, temperature=0)
