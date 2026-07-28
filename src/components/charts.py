"""
Dashboard charts.

Each `build_*` function returns a ready-to-render Plotly figure, styled with
a shared light theme (`_apply_theme`). `render_dashboard()` lays them out in
a Power BI-style grid of white cards. Charts read the canonical schema (see
src/data/schema.py); a chart is skipped entirely (replaced with a friendly
empty state) if its required column is missing from the active dataset.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.config import CHART_PALETTE, THEME
from src.data.metrics import (
    agent_performance,
    country_summary,
    csat_distribution,
    group_counts,
    sla_trend,
    state_distribution,
    ticket_trend,
)


def _apply_theme(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor=THEME.surface,
        plot_bgcolor=THEME.surface,
        font=dict(family=THEME.font_family, color=THEME.text, size=12),
        title_font=dict(size=14, color=THEME.text),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        colorway=CHART_PALETTE,
    )
    fig.update_xaxes(gridcolor=THEME.border, zeroline=False)
    fig.update_yaxes(gridcolor=THEME.border, zeroline=False)
    return fig


def _empty_state(message: str) -> None:
    st.markdown(
        f'<div style="padding:2.5rem 1rem; text-align:center; color: var(--aura-text-secondary); font-size:0.85rem;">{message}</div>',
        unsafe_allow_html=True,
    )


def build_incident_trend(df: pd.DataFrame) -> go.Figure:
    trend = ticket_trend(df, freq="W")
    fig = px.line(trend, x="period", y="tickets", markers=True, title="Incident Trend (Weekly)")
    fig.update_traces(line_color=THEME.primary, fill="tozeroy", fillcolor="rgba(0,120,212,0.08)")
    return _apply_theme(fig)


def build_monthly_trend(df: pd.DataFrame) -> go.Figure:
    trend = ticket_trend(df, freq="MS")
    fig = px.bar(trend, x="period", y="tickets", title="Monthly Ticket Trend")
    fig.update_traces(marker_color=THEME.primary)
    return _apply_theme(fig)


def build_sla_trend(df: pd.DataFrame) -> go.Figure:
    trend = sla_trend(df, freq="W")
    fig = px.line(trend, x="period", y="sla_pct", markers=True, title="SLA Compliance Trend (Weekly)")
    fig.update_traces(line_color=THEME.success)
    fig.add_hline(y=95, line_dash="dot", line_color=THEME.text_secondary, annotation_text="Target 95%")
    return _apply_theme(fig)


def build_priority_distribution(df: pd.DataFrame) -> go.Figure:
    counts = group_counts(df, "priority")
    fig = px.pie(counts, names="priority", values="count", hole=0.55, title="Priority Distribution")
    fig.update_traces(textinfo="percent+label")
    return _apply_theme(fig, height=320)


def build_category_breakdown(df: pd.DataFrame) -> go.Figure:
    counts = group_counts(df, "category").sort_values("count")
    fig = px.bar(counts, x="count", y="category", orientation="h", title="Tickets by Category")
    fig.update_traces(marker_color=THEME.primary)
    return _apply_theme(fig)


def build_agent_performance(df: pd.DataFrame) -> go.Figure:
    perf = agent_performance(df, top_n=10).sort_values("tickets_handled")
    fig = px.bar(
        perf, x="tickets_handled", y="assigned_to", orientation="h",
        title="Top Agent Performance (by volume)",
        hover_data=["avg_resolution_hours", "sla_compliance_pct"],
    )
    fig.update_traces(marker_color=THEME.primary)
    return _apply_theme(fig, height=360)


def build_satisfaction_or_state(df: pd.DataFrame) -> tuple[go.Figure, bool]:
    """Returns (figure, is_csat). Uses CSAT distribution if the dataset has
    survey data, otherwise falls back to a State distribution chart."""
    dist = csat_distribution(df)
    if not dist.empty:
        fig = px.bar(dist, x="rating", y="count", title="Customer Satisfaction Distribution")
        fig.update_traces(marker_color=THEME.primary)
        fig.update_xaxes(dtick=1, title="Survey rating (1-5)")
        return _apply_theme(fig), True

    counts = group_counts(df, "state")
    fig = px.pie(counts, names="state", values="count", hole=0.55, title="Ticket State Distribution")
    fig.update_traces(textinfo="percent+label")
    return _apply_theme(fig), False


def build_country_analytics(df: pd.DataFrame) -> go.Figure:
    summary = country_summary(df)
    fig = px.bar(
        summary, x="country", y="tickets", color="sla_compliance_pct",
        title="Ticket Volume & SLA by Country",
        color_continuous_scale=["#A80000", "#FFB900", "#107C10"],
    )
    return _apply_theme(fig)


def render_dashboard(df: pd.DataFrame) -> None:
    """Render all charts in a Power BI-style grid, two per row, inside light cards."""
    st.markdown('<p class="aura-section-title">Dashboard</p>', unsafe_allow_html=True)

    if df.empty:
        st.info("No tickets match the current filters. Adjust filters in the sidebar to see charts.")
        return

    row_specs = [
        ("created", build_incident_trend, "created", build_monthly_trend),
        ("created", build_sla_trend, "priority", build_priority_distribution),
        ("category", build_category_breakdown, "assigned_to", build_agent_performance),
    ]

    for left_col, left_builder, right_col, right_builder in row_specs:
        col_left, col_right = st.columns(2)
        for column, builder, container in [(left_col, left_builder, col_left), (right_col, right_builder, col_right)]:
            with container:
                with st.container(border=True):
                    if column not in df.columns or df[column].dropna().empty:
                        _empty_state(f"'{column}' column not found in this dataset.")
                    else:
                        st.plotly_chart(builder(df), use_container_width=True, config={"displayModeBar": False})

    col_left, col_right = st.columns(2)
    with col_left:
        with st.container(border=True):
            fig, _ = build_satisfaction_or_state(df)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with col_right:
        with st.container(border=True):
            if "country" not in df.columns or df["country"].dropna().empty:
                _empty_state("'country' column not found in this dataset.")
            else:
                st.plotly_chart(build_country_analytics(df), use_container_width=True, config={"displayModeBar": False})