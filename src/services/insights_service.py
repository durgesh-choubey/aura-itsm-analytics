"""
Executive Brief generation.

`build_structured_summary()` turns the filtered dataframe into a compact
dict of facts (no raw rows) -- this is what gets handed to the LLM prompt
*and* to the chatbot's context, so both surfaces reason over the same
grounded numbers instead of hallucinating from scratch.

`generate_executive_brief()` tries the LLM first and falls back to a
deterministic, rule-based brief if no API key is configured or the call
fails, so the page never breaks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.data.metrics import compute_kpis, group_counts
from src.services import llm_service


@dataclass
class ExecutiveBrief:
    highlights: list[str] = field(default_factory=list)
    recommendation: str = ""
    source: str = "rule-based"  # "llm" or "rule-based"


def build_structured_summary(df: pd.DataFrame) -> dict:
    kpis = compute_kpis(df)
    top_categories = group_counts(df, "category", top_n=3)
    top_group = group_counts(df, "assignment_group", top_n=1)

    critical_share = 0.0
    if "priority" in df.columns and len(df):
        critical_share = float(df["priority"].astype("string").str.contains("1", na=False).mean() * 100)

    return {
        "total_tickets": kpis.total_tickets,
        "resolved_tickets": kpis.resolved_tickets,
        "open_tickets": kpis.open_tickets,
        "sla_compliance_pct": round(kpis.sla_compliance_pct, 1),
        "avg_resolution_hours": round(kpis.avg_resolution_hours, 1),
        "csat_pct": round(kpis.csat_pct, 1) if kpis.csat_pct is not None else None,
        "top_categories": top_categories.to_dict(orient="records"),
        "top_assignment_group": top_group.to_dict(orient="records"),
        "critical_priority_share_pct": round(critical_share, 1),
    }


def _rule_based_brief(summary: dict) -> ExecutiveBrief:
    highlights = []

    sla = summary["sla_compliance_pct"]
    highlights.append(
        f"SLA compliance is {'above' if sla >= 95 else 'below'} target at {sla}%."
    )

    if summary["top_assignment_group"]:
        top_group_name = summary["top_assignment_group"][0]["assignment_group"]
        highlights.append(f"{top_group_name} has the highest ticket volume this period.")

    if summary["critical_priority_share_pct"] > 10:
        highlights.append(f"Critical (P1) incidents make up {summary['critical_priority_share_pct']}% of tickets.")
    else:
        highlights.append(f"Critical incidents remain a small share of volume at {summary['critical_priority_share_pct']}%.")

    if summary["csat_pct"] is not None:
        highlights.append(f"Customer satisfaction (CSAT) stands at {summary['csat_pct']}%.")
    else:
        highlights.append(f"{summary['open_tickets']} tickets are currently open across the filtered view.")

    if sla < 95 and summary["top_assignment_group"]:
        recommendation = (
            f"Increase {summary['top_assignment_group'][0]['assignment_group']} staffing during peak hours "
            "to bring SLA compliance back above target."
        )
    else:
        recommendation = "Maintain current staffing levels; monitor critical-priority volume for early signs of strain."

    return ExecutiveBrief(highlights=highlights[:4], recommendation=recommendation, source="rule-based")


def generate_executive_brief(df: pd.DataFrame) -> ExecutiveBrief:
    summary = build_structured_summary(df)

    if not llm_service.is_llm_available():
        return _rule_based_brief(summary)

    prompt = (
        "You are an ITSM analytics copilot. Given this structured ticket summary as JSON, "
        "write: 3-4 short bullet highlights (past tense, factual, no fluff), then ONE staffing "
        "or process recommendation in a single sentence. Keep bullets under 15 words each.\n\n"
        f"Data: {summary}\n\n"
        "Respond as plain text with lines starting '- ' for highlights and a final line "
        "starting 'Recommendation: '."
    )

    try:
        raw = llm_service.ask(prompt, system_prompt="You are a concise enterprise ITSM analytics assistant.")
        highlights = [
            line.strip("- ").strip()
            for line in raw.splitlines()
            if line.strip().startswith("-")
        ]
        recommendation_lines = [
            line.split("Recommendation:", 1)[1].strip()
            for line in raw.splitlines()
            if "Recommendation:" in line
        ]
        recommendation = recommendation_lines[0] if recommendation_lines else "Monitor current trends closely."
        if not highlights:
            return _rule_based_brief(summary)
        return ExecutiveBrief(highlights=highlights[:4], recommendation=recommendation, source="llm")
    except Exception:
        return _rule_based_brief(summary)
