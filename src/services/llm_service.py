"""
Thin wrapper around the Groq (Llama 3.3) chat model via LangChain.

Isolating this here means:
- Components never import langchain/groq directly.
- The rest of the app works (with rule-based fallbacks) even with no API key
  set, which matters for local dev and for anyone forking the repo.
"""

from __future__ import annotations

import os

import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads .env from the project root if present; no-op otherwise
except ImportError:
    pass


def _get_api_key() -> str | None:
    env_key = os.environ.get("GROQ_API_KEY")
    if env_key:
        return env_key
    try:
        return st.secrets.get("GROQ_API_KEY", None)
    except Exception:
        # No secrets.toml file present at all -- perfectly normal for local/dev.
        return None


@st.cache_resource(show_spinner=False)
def get_chat_model():
    """Return a cached LangChain ChatGroq instance, or None if unavailable."""
    api_key = _get_api_key()
    if not api_key:
        return None
    try:
        from langchain_groq import ChatGroq
        return ChatGroq(model="llama-3.3-70b-versatile", api_key=api_key, temperature=0.3)
    except Exception:
        return None


def is_llm_available() -> bool:
    return get_chat_model() is not None


def ask(prompt: str, system_prompt: str | None = None) -> str:
    """Send a prompt to the LLM. Raises if the model isn't configured —
    callers should check is_llm_available() first and use a fallback."""
    model = get_chat_model()
    if model is None:
        raise RuntimeError("LLM not configured: set GROQ_API_KEY to enable AI-generated responses.")

    from langchain_core.messages import HumanMessage, SystemMessage

    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=prompt))

    response = model.invoke(messages)
    return response.content
