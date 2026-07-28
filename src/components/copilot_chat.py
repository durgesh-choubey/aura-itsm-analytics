"""
AI Copilot chat panel.

Renders at the bottom of the page. Every answer is grounded in the same
structured summary dict used by the Executive Brief (see
src/services/insights_service.build_structured_summary), so the assistant
reasons over real filtered numbers instead of the raw dataset.

Scope is deliberately locked down: the copilot only answers questions about
the loaded ticket dataset (SLA, resolution, priority, categories, agents,
countries, trends). Anything else gets a short, direct refusal instead of
being sent to the LLM -- both to keep answers on-topic and to avoid burning
API calls on small talk / unrelated questions.
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

_DATASET_KEYWORDS = (
    "ticket", "sla", "resolution", "resolve", "resolved", "csat", "satisf",
    "priority", "critical", "category", "state", "status", "country",
    "agent", "assign", "open", "closed", "volume", "incident", "trend",
    "group", "p1", "p2", "p3", "p4", "backlog", "breach", "compliance",
)


def _is_on_topic(question: str) -> bool:
    q = question.lower()
    return any(keyword in q for keyword in _DATASET_KEYWORDS)


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
        top_category = summary["top_categories"][0]["category"] if summary["top_categories"] else "N/A"
        answer = f"Top category is '{top_category}'; SLA compliance is {summary['sla_compliance_pct']}%."
        action = "Ask about SLA, resolution time, open tickets, or CSAT."
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

    with st.container(border=True):
        st.markdown(
            compact_html(
                """
                <div class="aura-copilot-header">
                    <span class="dot"></span>
                    <strong>AI Copilot</strong>
                    <span style="color: var(--aura-text-secondary); font-size: 0.82rem;">
                        — ask about SLA, resolution time, CSAT, or trends in the filtered data
                    </span>
                </div>
                """
            ),
            unsafe_allow_html=True,
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
                if llm_service.is_llm_available():
                    answer, action = _llm_answer(question, summary)
                else:
                    answer, action = _fallback_answer(question, summary)
            except Exception:
                answer, action = _fallback_answer(question, summary)

        st.session_state[_HISTORY_KEY].append({"question": question, "answer": answer, "action": action})
        st.rerun()
