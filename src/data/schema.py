"""
Canonical ITSM ticket schema.

Every dataframe used downstream (sample data OR a user-uploaded file) is
normalized to these column names. Components never branch on "is this the
sample dataset or an upload" -- they just read canonical columns, and any
column that a given upload doesn't have is simply absent/None and handled
gracefully by metrics.py / charts.py / sidebar_filters.py.

`CANONICAL_FIELDS` documents every field's label, whether it's required for
the app to function at all, and its type (used for parsing + the mapping UI).
`ALIASES` is a lookup used by `auto_map_columns()` to guess which raw column
in an uploaded file corresponds to which canonical field, based on the
headers you provided (Number, Initiator, Created, Short description, ...).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    name: str            # canonical snake_case name
    label: str            # human-readable label for the mapping UI
    required: bool
    dtype: str            # "string" | "datetime"


CANONICAL_FIELDS: list[FieldSpec] = [
    FieldSpec("number", "Number (Ticket ID)", True, "string"),
    FieldSpec("created", "Created", True, "datetime"),
    FieldSpec("priority", "Priority", True, "string"),
    FieldSpec("state", "State", True, "string"),
    FieldSpec("initiator", "Initiator", False, "string"),
    FieldSpec("short_description", "Short description", False, "string"),
    FieldSpec("work_notes", "Work notes", False, "string"),
    FieldSpec("resolution_notes", "Resolution notes", False, "string"),
    FieldSpec("category", "Category", False, "string"),
    FieldSpec("assignment_group", "Assignment group", False, "string"),
    FieldSpec("assigned_to", "Assigned to", False, "string"),
    FieldSpec("configuration_item", "Configuration item", False, "string"),
    FieldSpec("host_name", "Host name", False, "string"),
    FieldSpec("master_incident", "Master Incident", False, "string"),
    FieldSpec("owned_by", "Owned by", False, "string"),
    FieldSpec("resolved", "Resolved", False, "datetime"),
    FieldSpec("closed", "Closed", False, "datetime"),
    FieldSpec("country", "Country", False, "string"),
    # Optional: only present if the source system tracks CSAT surveys.
    FieldSpec("customer_survey_result", "Customer survey result", False, "string"),
]

REQUIRED_FIELDS = [f.name for f in CANONICAL_FIELDS if f.required]
DATE_FIELDS = [f.name for f in CANONICAL_FIELDS if f.dtype == "datetime"]
FIELD_LABELS = {f.name: f.label for f in CANONICAL_FIELDS}

# Raw header text (lowercased, punctuation-stripped) -> canonical field name.
# Keys here are written as normalize_header() would produce them.
ALIASES: dict[str, str] = {
    "number": "number", "incident number": "number", "ticket number": "number",
    "ticket id": "number", "id": "number",

    "initiator": "initiator", "caller": "initiator", "opened by": "initiator",
    "reported by": "initiator", "requester": "initiator",

    "created": "created", "created time": "created", "opened": "created",
    "opened at": "created", "open time": "created",

    "short description": "short_description", "description": "short_description",
    "summary": "short_description", "subject": "short_description",

    "work notes": "work_notes", "notes": "work_notes", "internal notes": "work_notes",

    "resolution notes": "resolution_notes", "resolution note": "resolution_notes",
    "close notes": "resolution_notes", "closure notes": "resolution_notes",

    "priority": "priority",

    "state": "state", "status": "state",

    "category": "category", "topic": "category", "type": "category",

    "assignment group": "assignment_group", "agent group": "assignment_group",
    "team": "assignment_group", "group": "assignment_group",

    "assigned to": "assigned_to", "agent": "assigned_to", "agent name": "assigned_to",
    "owner": "assigned_to",

    "configuration item": "configuration_item", "ci": "configuration_item",
    "config item": "configuration_item",

    "host name": "host_name", "hostname": "host_name", "server": "host_name",
    "server name": "host_name",

    "master incident": "master_incident", "parent incident": "master_incident",

    "owned by": "owned_by", "support level": "owned_by", "owner group": "owned_by",

    "resolved": "resolved", "resolved time": "resolved", "resolution time": "resolved",
    "resolved at": "resolved",

    "closed": "closed", "closed time": "closed", "close time": "closed",
    "closed at": "closed",

    "country": "country", "location": "country", "region": "country",

    "customer survey result": "customer_survey_result", "csat": "customer_survey_result",
    "survey result": "customer_survey_result", "survey score": "customer_survey_result",
}


def normalize_header(raw_header: str) -> str:
    """'Assignment group' / 'Assignment_Group' / '  Assignment  Group ' -> 'assignment group'."""
    text = re.sub(r"[_\-]+", " ", str(raw_header).strip().lower())
    text = re.sub(r"\s+", " ", text)
    return text


def auto_map_columns(raw_columns: list[str]) -> dict[str, str | None]:
    """Best-effort mapping of raw uploaded column names -> canonical field names.

    Returns {raw_column: canonical_name_or_None}. Columns with no confident
    match map to None and are left for manual mapping / ignored.
    """
    mapping: dict[str, str | None] = {}
    used_canonical: set[str] = set()

    for raw in raw_columns:
        key = normalize_header(raw)
        canonical = ALIASES.get(key)
        if canonical and canonical not in used_canonical:
            mapping[raw] = canonical
            used_canonical.add(canonical)
        else:
            mapping[raw] = None

    return mapping
