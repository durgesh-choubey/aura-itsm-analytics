"""
AURA - Automated Unified Reporting Assistant
Entry point. Layout order (top to bottom), per spec:

    Header -> Data Source -> Compact KPI strip -> Executive Brief
    -> Filters (sidebar) -> Charts -> Data Table & Export -> AI Copilot

This file only orchestrates; all rendering logic lives in src/components/*
and all data/derivation logic lives in src/data/* and src/services/*.
"""

from __future__ import annotations

import pandas as pd

from src.components.charts import render_dashboard
from src.components.copilot_chat import render_copilot
from src.components.data_source import render_data_source_selector
from src.components.data_table import render_data_table
from src.components.executive_brief import render_executive_brief
from src.components.header import inject_global_styles, render_header
from src.components.kpi_strip import render_kpi_strip
from src.components.sidebar_filters import render_sidebar_filters
from src.data.loader import apply_filters
from src.data.metrics import compute_kpis, previous_period_kpis
from src.services.insights_service import generate_executive_brief


def main() -> None:
    # 1. Global theme + page config (must run first, before any other st.* call)
    inject_global_styles()

    # 2. Header (the single "AURA" title on the page)
    last_refreshed = pd.Timestamp.now().strftime("%b %d, %Y %H:%M")
    render_header(last_refreshed=last_refreshed)

    # 2b. Data source -- sample dataset or a user-uploaded CSV/XLSX, normalized
    #     to the same canonical schema either way.
    active_df, _source_label = render_data_source_selector()

    # 4. Filters -- rendered in the sidebar; placed here in code so the filter
    #    values are available before computing KPIs/brief/charts below, even
    #    though visually they live in the sidebar rather than the main flow.
    filters = render_sidebar_filters(active_df)
    filtered_df = apply_filters(active_df, filters)

    # 3. Compact KPI strip (Power BI tile row)
    current_kpis = compute_kpis(filtered_df)
    previous_kpis = previous_period_kpis(filtered_df)
    render_kpi_strip(current_kpis, previous_kpis)

    # 3b. Executive Brief
    brief = generate_executive_brief(filtered_df)
    render_executive_brief(brief)

    # 5. Charts
    render_dashboard(filtered_df)

    # 5b. Data Table + CSV export -- same filtered_df the charts use, with a
    #     column picker so the export matches exactly what's shown.
    render_data_table(filtered_df)

    # 6. AI Copilot
    render_copilot(filtered_df)


if __name__ == "__main__":
    main()