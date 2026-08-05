"""
AURA Chat -- the in-app analytics assistant.

POC approach: ten leadership-relevant Q&A pairs are hardcoded below (answers
pre-written from real analysis of the dataset), since the free-tier Groq API
was giving inconsistent answers. Typed questions are fuzzy-matched against
these ten; the first two are also offered as one-click suggestion chips.
Anything that doesn't match falls back to the existing LLM/rule-based path
(so the chat still responds to other questions, just without the same
guaranteed answer quality). Scope stays locked to the dataset via the
existing off-topic blocklist for anything that reaches the fallback path.

UX: the user's question appears in the chat immediately on submit; the
answer is generated in a second pass and the page reruns once more to show
it (see render_copilot()'s two-phase append-then-fill pattern).
"""

from __future__ import annotations

import difflib

import pandas as pd
import streamlit as st

from src.services import llm_service
from src.services.insights_service import build_structured_summary
from src.utils.html import compact_html

_HISTORY_KEY = "aura_copilot_history"

_OFF_TOPIC_REPLY = "I can only answer questions about this ticket dataset."
_OFF_TOPIC_ACTION = "Try asking about SLA, resolution time, priority, categories, agents, or countries."

_OFF_TOPIC_PATTERNS = (
    "weather", "joke", "poem", "song lyrics", "recipe", "capital of",
    "president of", "prime minister", "write code", "write a python",
    "translate", "movie", "sports score", "stock price", "news today",
    "who are you", "how are you", "what is your name", "your favorite",
    "tell me a story", "meaning of life",
)

# ---------------------------------------------------------------------------
# Hardcoded POC Q&A -- pre-written from real analysis of the dataset.
# The first two are offered as one-click suggestion chips.
# ---------------------------------------------------------------------------
QA_PAIRS: list[dict] = [
    {
        "question": "Which assignment groups are handling the highest volume of critical incidents?",
        "answer": (
            "Desktop Support handles the most critical incidents (538), followed by "
            "Identity &amp; Access Management (264), Server Support (259), Network Operations (258), "
            "and Service Desk (253). Desktop Support appears to carry a significantly larger share "
            "of critical work."
        ),
        "action": "Review Desktop Support staffing given its outsized share of critical incidents.",
    },
    {
        "question": "What are the top incident categories driving operational risk across countries?",
        "answer": (
            "Across all countries, the largest incident categories are Application, Access Management, "
            "Email, Hardware, and Server. These should be the primary focus for service improvement "
            "initiatives."
        ),
        "action": "Prioritize root-cause reduction on Application and Access Management incidents.",
    },
    {
        "question": "Which countries experience the highest number of High/Critical incidents?",
        "answer": (
            "United States (356) leads, followed by Germany (353), Canada (343), India (331), and "
            "Brazil (326). The distribution is fairly balanced, indicating global operational demand "
            "rather than a single regional hotspot."
        ),
        "action": "Ensure regional support coverage is balanced across these top five countries.",
    },
    {
        "question": "What percentage of incidents remain unresolved or on hold?",
        "answer": (
            "Current workflow states are: Closed 2,056, Resolved 2,024, New 2,006, In Progress 1,973, "
            "On Hold 1,941. Nearly 39% of incidents are still either New or In Progress, while another "
            "19% are On Hold, suggesting opportunities to reduce backlog and improve flow efficiency."
        ),
        "action": "Investigate why nearly 1 in 5 tickets are stuck On Hold.",
    },
    {
        "question": "Which configuration items generate the most recurring incidents?",
        "answer": (
            "No configuration item is a dominant problem source. The highest occurrence for any single "
            "CI is only 3 incidents, suggesting incidents are widely distributed across infrastructure "
            "rather than concentrated on a few assets."
        ),
        "action": "No single-asset remediation needed; focus on category-level fixes instead.",
    },
    {
        "question": "Are critical incidents resolved faster than lower-priority incidents?",
        "answer": (
            "Yes. Average resolution times are: Critical 21.4 hrs, Moderate 22.0 hrs, High 22.7 hrs, "
            "Low 23.2 hrs. Critical incidents receive the fastest response, indicating prioritization "
            "is working as intended."
        ),
        "action": "Continue current priority-based triage; it's working as designed.",
    },
    {
        "question": "Which assignment groups have the largest backlog of open incidents?",
        "answer": (
            "Desktop Support (1,188) has the largest open backlog, followed by Application Support (633), "
            "Service Desk (622), Network Operations (613), and Messaging Support (605). Desktop Support "
            "should be reviewed for workload balancing or staffing."
        ),
        "action": "Prioritize backlog reduction efforts on Desktop Support.",
    },
    {
        "question": "Who are the top-performing analysts by incident resolution volume?",
        "answer": (
            "Highest resolution volumes are: David Lee (223), James Anderson (223), Daniel Kim (213), "
            "Emily Carter (213), and Carlos Gomez (206). These analysts consistently close the largest "
            "number of incidents."
        ),
        "action": "Consider these analysts for best-practice sharing or mentoring.",
    },
    {
        "question": "Which incident categories contribute the largest workload?",
        "answer": (
            "Application (1,037), Access Management (1,030), Email (1,029), Hardware (1,021), and "
            "Server (1,016). These categories represent the greatest opportunity for automation and "
            "root-cause reduction."
        ),
        "action": "Evaluate automation opportunities for the top 5 categories.",
    },
    {
        "question": "What trends are visible in incident creation over time?",
        "answer": (
            "Incident volume gradually declines over the available timeline, with later months showing "
            "fewer records than earlier periods. This could indicate improving operational stability or "
            "simply reflect that the dataset ends before those months are complete, so additional context "
            "would be needed before drawing firm conclusions."
        ),
        "action": "Confirm whether the decline reflects real improvement or incomplete late-period data.",
    },
]

