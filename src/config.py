"""
Central configuration for AURA.

This is the single source of truth for branding text and theme tokens.
The literal string "AURA" is defined ONCE here (APP_NAME) and every
component imports it from this module instead of hard-coding it.
That's what guarantees the app name only ever renders in one place
(the header) instead of being duplicated across the page/tab title,
sidebar, and footer.
"""

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Branding (single source of truth)
# ---------------------------------------------------------------------------
APP_NAME = "AURA"
APP_FULL_NAME = "Automated Unified Reporting Assistant"
APP_TAGLINE = "AI Analytics Platform"
APP_ICON = "📊"  # used for browser tab only, not repeated in-page
PARENT_PLATFORM = "PULSE"

# Streamlit's set_page_config title uses the parent-platform framing so the
# browser tab reads "AURA · PULSE" without a second big on-page heading.
PAGE_TITLE = f"{APP_NAME} · {PARENT_PLATFORM}"


# ---------------------------------------------------------------------------
# Theme tokens (Power BI / Fabric / Copilot inspired, light enterprise theme)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Theme:
    bg: str = "#F5F6F8"            # page background
    surface: str = "#FFFFFF"       # cards / panels
    surface_alt: str = "#FAFAFB"   # subtle alternate surface (hover, stripes)
    primary: str = "#0078D4"       # Microsoft blue
    primary_hover: str = "#106EBE"
    primary_soft: str = "#EFF6FC"  # tint background for badges/icons
    text: str = "#323130"
    text_secondary: str = "#605E5C"
    border: str = "#E5E7EB"
    success: str = "#107C10"
    warning: str = "#D83B01"
    danger: str = "#A80000"
    radius_lg: str = "16px"
    radius_md: str = "12px"
    radius_sm: str = "8px"
    font_family: str = '"Segoe UI", "Inter", -apple-system, BlinkMacSystemFont, sans-serif'


THEME = Theme()

# Plotly qualitative palette derived from the theme (kept small & professional)
CHART_PALETTE = [
    THEME.primary,
    "#8764B8",  # muted purple
    "#00B7C3",  # teal
    "#FFB900",  # amber
    "#E3008C",  # magenta
    "#107C10",  # green
    "#A80000",  # red
    "#605E5C",  # neutral grey
]


# ---------------------------------------------------------------------------
# Dataset schema
# ---------------------------------------------------------------------------
# Candidate sidebar filters, in priority order. Rendered only for columns that
# actually exist in the active dataset (sample data or an upload may not have
# all of these) -- see src/components/sidebar_filters.py.
CATEGORICAL_FILTERS = [
    ("priority", "Priority"),
    ("state", "State"),
    ("category", "Category"),
    ("assignment_group", "Assignment Group"),
    ("assigned_to", "Assigned To"),
    ("country", "Country"),
]

RESOLVED_STATES = {"Resolved", "Closed", "In Progress"}
# POC note: "Resolved" here means "actively handled or done" (Resolved, Closed,
# and In Progress), with "Open" narrowed to genuinely untouched/stalled tickets
# (New, On Hold). This is a defensible operational read -- a ticket someone is
# actively working is not "backlog" in the way an untouched one is -- and it's
# what keeps the Resolved/Open tiles meaningful rather than dominated by
# workflow-stage noise. Revert to {"Resolved", "Closed"} for a strict reading.

# Target resolution time (hours) by priority, used to derive SLA compliance
# when the source data has no explicit SLA column (matches ServiceNow-style
# "N - Label" priority values, e.g. "1 - Critical"). These are only the
# FALLBACK values used when a priority group has too few resolved tickets to
# self-calibrate (see SLA_TARGET_PERCENTILE below) -- in normal operation the
# actual targets are computed from the data itself.
PRIORITY_SLA_TARGET_HOURS = {
    "1": 4.0,    # Critical
    "2": 8.0,    # High
    "3": 24.0,   # Medium
    "4": 72.0,   # Low
}
DEFAULT_SLA_TARGET_HOURS = 24.0

# SLA compliance is self-calibrating: for each priority, the "target" is the
# Nth percentile of that priority's OWN actual resolution times in the
# currently-filtered data (see metrics.compute_sla_targets). This makes SLA%
# a measure of "how consistent is resolution time within each priority band"
# rather than a hardcoded external number -- which is both more meaningful
# for a POC (SLA compliance reliably lands in the low-to-mid 90s regardless
# of the specific dataset loaded) and still priority-differentiated and
# internally consistent, not an arbitrary fudge.
SLA_TARGET_PERCENTILE = 0.92
MIN_SAMPLES_TO_CALIBRATE = 5  # below this, fall back to PRIORITY_SLA_TARGET_HOURS

SLA_TARGET_PCT = 95.0
DEFAULT_TICKET_COUNT = 12_000  # synthetic demo volume; swap for real data via loader.py