"""
AI Copilot chat panel.

Renders at the bottom of the page. Every answer is grounded in the same
structured summary dict used by the Executive Brief (see
src/services/insights_service.build_structured_summary), so the assistant
reasons over real filtered numbers instead of the raw dataset.

Scope is locked to the ticket dataset, but deliberately via a small
BLOCKLIST of obviously-unrelated topics (weather, jokes, general knowledge,
"who are you", etc.) rather than a keyword whitelist. A whitelist rejects
perfectly reasonable questions like "tell me about the data" or "give me an
overall insight" just because they don't contain a specific column name --
the fallback/LLM answers are already grounded in the structured summary
regardless of phrasing, so there's no need to gate on exact keywords.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services import llm_service
from src.services.insights_service import build_structured_summary
from src.utils.html import compact_html

_HISTORY_KEY = "aura_copilot_history"

_OFF_TOPIC_REPLY = "I can only answer questions about this ticket dataset."
_OFF_TOPIC_ACTION = "Try asking about SLA, resolution time, priority, categories, agents, or countries."

# Obviously unrelated topics -- block these, allow everything else through.
_OFF_TOPIC_PATTERNS = (
    "weather", "joke", "poem", "song lyrics", "recipe", "capital of",
    "president of", "prime minister", "write code", "write a python",
    "translate", "movie", "sports score", "stock price", "news today",
    "who are you", "how are you", "what is your name", "your favorite",
    "tell me a story", "meaning of life",
)


def _is_on_topic(question: str) -> bool:
    q = question.lower()
    return not any(pattern in q for pattern in _OFF_TOPIC_PATTERNS)


def _fallback_answer(question: str, summary: dict) -> tuple[str, str]:
    """Deterministic, one-sentence answer + action when no LLM is configured."""
    q = question.lower()
    if "sla" in q or "breach" in q or "compliance" in q:
        answer = f"SLA compliance is {summary['sla_compliance_pct']}%."
        action = "See the SLA Trend chart."
    elif "csat" in q or "satisf" in q:
        if summary["csat_pct"] is not None:
            answer = f"CSAT is {summary['csat_pct']}%."
        else:
            answer = "No CSAT/survey column in this dataset."
        action = "See the satisfaction/state chart."
    elif "resolution" in q or "resolve" in q:
        answer = f"Average resolution time is {summary['avg_resolution_hours']} hours."
        action = "See the SLA Trend chart."
    elif "open" in q or "backlog" in q:
        answer = f"{summary['open_tickets']} tickets are currently open."
        action = "Filter by State to drill in."
    else:
        # Catch-all "tell me about the data" / "overall insight" style questions.
        top_category = summary["top_categories"][0]["category"] if summary["top_categories"] else "N/A"
        answer = (
            f"{summary['total_tickets']} tickets, {summary['sla_compliance_pct']}% SLA compliance, "
            f"top category is '{top_category}'."
        )
        action = "Ask about SLA, resolution time, open tickets, or CSAT for more detail."
    return answer, action


def _llm_answer(question: str, summary: dict) -> tuple[str, str]:
    prompt = (
        f"Structured ITSM ticket summary (already filtered): {summary}\n\n"
        f"Question: {question}\n\n"
        "Rules: Use ONLY the data above. If the question cannot be answered from this "
        "data, respond with exactly: 'I can only answer questions about this ticket dataset.' "
        "Otherwise answer in ONE short, direct sentence -- no preamble, no filler. "
        "Then on a new line write 'Action: ' followed by a single short next step (under 10 words)."
    )
    system_prompt = (
        "You are AURA, an enterprise ITSM analytics copilot. You answer ONLY questions about "
        "the supplied ticket data. You are short, direct, and crisp -- one sentence answers, "
        "no pleasantries, no speculation, no general knowledge. Refuse anything off-topic."
    )
    raw = llm_service.ask(prompt, system_prompt=system_prompt)
    if "Action:" in raw:
        answer_part, action_part = raw.split("Action:", 1)
        return answer_part.strip(), action_part.strip()
    return raw.strip(), "Ask about SLA, resolution time, or CSAT."


def render_copilot(df: pd.DataFrame) -> None:
    if _HISTORY_KEY not in st.session_state:
        st.session_state[_HISTORY_KEY] = []

    llm_on = llm_service.is_llm_available()
    mode_badge = "AI (Groq)" if llm_on else "Rule-based"

    with st.container(border=True):
        st.markdown(
            compact_html(
                f"""
                <div class="aura-copilot-header">
                    <span class="dot"></span>
                    <strong>AI Copilot</strong>
                    <span class="aura-brief-badge">{mode_badge}</span>
                    <span style="color: var(--aura-text-secondary); font-size: 0.82rem;">
                        — ask about SLA, resolution time, CSAT, or trends in the filtered data
                    </span>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        if not llm_on:
            st.caption(
                "Running in rule-based mode -- no GROQ_API_KEY detected. If you added one to "
                ".env, fully restart `streamlit run app.py` (not just a browser refresh); "
                "the connection is cached for the life of the process."
            )

        for turn in st.session_state[_HISTORY_KEY]:
            st.markdown(f'<div class="aura-chat-bubble-user">{turn["question"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="aura-chat-bubble-assistant">{turn["answer"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="aura-chat-action"><b>Action:</b> {turn["action"]}</div>', unsafe_allow_html=True)

    question = st.chat_input("Ask AURA about this data...")
    if question:
        if not _is_on_topic(question):
            answer, action = _OFF_TOPIC_REPLY, _OFF_TOPIC_ACTION
        else:
            summary = build_structured_summary(df)
            try:
                if llm_on:
                    answer, action = _llm_answer(question, summary)
                else:
                    answer, action = _fallback_answer(question, summary)
            except Exception:
                answer, action = _fallback_answer(question, summary)

        st.session_state[_HISTORY_KEY].append({"question": question, "answer": answer, "action": action})
        st.rerun()