"""
Dataset loading.

Two sources feed the app, both normalized to the same canonical schema
(see src/data/schema.py) so every downstream component is source-agnostic:

1. Backend dataset -- any single .csv/.xlsx file dropped into the `data/`
   folder (e.g. `data/ITSM Dataset.csv`). Auto-mapped to canonical columns
   using the same heuristics as uploads. Falls back to a seeded synthetic
   dataset if no file is present, so the app still runs out of the box.
2. Uploaded file -- read raw, auto-mapped, then user-confirmed via the
   mapping UI in src/components/data_source.py.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from src.config import DEFAULT_TICKET_COUNT
from src.data.schema import CANONICAL_FIELDS, DATE_FIELDS, auto_map_columns

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls")

_PRIORITIES = ["1 - Critical", "2 - High", "3 - Medium", "4 - Low"]
_PRIORITY_WEIGHTS = [0.08, 0.22, 0.42, 0.28]
_STATES = ["New", "In Progress", "On Hold", "Resolved", "Closed", "Cancelled"]
_STATE_WEIGHTS = [0.08, 0.12, 0.06, 0.22, 0.48, 0.04]
_CATEGORIES = ["Server", "Network", "Database", "Application", "Hardware", "Access Management", "Security"]
_ASSIGNMENT_GROUPS = ["Server Support", "Network Support", "Application Support", "Security", "IT Operations", "Service Desk"]
_OWNED_BY = ["Service Desk", "IT Operations", "Server Support", "Network Support"]
_COUNTRIES = ["United States", "India", "United Kingdom", "Germany", "Singapore", "Australia", "Canada"]
_FIRST_NAMES = ["Aarav", "Kevin", "Sara", "Victor", "Priya", "Wei", "Fatima", "Diego", "Anna", "Noah"]
_LAST_NAMES = ["Kapoor", "Taylor", "Ahmed", "Hugo", "Sharma", "Chen", "Khan", "Garcia", "Muller", "Smith"]


_CSV_ENCODING_FALLBACKS = ("utf-8", "utf-8-sig", "cp1252", "latin-1")


def _read_csv_robust(source) -> tuple[pd.DataFrame, int]:
    """Returns (dataframe, skipped_row_count). See docstring context above:
    tries encodings in order, and if the file itself has ragged/malformed
    rows, retries leniently and counts how many rows had to be dropped so
    the caller can warn the user instead of silently losing data.
    """
    last_error: Exception | None = None
    working_encoding: str | None = None

    for encoding in _CSV_ENCODING_FALLBACKS:
        try:
            if hasattr(source, "seek"):
                source.seek(0)
            return pd.read_csv(source, encoding=encoding), 0
        except (UnicodeDecodeError, UnicodeError) as exc:
            last_error = exc
            continue
        except pd.errors.ParserError as exc:
            # Encoding is fine -- the file itself has ragged rows. Stop
            # cycling encodings and fall through to the lenient retry below.
            working_encoding = encoding
            last_error = exc
            break

    if working_encoding is not None:
        try:
            if hasattr(source, "seek"):
                source.seek(0)
            bad_lines: list = []
            df = pd.read_csv(
                source, encoding=working_encoding, engine="python",
                on_bad_lines=lambda bad_line: bad_lines.append(bad_line) or None,
            )
            return df, len(bad_lines)
        except Exception as exc:
            last_error = exc

    raise last_error


def _find_backend_dataset_file() -> Path | None:
    """Return the first supported data file found in data/, if any."""
    if not _DATA_DIR.exists():
        return None
    candidates = sorted(
        p for p in _DATA_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _SUPPORTED_EXTENSIONS and not p.name.startswith(".")
    )
    return candidates[0] if candidates else None


def _read_file_from_path(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df, skipped = _read_csv_robust(path)
        df.attrs["skipped_rows"] = skipped
        return df
    df = pd.read_excel(path)
    df.attrs["skipped_rows"] = 0
    return df


@st.cache_data(show_spinner="Generating sample ticket data...")
def _generate_synthetic_tickets(n_tickets: int = DEFAULT_TICKET_COUNT) -> pd.DataFrame:
    """Seeded synthetic dataset shaped like the real ITSM export schema.
    Used only as a fallback when no file exists in data/."""
    rng = np.random.default_rng(seed=42)

    created = pd.Timestamp("2028-01-01") + pd.to_timedelta(
        rng.integers(0, 180 * 24 * 60, size=n_tickets), unit="m"
    )

    priority = rng.choice(_PRIORITIES, size=n_tickets, p=_PRIORITY_WEIGHTS)
    state = rng.choice(_STATES, size=n_tickets, p=_STATE_WEIGHTS)

    target_hours = {"1 - Critical": 4, "2 - High": 8, "3 - Medium": 24, "4 - Low": 72}
    base_hours = np.array([target_hours[p] for p in priority])
    resolution_hours = np.abs(rng.normal(loc=base_hours * 0.7, scale=base_hours * 0.4))

    is_resolved = np.isin(state, ["Resolved", "Closed"])
    resolved = pd.Series(created + pd.to_timedelta(resolution_hours, unit="h")).where(is_resolved)
    closed = pd.Series(resolved + pd.to_timedelta(rng.integers(0, 6, size=n_tickets), unit="h")).where(
        state == "Closed"
    )

    people = [f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}" for _ in range(n_tickets)]
    assignees = [f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}" for _ in range(n_tickets)]

    df = pd.DataFrame({
        "number": [f"INC{100000 + i}" for i in range(n_tickets)],
        "initiator": people,
        "created": created,
        "short_description": rng.choice(
            ["Server patch pending", "Network latency reported", "Application error on login",
             "Database connection timeout", "Access request pending", "Hardware failure reported"],
            size=n_tickets,
        ),
        "work_notes": "Reviewed alerts and diagnostics for the incident.",
        "resolution_notes": np.where(
            is_resolved, "Resolved following the approved operational procedure.", ""
        ),
        "priority": priority,
        "state": state,
        "category": rng.choice(_CATEGORIES, size=n_tickets),
        "assignment_group": rng.choice(_ASSIGNMENT_GROUPS, size=n_tickets),
        "assigned_to": assignees,
        "configuration_item": [f"CI-{rng.integers(10000, 99999)}" for _ in range(n_tickets)],
        "host_name": [f"HOST-{rng.integers(10000, 99999)}" for _ in range(n_tickets)],
        "master_incident": "",
        "owned_by": rng.choice(_OWNED_BY, size=n_tickets),
        "resolved": resolved,
        "closed": closed,
        "country": rng.choice(_COUNTRIES, size=n_tickets),
    })

    return df.sort_values("created").reset_index(drop=True)


@st.cache_data(show_spinner="Loading backend ticket data...")
def load_backend_dataset() -> tuple[pd.DataFrame, str, int]:
    """Return (dataframe, label, skipped_row_count) for the app's default dataset.

    Prefers a real file dropped into data/ (e.g. data/ITSM Dataset.csv),
    auto-mapped to the canonical schema exactly like an upload. Falls back
    to a seeded synthetic dataset if no file is present.
    """
    backend_file = _find_backend_dataset_file()
    if backend_file is not None:
        raw_df = _read_file_from_path(backend_file)
        skipped = raw_df.attrs.get("skipped_rows", 0)
        mapping = auto_map_columns(list(raw_df.columns))
        canonical_df = apply_column_mapping(raw_df, mapping)
        return canonical_df, backend_file.stem, skipped
    return _generate_synthetic_tickets(), "Sample Data (synthetic)", 0


# Backwards-compatible alias used by components/data_source.py's synthetic-only reset path.
def load_sample_tickets(n_tickets: int = DEFAULT_TICKET_COUNT) -> pd.DataFrame:
    return _generate_synthetic_tickets(n_tickets)


def read_uploaded_file(uploaded_file) -> pd.DataFrame:
    """Read an uploaded CSV or Excel file into a raw (un-mapped) DataFrame.
    Sets df.attrs['skipped_rows'] if any malformed CSV rows had to be dropped."""
    name = uploaded_file.name.lower()
    raw_bytes = uploaded_file.read()
    buffer = io.BytesIO(raw_bytes)

    if name.endswith(".csv"):
        df, skipped = _read_csv_robust(buffer)
        df.attrs["skipped_rows"] = skipped
        return df
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(buffer)
        df.attrs["skipped_rows"] = 0
        return df
    raise ValueError("Unsupported file type. Please upload a .csv or .xlsx file.")


def apply_column_mapping(raw_df: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
    """Rename raw columns to canonical names per `mapping` ({raw_col: canonical_or_None}),
    drop unmapped columns, and coerce types (dates parsed, blanks -> NaN)."""
    keep = {raw: canonical for raw, canonical in mapping.items() if canonical}
    df = raw_df[list(keep.keys())].rename(columns=keep)

    # Ensure every canonical field exists, even if the upload didn't have it.
    for field in CANONICAL_FIELDS:
        if field.name not in df.columns:
            df[field.name] = pd.NA

    for date_col in DATE_FIELDS:
        try:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce", format="mixed")
        except (TypeError, ValueError):
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    string_cols = [f.name for f in CANONICAL_FIELDS if f.dtype == "string"]
    for col in string_cols:
        df[col] = df[col].astype("string").str.strip()
        df[col] = df[col].replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})

    return df.reset_index(drop=True)


def apply_filters(df: pd.DataFrame, filters: dict[str, list[str]]) -> pd.DataFrame:
    """Apply a dict of {column: [selected values]} filters. Empty list = no filter."""
    filtered = df
    for column, selected_values in filters.items():
        if selected_values and column in filtered.columns:
            filtered = filtered[filtered[column].isin(selected_values)]
    return filtered