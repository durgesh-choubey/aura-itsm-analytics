"""
Top/bottom scroll navigation.

Enterprise dashboards like Power BI/Fabric are often long single-page
reports; a floating jump-to-top / jump-to-bottom control makes that
navigable without endless manual scrolling.

Implemented with plain HTML anchor links (<a href="#id">) rather than a
JS scrollTo() call. Streamlit strips/won't reliably execute <script> tags
injected via st.markdown, but native in-page anchor navigation is just
browser behavior -- no script execution or Streamlit rerun required, so
it's the reliable choice here. `scroll-behavior: smooth` in styles.css
makes the jump animated rather than instant.
"""

from __future__ import annotations

import streamlit as st

from src.utils.html import compact_html


def render_top_anchor() -> None:
    """Call once, first thing on the page (right after inject_global_styles()).
    Renders the scroll target for "back to top" plus the floating nav buttons
    (position: fixed, so placement in the DOM doesn't matter for the buttons
    themselves -- only the anchor's position matters)."""
    html = """
        <div id="aura-top"></div>
        <div class="aura-scroll-nav">
            <a href="#aura-top" title="Back to top">&#9650;</a>
            <a href="#aura-bottom" title="Go to bottom">&#9660;</a>
        </div>
    """
    st.markdown(compact_html(html), unsafe_allow_html=True)


def render_bottom_anchor() -> None:
    """Call once, last thing on the page (after the Copilot panel)."""
    st.markdown('<div id="aura-bottom"></div>', unsafe_allow_html=True)