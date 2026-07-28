"""Sidebar filter panel — Power BI 'slicer' style multiselects."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import CATEGORICAL_FILTERS, PARENT_PLATFORM


def render_sidebar_filters(df: pd.DataFrame) -> dict[str, list[str]]:
    """Render sidebar multiselects for each categorical filter column.

    Returns a dict of {column_name: [selected values]} for use with
    src.data.loader.apply_filters(). An empty list means "no filter applied".
    """
    with st.sidebar:
        st.markdown(
            f'<p class="aura-sidebar-title">Filters</p>',
            unsafe_allow_html=True,
        )

        selections: dict[str, list[str]] = {}
        available_filters = [(c, label) for c, label in CATEGORICAL_FILTERS if c in df.columns]

        if not available_filters:
            st.caption("No filterable columns detected in this dataset.")

        for column, display_label in available_filters:
            options = sorted(df[column].dropna().unique().tolist())
            if not options:
                continue
            selections[column] = st.multiselect(display_label, options=options, default=[])

        st.divider()
        st.caption(f"{PARENT_PLATFORM} · ITSM Analytics Module")

    return selections
