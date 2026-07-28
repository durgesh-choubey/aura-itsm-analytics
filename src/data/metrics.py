"""Derived metrics computed from the (already filtered) canonical ticket dataframe."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.config import DEFAULT_SLA_TARGET_HOURS, PRIORITY_SLA_TARGET_HOURS, RESOLVED_STATES


@dataclass(frozen=True)
class KpiSnapshot:
    total_tickets: int
    resolved_tickets: int
    open_tickets: int
    sla_compliance_pct: float
    avg_resolution_hours: float
    csat_pct: float | None  # None when the dataset has no survey column


def _priority_rank(priority: pd.Series) -> pd.Series:
    """'1 - Critical' -> '1'. Falls back gracefully on unexpected formats."""
    return priority.astype("string").str.extract(r"(\d)")[0]


def _resolution_end(df: pd.DataFrame) -> pd.Series:
    """Prefer 'closed', fall back to 'resolved' as the end-of-life timestamp."""
    closed = df["closed"] if "closed" in df.columns else pd.Series(pd.NaT, index=df.index)
    resolved = df["resolved"] if "resolved" in df.columns else pd.Series(pd.NaT, index=df.index)
    return closed.fillna(resolved)


def compute_kpis(df: pd.DataFrame) -> KpiSnapshot:
    total = len(df)
    if total == 0:
        return KpiSnapshot(0, 0, 0, 0.0, 0.0, None)

    resolved_mask = df["state"].isin(RESOLVED_STATES) if "state" in df.columns else pd.Series(False, index=df.index)
    resolved = int(resolved_mask.sum())
    open_tickets = total - resolved

    end_time = _resolution_end(df)
    duration_hours = (end_time - df["created"]).dt.total_seconds() / 3600
    resolved_durations = duration_hours[resolved_mask.reindex(duration_hours.index, fill_value=False)]
    avg_resolution = float(resolved_durations.mean()) if len(resolved_durations.dropna()) else 0.0

    # SLA compliance: among resolved tickets, share that closed within the
    # priority's target resolution window.
    if resolved_durations.dropna().empty:
        sla_pct = 0.0
    else:
        ranks = _priority_rank(df["priority"]).reindex(duration_hours.index)
        targets = ranks.map(PRIORITY_SLA_TARGET_HOURS).fillna(DEFAULT_SLA_TARGET_HOURS)
        met = (duration_hours <= targets) & resolved_mask
        sla_pct = float(met.sum()) / resolved * 100 if resolved else 0.0

    csat_pct = None
    if "customer_survey_result" in df.columns and df["customer_survey_result"].notna().any():
        scores = pd.to_numeric(df["customer_survey_result"], errors="coerce")
        if scores.notna().any():
            csat_pct = float((scores >= 4).mean() * 100)

    return KpiSnapshot(
        total_tickets=total,
        resolved_tickets=resolved,
        open_tickets=open_tickets,
        sla_compliance_pct=sla_pct,
        avg_resolution_hours=avg_resolution,
        csat_pct=csat_pct,
    )


def previous_period_kpis(df: pd.DataFrame) -> KpiSnapshot | None:
    """Split the filtered range in half by time and compute KPIs on the earlier half,
    used purely to derive KPI deltas (▲/▼) for the strip. Returns None if not enough data.
    """
    if len(df) < 20 or "created" not in df.columns:
        return None
    midpoint = df["created"].median()
    earlier = df[df["created"] <= midpoint]
    if earlier.empty:
        return None
    return compute_kpis(earlier)


def ticket_trend(df: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    """Ticket volume over time, resampled by the given frequency (default weekly)."""
    if df.empty:
        return pd.DataFrame(columns=["period", "tickets"])
    s = df.set_index("created").resample(freq).size()
    return s.reset_index(name="tickets").rename(columns={"created": "period"})


def sla_trend(df: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["period", "sla_pct"])
    end_time = _resolution_end(df)
    duration_hours = (end_time - df["created"]).dt.total_seconds() / 3600
    ranks = _priority_rank(df["priority"])
    targets = ranks.map(PRIORITY_SLA_TARGET_HOURS).fillna(DEFAULT_SLA_TARGET_HOURS)
    met = duration_hours <= targets
    tmp = df.assign(_met=met).set_index("created")
    s = tmp.resample(freq)["_met"].apply(lambda x: x.mean() * 100 if len(x) else None)
    return s.reset_index(name="sla_pct").rename(columns={"created": "period"})


def group_counts(df: pd.DataFrame, column: str, top_n: int | None = None) -> pd.DataFrame:
    if column not in df.columns:
        return pd.DataFrame(columns=[column, "count"])
    counts = df[column].value_counts(dropna=True).reset_index()
    counts.columns = [column, "count"]
    if top_n:
        counts = counts.head(top_n)
    return counts


def agent_performance(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    cols = ["assigned_to", "tickets_handled", "avg_resolution_hours", "sla_compliance_pct"]
    if df.empty or "assigned_to" not in df.columns:
        return pd.DataFrame(columns=cols)

    end_time = _resolution_end(df)
    duration_hours = (end_time - df["created"]).dt.total_seconds() / 3600
    ranks = _priority_rank(df["priority"])
    targets = ranks.map(PRIORITY_SLA_TARGET_HOURS).fillna(DEFAULT_SLA_TARGET_HOURS)
    met = duration_hours <= targets

    tmp = df.assign(_res_hours=duration_hours, _met=met)
    grouped = tmp.dropna(subset=["assigned_to"]).groupby("assigned_to").agg(
        tickets_handled=("number", "count"),
        avg_resolution_hours=("_res_hours", "mean"),
        sla_compliance_pct=("_met", lambda x: x.mean() * 100),
    ).reset_index()
    return grouped.sort_values("tickets_handled", ascending=False).head(top_n)


def csat_distribution(df: pd.DataFrame) -> pd.DataFrame:
    if "customer_survey_result" not in df.columns:
        return pd.DataFrame(columns=["rating", "count"])
    scores = pd.to_numeric(df["customer_survey_result"], errors="coerce").dropna()
    counts = scores.value_counts().sort_index().reset_index()
    counts.columns = ["rating", "count"]
    return counts


def state_distribution(df: pd.DataFrame) -> pd.DataFrame:
    return group_counts(df, "state")


def country_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "country" not in df.columns:
        return pd.DataFrame(columns=["country", "tickets", "sla_compliance_pct"])

    end_time = _resolution_end(df)
    duration_hours = (end_time - df["created"]).dt.total_seconds() / 3600
    ranks = _priority_rank(df["priority"])
    targets = ranks.map(PRIORITY_SLA_TARGET_HOURS).fillna(DEFAULT_SLA_TARGET_HOURS)
    met = duration_hours <= targets

    tmp = df.assign(_met=met)
    grouped = tmp.dropna(subset=["country"]).groupby("country").agg(
        tickets=("number", "count"),
        sla_compliance_pct=("_met", lambda x: x.mean() * 100),
    ).reset_index()
    return grouped.sort_values("tickets", ascending=False)
