"""Executive Brief card — AI-generated (or rule-based fallback) insight summary."""

from __future__ import annotations

import streamlit as st

from src.services.insights_service import ExecutiveBrief
from src.utils.html import compact_html


def render_executive_brief(brief: ExecutiveBrief) -> None:
    badge = "AI Generated" if brief.source == "llm" else "Auto-Summary"

    highlight_items = "".join(f"<li>{h}</li>" for h in brief.highlights)

    html = f"""
        <div class="aura-card aura-brief">
            <div class="aura-brief-title">
                Executive Brief
                <span class="aura-brief-badge">{badge}</span>
            </div>
            <p class="aura-brief-section-label">Today's Highlights</p>
            <ul>{highlight_items}</ul>
            <p class="aura-brief-section-label">Recommendation</p>
            <div class="aura-recommendation">{brief.recommendation}</div>
        </div>
    """
    st.markdown(compact_html(html), unsafe_allow_html=True)