SUGGESTED_QUESTIONS = [QA_PAIRS[0]["question"], QA_PAIRS[1]["question"]]


def _normalize(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return " ".join(cleaned.split())


def _match_hardcoded(question: str) -> dict | None:
    """Fuzzy-match a typed question against the ten hardcoded Q&A pairs, so
    close paraphrasing still hits the pre-written answer, not just exact text."""
    normalized_q = _normalize(question)
    if not normalized_q:
        return None

    candidates = {_normalize(qa["question"]): qa for qa in QA_PAIRS}

    close = difflib.get_close_matches(normalized_q, candidates.keys(), n=1, cutoff=0.55)
    if close:
        return candidates[close[0]]

    # Fallback: keyword-overlap match for shorter/differently-phrased questions.
    q_words = set(normalized_q.split())
    best_match, best_score = None, 0.0
    for norm_q, qa in candidates.items():
        cand_words = set(norm_q.split())
        if not cand_words:
            continue
        overlap = len(q_words & cand_words) / len(cand_words)
        if overlap > best_score:
            best_match, best_score = qa, overlap
    return best_match if best_score >= 0.5 else None


def _is_on_topic(question: str) -> bool:
    q = question.lower()
    return not any(pattern in q for pattern in _OFF_TOPIC_PATTERNS)


def _fallback_answer(question: str, summary: dict) -> tuple[str, str]:
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
        "surface the most relevant trend or risk, and end with a concrete implication. "
        "Then on a new line write 'Action: ' followed by one concrete next step (under 15 words)."
    )
    system_prompt = (
        "You are AURA Chat, an enterprise ITSM analytics assistant used by IT leadership. "
        "You answer ONLY questions about the ticket data supplied to you. Refuse anything "
        "off-topic with exactly: 'I can only answer questions about this ticket dataset.'"
    )
    raw = llm_service.ask(prompt, system_prompt=system_prompt)
    if "Action:" in raw:
        answer_part, action_part = raw.split("Action:", 1)
        return answer_part.strip(), action_part.strip()
    return raw.strip(), "Ask about SLA, resolution time, open tickets, or CSAT for more depth."


def _generate_answer(question: str, df: pd.DataFrame) -> tuple[str, str]:
    hardcoded = _match_hardcoded(question)
    if hardcoded:
        return hardcoded["answer"], hardcoded["action"]

    if not _is_on_topic(question):
        return _OFF_TOPIC_REPLY, _OFF_TOPIC_ACTION

    summary = build_structured_summary(df)
    try:
        if llm_service.is_llm_available():
            return _llm_answer(question, summary)
        return _fallback_answer(question, summary)
    except Exception:
        return _fallback_answer(question, summary)


def _submit_question(question: str) -> None:
    st.session_state[_HISTORY_KEY].append({"question": question, "answer": None, "action": None})


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

        if not st.session_state[_HISTORY_KEY]:
            st.caption("Try asking:")
            col1, col2 = st.columns(2)
            with col1:
                if st.button(SUGGESTED_QUESTIONS[0], use_container_width=True, key="aura_suggest_0"):
                    _submit_question(SUGGESTED_QUESTIONS[0])
                    st.rerun()
            with col2:
                if st.button(SUGGESTED_QUESTIONS[1], use_container_width=True, key="aura_suggest_1"):
                    _submit_question(SUGGESTED_QUESTIONS[1])
                    st.rerun()

    question = st.chat_input("Ask AURA about this data...")
    if question:
        _submit_question(question)
        st.rerun()

    pending = [turn for turn in st.session_state[_HISTORY_KEY] if turn["answer"] is None]
    if pending:
        turn = pending[-1]
        turn["answer"], turn["action"] = _generate_answer(turn["question"], df)
        st.rerun()