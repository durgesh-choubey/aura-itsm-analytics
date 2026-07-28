"""
Header component.

This module owns two responsibilities on purpose, grouped together because
they both run exactly once at the top of the page:

1. `inject_global_styles()` — loads assets/styles.css and sets the page config
   (browser tab title/icon). This is the ONLY place CSS is injected.
2. `render_header()` — renders the ONE visible "AURA" heading on the page.

No other component should render the app name as a heading. Sidebar, charts,
and the copilot panel refer to the platform generically (e.g. "PULSE Portal")
instead of repeating "AURA" as a title.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.config import (
    APP_FULL_NAME,
    APP_ICON,
    APP_NAME,
    APP_TAGLINE,
    PAGE_TITLE,
    PARENT_PLATFORM,
)
from src.utils.html import compact_html

_STYLES_PATH = Path(__file__).resolve().parents[2] / "assets" / "styles.css"


def inject_global_styles() -> None:
    """Set page config and inject the global stylesheet. Call once, first, in app.py."""
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    css = _STYLES_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def render_header(last_refreshed: str | None = None) -> None:
    """Render the single AURA title card, framed as a module inside PULSE."""
    refreshed_html = (
        f'<span class="aura-breadcrumb">Last refreshed: <b>{last_refreshed}</b></span>'
        if last_refreshed
        else f'<span class="aura-breadcrumb"><b>{PARENT_PLATFORM}</b> Portal · ITSM Analytics Module</span>'
    )

    html = f"""
        <div class="aura-card aura-header">
            <div class="aura-header-titleblock">
                <div class="aura-header-icon">🤖</div>
                <div>
                    <p class="aura-header-name">{APP_NAME}</p>
                    <p class="aura-header-subtitle">{APP_FULL_NAME} — {APP_TAGLINE}</p>
                </div>
            </div>
            {refreshed_html}
        </div>
    """
    st.markdown(compact_html(html), unsafe_allow_html=True)
