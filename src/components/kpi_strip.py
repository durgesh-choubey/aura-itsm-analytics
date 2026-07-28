"""Compact KPI tile strip — the 'Power BI dashboard tiles' row under the header."""

from __future__ import annotations

import streamlit as st

from src.data.metrics import KpiSnapshot
from src.utils.formatting import (
    delta_arrow,
    delta_color,
    format_count,
    format_hours,
    format_percent,
)
from src.utils.html import compact_html


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100


def _tile_html(label: str, value: str, delta_value: float | None, higher_is_better: bool = True) -> str:
    delta_html = ""
    if delta_value is not None:
        color = delta_color(delta_value, higher_is_better=higher_is_better)
        arrow = delta_arrow(delta_value)
        delta_html = (
            f'<div class="aura-kpi-delta {color}">{arrow} {abs(delta_value):.1f}% vs prior period</div>'
        )
    html = f"""
        <div class="aura-kpi-tile">
            <p class="aura-kpi-label">{label}</p>
            <p class="aura-kpi-value">{value}</p>
            {delta_html}
        </div>
    """
    return compact_html(html)


def render_kpi_strip(current: KpiSnapshot, previous: KpiSnapshot | None = None) -> None:
    """Render the 5-tile compact KPI row: Tickets, Resolved, SLA, Avg Resolution, and
    CSAT if the dataset has survey data, otherwise Open Tickets as the 5th tile."""

    def delta(curr_val: float, attr: str) -> float | None:
        if previous is None:
            return None
        prev_val = getattr(previous, attr)
        if prev_val is None:
            return None
        return _pct_change(curr_val, prev_val)

    tiles = [
        _tile_html(
            "Tickets", format_count(current.total_tickets),
            delta(current.total_tickets, "total_tickets"), higher_is_better=True,
        ),
        _tile_html(
            "Resolved", format_count(current.resolved_tickets),
            delta(current.resolved_tickets, "resolved_tickets"), higher_is_better=True,
        ),
        _tile_html(
            "SLA Compliance", format_percent(current.sla_compliance_pct),
            delta(current.sla_compliance_pct, "sla_compliance_pct"), higher_is_better=True,
        ),
        _tile_html(
            "Avg Resolution", format_hours(current.avg_resolution_hours),
            delta(current.avg_resolution_hours, "avg_resolution_hours"), higher_is_better=False,
        ),
    ]

    if current.csat_pct is not None:
        tiles.append(
            _tile_html(
                "CSAT", format_percent(current.csat_pct),
                delta(current.csat_pct, "csat_pct"), higher_is_better=True,
            )
        )
    else:
        tiles.append(
            _tile_html(
                "Open Tickets", format_count(current.open_tickets),
                delta(current.open_tickets, "open_tickets"), higher_is_better=False,
            )
        )

    st.markdown(compact_html(f'<div class="aura-kpi-row">{"".join(tiles)}</div>'), unsafe_allow_html=True)
