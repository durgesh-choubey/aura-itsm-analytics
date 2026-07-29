"""
Data source status card.

For this release, AURA analyzes the backend dataset only -- whatever file is
found in data/ (e.g. data/ITSM Dataset.csv), or a generated synthetic
fallback if none is present. The "upload your own dataset" flow is
temporarily disabled per product decision; the underlying plumbing
(read_uploaded_file, apply_column_mapping, the schema auto-mapper) is left
intact in src/data/loader.py and src/data/schema.py so it can be re-wired
back into this component in a future release without rebuilding it.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data.loader import load_backend_dataset

_STATE_DF_KEY = "aura_active_dataset"
_STATE_LABEL_KEY = "aura_active_dataset_label"
_STATE_SKIPPED_KEY = "aura_active_dataset_skipped_rows"


def _init_session_state() -> None:
    if _STATE_DF_KEY not in st.session_state:
        df, label, skipped = load_backend_dataset()
        st.session_state[_STATE_DF_KEY] = df
        st.session_state[_STATE_LABEL_KEY] = label
        st.session_state[_STATE_SKIPPED_KEY] = skipped


def render_data_source_selector() -> tuple[pd.DataFrame, str]:
    """Render a compact data-source status card and return (active_dataframe, source_label)."""
    _init_session_state()

    with st.container(border=True):
        st.markdown(
            f'<p style="margin:0; font-weight:700; color:var(--aura-text);">Data Source</p>'
            f'<p style="margin:0.15rem 0 0 0; font-size:0.82rem; color:var(--aura-text-secondary);">'
            f'Currently analyzing: <b>{st.session_state[_STATE_LABEL_KEY]}</b> '
            f'({len(st.session_state[_STATE_DF_KEY]):,} tickets)</p>',
            unsafe_allow_html=True,
        )

        skipped = st.session_state.get(_STATE_SKIPPED_KEY, 0)
        if skipped:
            st.warning(
                f"Skipped {skipped} malformed row(s) while reading this file -- likely an "
                "unescaped comma inside a text field (e.g. Short description/Work notes). "
                "Re-export with those fields properly quoted, or as .xlsx, for zero data loss."
            )

    return st.session_state[_STATE_DF_KEY], st.session_state[_STATE_LABEL_KEY]