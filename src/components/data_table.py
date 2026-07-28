"""
Data table + export.

Renders the SAME filtered dataframe the charts use (sidebar filters already
applied upstream in app.py), lets the user pick which columns to show, and
exports exactly what's on screen -- filtered rows x selected columns -- as
CSV. No separate filtering logic here; it reuses whatever the sidebar
filters already produced, so the table and the export always match what
the user is currently looking at.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data.schema import FIELD_LABELS

# A sensible default column set -- the rest are available via the picker
# but hidden by default to keep the table readable at a glance.
_DEFAULT_VISIBLE_COLUMNS = [
    "number", "created", "priority", "state", "category",
    "assignment_group", "assigned_to", "country", "resolved", "closed",
]


def render_data_table(df: pd.DataFrame) -> None:
    st.markdown('<p class="aura-section-title">Data Table</p>', unsafe_allow_html=True)

    with st.container(border=True):
        if df.empty:
            st.info("No tickets match the current filters.")
            return

        available_columns = list(df.columns)
        default_selection = [c for c in _DEFAULT_VISIBLE_COLUMNS if c in available_columns]
        if not default_selection:
            default_selection = available_columns[:8]

        selected_columns = st.multiselect(
            "Columns to show",
            options=available_columns,
            default=default_selection,
            format_func=lambda c: FIELD_LABELS.get(c, c),
            help="Add or remove columns. The CSV export matches exactly what's shown here.",
        )

        display_df = df[selected_columns] if selected_columns else df

        col_count = len(selected_columns) if selected_columns else len(df.columns)
        st.caption(f"{len(display_df):,} rows × {col_count} columns — reflects the filters applied in the sidebar.")

        st.dataframe(display_df, use_container_width=True, height=380)

        csv_bytes = display_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export as CSV",
            data=csv_bytes,
            file_name="aura_filtered_tickets.csv",
            mime="text/csv",
            type="primary",
        )