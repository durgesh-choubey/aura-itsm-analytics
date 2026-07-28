"""
Data source selector.

Rendered as a card right under the header, before KPIs/charts are computed,
since it decides which dataframe the rest of the page analyzes.

Flow for uploads:
  1. User uploads a .csv/.xlsx file.
  2. We auto-map its columns to the canonical schema (src/data/schema.py)
     using header-name heuristics.
  3. We show the detected mapping and let the user fix any field manually
     (only required fields are mandatory; everything else is optional).
  4. On confirm, the mapped + normalized dataframe is stored in
     st.session_state so it survives reruns without re-uploading.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data.loader import apply_column_mapping, load_backend_dataset, read_uploaded_file
from src.data.schema import CANONICAL_FIELDS, REQUIRED_FIELDS

_STATE_DF_KEY = "aura_active_dataset"
_STATE_LABEL_KEY = "aura_active_dataset_label"
_STATE_RAW_KEY = "aura_pending_raw_df"
_STATE_SKIPPED_KEY = "aura_active_dataset_skipped_rows"


def _init_session_state() -> None:
    if _STATE_DF_KEY not in st.session_state:
        df, label, skipped = load_backend_dataset()
        st.session_state[_STATE_DF_KEY] = df
        st.session_state[_STATE_LABEL_KEY] = label
        st.session_state["_backend_label"] = label
        st.session_state[_STATE_SKIPPED_KEY] = skipped


def _render_mapping_ui(raw_df: pd.DataFrame) -> None:
    from src.data.schema import auto_map_columns

    auto_mapping = auto_map_columns(list(raw_df.columns))
    canonical_options = ["-- Ignore --"] + [f.name for f in CANONICAL_FIELDS]
    field_labels = {f.name: f.label for f in CANONICAL_FIELDS}

    detected = sum(1 for v in auto_mapping.values() if v)
    st.success(f"Detected {detected} of {len(raw_df.columns)} columns automatically.")

    with st.expander("Review / adjust column mapping", expanded=False):
        st.caption("Match each column from your file to a field AURA understands. Required fields are marked *.")
        final_mapping: dict[str, str | None] = {}
        for raw_col in raw_df.columns:
            guessed = auto_mapping.get(raw_col)
            label_for_guess = field_labels.get(guessed, "-- Ignore --") if guessed else "-- Ignore --"
            display_options = ["-- Ignore --"] + [f"{f.label}{' *' if f.required else ''}" for f in CANONICAL_FIELDS]
            option_to_field = {"-- Ignore --": None}
            for f in CANONICAL_FIELDS:
                option_to_field[f"{f.label}{' *' if f.required else ''}"] = f.name

            default_display = f"{field_labels[guessed]}{' *' if guessed in REQUIRED_FIELDS else ''}" if guessed else "-- Ignore --"
            choice = st.selectbox(
                f"'{raw_col}' maps to:",
                options=display_options,
                index=display_options.index(default_display) if default_display in display_options else 0,
                key=f"map_{raw_col}",
            )
            final_mapping[raw_col] = option_to_field[choice]

        mapped_required = {v for v in final_mapping.values() if v in REQUIRED_FIELDS}
        missing_required = set(REQUIRED_FIELDS) - mapped_required
        if missing_required:
            missing_labels = ", ".join(field_labels[m] for m in missing_required)
            st.warning(f"Missing required field(s): {missing_labels}. Map a column to each before analyzing.")

        if st.button("Use this dataset", type="primary", disabled=bool(missing_required)):
            canonical_df = apply_column_mapping(raw_df, final_mapping)
            st.session_state[_STATE_DF_KEY] = canonical_df
            st.session_state[_STATE_LABEL_KEY] = st.session_state.get("_pending_filename", "Uploaded dataset")
            st.session_state[_STATE_SKIPPED_KEY] = raw_df.attrs.get("skipped_rows", 0)
            st.session_state.pop(_STATE_RAW_KEY, None)
            st.rerun()


def render_data_source_selector() -> tuple[pd.DataFrame, str]:
    """Render the data-source card and return (active_dataframe, source_label)."""
    _init_session_state()

    with st.container(border=True):
        col_label, col_action = st.columns([3, 2])
        with col_label:
            st.markdown(
                f'<p style="margin:0; font-weight:700; color:var(--aura-text);">Data Source</p>'
                f'<p style="margin:0.15rem 0 0 0; font-size:0.82rem; color:var(--aura-text-secondary);">'
                f'Currently analyzing: <b>{st.session_state[_STATE_LABEL_KEY]}</b> '
                f'({len(st.session_state[_STATE_DF_KEY]):,} tickets)</p>',
                unsafe_allow_html=True,
            )
        with col_action:
            mode = st.radio(
                "Source", options=["Backend Dataset", "Upload my own"],
                horizontal=True, label_visibility="collapsed", key="aura_source_mode",
            )

        skipped = st.session_state.get(_STATE_SKIPPED_KEY, 0)
        if skipped:
            st.warning(
                f"Skipped {skipped} malformed row(s) while reading this file -- likely an "
                "unescaped comma inside a text field (e.g. Short description/Work notes). "
                "Re-export with those fields properly quoted, or as .xlsx, for zero data loss."
            )

        if mode == "Backend Dataset":
            if st.session_state[_STATE_LABEL_KEY] != st.session_state.get("_backend_label"):
                if st.button("Reset to backend dataset"):
                    df, label, skipped = load_backend_dataset()
                    st.session_state[_STATE_DF_KEY] = df
                    st.session_state[_STATE_LABEL_KEY] = label
                    st.session_state[_STATE_SKIPPED_KEY] = skipped
                    st.rerun()
        else:
            uploaded_file = st.file_uploader(
                "Upload a ticket export (.csv or .xlsx)", type=["csv", "xlsx", "xls"],
                label_visibility="collapsed",
            )
            if uploaded_file is not None:
                try:
                    raw_df = read_uploaded_file(uploaded_file)
                    st.session_state["_pending_filename"] = uploaded_file.name
                    _render_mapping_ui(raw_df)
                except Exception as exc:
                    st.error(f"Couldn't read that file: {exc}")

    return st.session_state[_STATE_DF_KEY], st.session_state[_STATE_LABEL_KEY]