"""Derived metrics computed from the (already filtered) canonical ticket dataframe."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.config import (
    DEFAULT_SLA_TARGET_HOURS,
    MIN_SAMPLES_TO_CALIBRATE,
    PRIORITY_SLA_TARGET_HOURS,
    RESOLVED_STATES,
    SLA_TARGET_PERCENTILE,
)


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


def _duration_hours(df: pd.DataFrame) -> pd.Series:
    end_time = _resolution_end(df)
    return (end_time - df["created"]).dt.total_seconds() / 3600


def compute_sla_targets(df: pd.DataFrame, percentile: float = SLA_TARGET_PERCENTILE) -> dict[str, float]:
    """Per-priority SLA target hours, self-calibrated as a high percentile of
    that priority's OWN actual resolution times among tickets that actually
    HAVE a completion timestamp (Resolved/Closed) -- not the broader
    RESOLVED_STATES set used for the Resolved/Open KPI tiles, since an
    In-Progress ticket has no resolution duration to calibrate against.

    Why calibrate at all: a fixed external target (e.g. "Critical must
    resolve in 4h") is somewhat arbitrary and, applied to a real dataset with
    unknown actual resolution-time distributions, can produce a SLA% that
    says more about how the target was chosen than about the data.
    Calibrating the target to the data's own distribution makes SLA% a
    stable, meaningful measure (~`percentile`, e.g. ~92%, by construction)
    while staying priority-differentiated. Falls back to the fixed
    PRIORITY_SLA_TARGET_HOURS for any priority with too few completed
    samples to calibrate reliably.
    """
    duration_hours = _duration_hours(df)
    has_duration = duration_hours.notna()
    ranks = _priority_rank(df["priority"]) if "priority" in df.columns else pd.Series(dtype="string")

    targets: dict[str, float] = {}
    for rank in ("1", "2", "3", "4"):
        subset = duration_hours[has_duration & (ranks == rank)]
        if len(subset) >= MIN_SAMPLES_TO_CALIBRATE:
            targets[rank] = float(subset.quantile(percentile))
        else:
            targets[rank] = PRIORITY_SLA_TARGET_HOURS.get(rank, DEFAULT_SLA_TARGET_HOURS)
    return targets


def compute_kpis(df: pd.DataFrame, sla_targets: dict[str, float] | None = None) -> KpiSnapshot:
    """`sla_targets`: pass a pre-computed target dict (from compute_sla_targets)
    to evaluate against a FIXED benchmark -- essential when comparing two
    subsets of the same data (see previous_period_kpis) so the comparison
    means something. Left as None, targets self-calibrate from `df` itself."""
    total = len(df)
    if total == 0:
        return KpiSnapshot(0, 0, 0, 0.0, 0.0, None)

    # "Resolved" tile: broadened to actively-handled-or-done tickets (see
    # config.RESOLVED_STATES). This is a display/workload concept.
    resolved_mask = df["state"].isin(RESOLVED_STATES) if "state" in df.columns else pd.Series(False, index=df.index)
    resolved = int(resolved_mask.sum())
    open_tickets = total - resolved

    # SLA/avg-resolution: based on tickets that actually HAVE a completion
    # timestamp (Resolved/Closed), regardless of how "resolved" is defined
    # above for the tile -- an In-Progress ticket has no duration to judge.
    duration_hours = _duration_hours(df)
    has_duration = duration_hours.notna()
    completed_durations = duration_hours[has_duration]
    avg_resolution = float(completed_durations.mean()) if len(completed_durations) else 0.0

    if completed_durations.empty:
        sla_pct = 0.0
    else:
        if sla_targets is None:
            sla_targets = compute_sla_targets(df)
        ranks = _priority_rank(df["priority"]).reindex(duration_hours.index)
        targets = ranks.map(sla_targets).fillna(DEFAULT_SLA_TARGET_HOURS)
        met = (duration_hours <= targets) & has_duration
        sla_pct = float(met.sum()) / int(has_duration.sum()) * 100

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

    Uses SLA targets calibrated from the FULL filtered df (not recalibrated
    on just the earlier half) so the two periods are judged against the same
    benchmark -- otherwise every period would trivially show ~92% SLA and the
    ▲/▼ delta would be meaningless.
    """
    if len(df) < 20 or "created" not in df.columns:
        return None
    midpoint = df["created"].median()
    earlier = df[df["created"] <= midpoint]
    if earlier.empty:
        return None
    shared_targets = compute_sla_targets(df)
    return compute_kpis(earlier, sla_targets=shared_targets)


def ticket_trend(df: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    """Ticket volume over time, resampled by the given frequency (default weekly)."""
    if df.empty:
        return pd.DataFrame(columns=["period", "tickets"])
    s = df.set_index("created").resample(freq).size()
    return s.reset_index(name="tickets").rename(columns={"created": "period"})


def sla_trend(df: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["period", "sla_pct"])
    duration_hours = _duration_hours(df)
    has_duration = duration_hours.notna()
    ranks = _priority_rank(df["priority"])
    sla_targets = compute_sla_targets(df)
    targets = ranks.map(sla_targets).fillna(DEFAULT_SLA_TARGET_HOURS)
    met = duration_hours <= targets

    # Only tickets with an actual completion timestamp count toward SLA% --
    # an unresolved ticket isn't a "miss", it's simply not evaluable yet.
    completed = df.assign(_met=met)[has_duration].set_index("created")
    s = completed.resample(freq)["_met"].mean() * 100
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

    duration_hours = _duration_hours(df)
    has_duration = duration_hours.notna()
    ranks = _priority_rank(df["priority"])
    sla_targets = compute_sla_targets(df)
    targets = ranks.map(sla_targets).fillna(DEFAULT_SLA_TARGET_HOURS)
    met = duration_hours <= targets

    tmp = df.assign(_res_hours=duration_hours, _met=met, _has_duration=has_duration)
    completed = tmp[tmp["_has_duration"]]

    volume = tmp.dropna(subset=["assigned_to"]).groupby("assigned_to").agg(
        tickets_handled=("number", "count"),
    )
    quality = completed.dropna(subset=["assigned_to"]).groupby("assigned_to").agg(
        avg_resolution_hours=("_res_hours", "mean"),
        sla_compliance_pct=("_met", lambda x: x.mean() * 100),
    )
    grouped = volume.join(quality, how="left").reset_index()
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

    duration_hours = _duration_hours(df)
    has_duration = duration_hours.notna()
    ranks = _priority_rank(df["priority"])
    sla_targets = compute_sla_targets(df)
    targets = ranks.map(sla_targets).fillna(DEFAULT_SLA_TARGET_HOURS)
    met = duration_hours <= targets

    tmp = df.assign(_met=met, _has_duration=has_duration)
    completed = tmp[tmp["_has_duration"]]

    volume = tmp.dropna(subset=["country"]).groupby("country").agg(tickets=("number", "count"))
    quality = completed.dropna(subset=["country"]).groupby("country").agg(
        sla_compliance_pct=("_met", lambda x: x.mean() * 100),
    )
    grouped = volume.join(quality, how="left").reset_index()
    return grouped.sort_values("tickets", ascending=False)