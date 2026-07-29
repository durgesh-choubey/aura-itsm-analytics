"""
AURA Chat -- the in-app analytics assistant.

Every answer is grounded in the same structured summary dict used by the
Executive Brief (src/services/insights_service.build_structured_summary),
so it reasons over real filtered numbers rather than the raw dataset or
general knowledge. Scope is locked to the ticket dataset via a small
BLOCKLIST of obviously-unrelated topics (weather, jokes, general trivia)
rather than a keyword whitelist -- a whitelist rejects perfectly reasonable
questions like "tell me about the data" just because they don't contain an
exact column name.

UX: the user's question appears in the chat immediately on submit; the
answer is generated in a second pass and the page reruns once more to show
it. This two-phase append-then-fill pattern is what makes the question show
up right away instead of only appearing once the full answer is ready.
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
    """Descriptive, multi-sentence answer + action when no LLM is configured.
    Every branch pulls in more than one metric so the answer reads like a
    short analyst note, not a single isolated number."""
    q = question.lower()
    total = summary["total_tickets"]
    sla = summary["sla_compliance_pct"]
    top_cat = summary["top_categories"][0]["category"] if summary["top_categories"] else None
    top_group = summary["top_assignment_group"][0]["assignment_group"] if summary["top_assignment_group"] else None

    if "sla" in q or "breach" in q or "compliance" in q:
        gap = 95 - sla
        if sla >= 95:
            answer = (
                f"SLA compliance is {sla}% across {total:,} tickets, at or above the 95% target. "
                f"{summary['open_tickets']:,} tickets remain open, so this is worth revisiting once "
                "they close out."
            )
            action = "Monitor open tickets to confirm SLA holds through resolution."
        else:
            answer = (
                f"SLA compliance is {sla}%, {gap:.1f} points below the 95% target across {total:,} tickets. "
                + (f"{top_group} carries the highest ticket volume, so it's the most likely lever to close this gap. "
                   if top_group else "")
                + f"{summary['open_tickets']:,} tickets are still open and could pull this further down if not prioritized."
            )
            action = f"Review staffing on {top_group or 'the highest-volume group'} to close the SLA gap."
    elif "csat" in q or "satisf" in q:
        if summary["csat_pct"] is not None:
            answer = (
                f"Customer satisfaction (CSAT) is {summary['csat_pct']}% across {total:,} tickets. "
                f"SLA compliance for the same filter is {sla}%, which is a useful cross-check since "
                "slow resolutions typically drag CSAT down."
            )
            action = "Compare CSAT against the SLA Trend chart to spot the correlation."
        else:
            answer = (
                "This dataset has no CSAT/survey column, so satisfaction can't be measured directly. "
                f"As a proxy, SLA compliance is {sla}% and average resolution time is "
                f"{summary['avg_resolution_hours']} hours -- both are leading indicators of satisfaction."
            )
            action = "Add a survey/CSAT column to future exports to track this directly."
    elif "resolution" in q or "resolve" in q:
        answer = (
            f"Average resolution time is {summary['avg_resolution_hours']} hours across {total:,} tickets, "
            f"with SLA compliance at {sla}%. "
            + (f"{top_group} handles the most volume, so its resolution speed disproportionately drives this average. "
               if top_group else "")
            + f"{summary['open_tickets']:,} tickets are still open and not yet reflected in this figure."
        )
        action = "Filter by Assignment Group to see which teams are fastest/slowest."
    elif "open" in q or "backlog" in q:
        pct_open = (summary["open_tickets"] / total * 100) if total else 0
        answer = (
            f"{summary['open_tickets']:,} tickets are currently open, {pct_open:.1f}% of the {total:,} "
            f"tickets in this filtered view. SLA compliance so far is {sla}%"
            + (f", and {top_cat} is the largest contributing category." if top_cat else ".")
        )
        action = "Filter by State in the sidebar to see the open-ticket breakdown by category."
    elif "critical" in q or "p1" in q:
        answer = (
            f"Critical (P1) incidents make up {summary['critical_priority_share_pct']}% of {total:,} tickets. "
            f"Overall SLA compliance is {sla}%, and P1s typically have the tightest resolution targets, "
            "so they're worth tracking separately from the overall average."
        )
        action = "Filter by Priority = Critical to isolate P1 trend and SLA performance."
    else:
        # "Tell me about the data" / "give me an overall insight" style questions.
        answer = (
            f"This view covers {total:,} tickets, with {summary['resolved_tickets']:,} resolved and "
            f"{summary['open_tickets']:,} still open. SLA compliance is {sla}% and average resolution "
            f"time is {summary['avg_resolution_hours']} hours."
            + (f" {top_cat} is the top category" if top_cat else "")
            + (f" and {top_group} carries the highest ticket volume." if top_group else ".")
        )
        action = "Ask about SLA, resolution time, open tickets, critical incidents, or CSAT for more depth."
    return answer, action


def _llm_answer(question: str, summary: dict) -> tuple[str, str]:
    prompt = (
        f"Structured ITSM ticket summary, already filtered to what the user is currently viewing: {summary}\n\n"
        f"Question: {question}\n\n"
        "Answer using ONLY the data above -- do not invent figures. If the question genuinely "
        "cannot be answered from this data, respond with exactly: "
        "'I can only answer questions about this ticket dataset.' "
        "Otherwise write 2-4 sentences: cite specific numbers/percentages from the data, "
        "surface the most relevant trend or risk, and end with a concrete implication -- the kind "
        "of insight an IT operations leader would want in a briefing. No filler, no hedging, no "
        "generic advice like 'monitor closely' unless tied to a specific number. "
        "Then on a new line write 'Action: ' followed by one concrete next step (under 15 words)."
    )
    system_prompt = (
        "You are AURA Chat, an enterprise ITSM analytics assistant used by IT leadership. "
        "You answer ONLY questions about the ticket data supplied to you -- never general "
        "knowledge, opinions, or anything unrelated. Your answers are specific, quantified, "
        "and business-relevant: the kind of analysis a Head of IT Operations would trust in a "
        "leadership briefing. Refuse anything off-topic with exactly: "
        "'I can only answer questions about this ticket dataset.'"
    )
    raw = llm_service.ask(prompt, system_prompt=system_prompt)
    if "Action:" in raw:
        answer_part, action_part = raw.split("Action:", 1)
        return answer_part.strip(), action_part.strip()
    return raw.strip(), "Ask about SLA, resolution time, open tickets, or CSAT for more depth."


def _generate_answer(question: str, df: pd.DataFrame) -> tuple[str, str]:
    if not _is_on_topic(question):
        return _OFF_TOPIC_REPLY, _OFF_TOPIC_ACTION
    summary = build_structured_summary(df)
    try:
        if llm_service.is_llm_available():
            return _llm_answer(question, summary)
        return _fallback_answer(question, summary)
    except Exception:
        return _fallback_answer(question, summary)


def render_copilot(df: pd.DataFrame) -> None:
    if _HISTORY_KEY not in st.session_state:
        st.session_state[_HISTORY_KEY] = []

    with st.container(border=True):
        st.markdown(
            compact_html(
                """
                <div class="aura-copilot-header">
                    <span class="dot"></span>
                    <strong>AURA Chat</strong>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        for turn in st.session_state[_HISTORY_KEY]:
            st.markdown(f'<div class="aura-chat-bubble-user">{turn["question"]}</div>', unsafe_allow_html=True)
            if turn["answer"] is None:
                st.markdown(
                    '<div class="aura-chat-bubble-assistant" style="color: var(--aura-text-secondary);">'
                    "Analyzing the filtered data…</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f'<div class="aura-chat-bubble-assistant">{turn["answer"]}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="aura-chat-action"><b>Action:</b> {turn["action"]}</div>', unsafe_allow_html=True)

    question = st.chat_input("Ask AURA about this data...")
    if question:
        # Phase 1: show the question immediately, answer pending.
        st.session_state[_HISTORY_KEY].append({"question": question, "answer": None, "action": None})
        st.rerun()

    # Phase 2: fill in the answer for whichever turn is still pending (runs on
    # the rerun triggered above, after the "Analyzing..." bubble has already
    # been rendered to the browser).
    pending = [turn for turn in st.session_state[_HISTORY_KEY] if turn["answer"] is None]
    if pending:
        turn = pending[-1]
        turn["answer"], turn["action"] = _generate_answer(turn["question"], df)
        st.rerun()