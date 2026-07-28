# AURA — Enterprise ITSM Analytics (PULSE module)

A Power BI / Microsoft Fabric / Copilot-styled Streamlit analytics app for
ITSM ticket data, built as a module inside the PULSE automation platform.

## Layout (top to bottom)

Header → Data Source → Compact KPI strip → Executive Brief → Filters (sidebar)
→ Charts → AI Copilot

## Project structure

```
app.py                          Entry point — orchestrates the page only
requirements.txt
.streamlit/config.toml          Forces the light theme at the framework level
assets/styles.css                Single source of all CSS (no dark/cyberpunk leftovers)

src/
  config.py                      Branding text (single source for "AURA"), theme tokens, SLA targets
  data/
    schema.py                    Canonical ITSM field list + column auto-mapping for uploads
    loader.py                    Sample data generator + upload reading/mapping application
    metrics.py                   KPI + chart-ready aggregate calculations
  components/
    header.py                    Injects CSS once; renders the ONE on-page "AURA" title
    data_source.py                Sample-data vs upload picker + column-mapping UI
    kpi_strip.py                  Compact Power BI-style KPI tile row
    executive_brief.py            AI / rule-based insight card
    sidebar_filters.py             Power BI "slicer"-style filters (dynamic per dataset)
    charts.py                      Plotly chart builders + dashboard grid layout
    copilot_chat.py               Microsoft Copilot-style chat panel
  services/
    llm_service.py                 Thin Groq/LangChain wrapper (optional — app works without it)
    insights_service.py            Builds structured summaries + executive brief generation
  utils/
    formatting.py                  Number/percent/duration formatting helpers
```

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in GROQ_API_KEY
streamlit run app.py
```

`llm_service.py` loads `.env` automatically via `python-dotenv`. Set
`GROQ_API_KEY` there (or as a real env var, or in `.streamlit/secrets.toml`)
to enable LLM-generated executive briefs and copilot answers. Without it,
the app uses deterministic rule-based summaries — nothing breaks.

## Backend dataset

Drop a real ITSM export into `data/` (e.g. `data/ITSM Dataset.csv`) and the
app will use it automatically — no code changes needed. It's auto-mapped to
the canonical schema exactly the same way an upload is (see below). With no
file in `data/`, the app falls back to a generated synthetic dataset shaped
like the same schema, so it still runs out of the box.

Only one file is picked up from `data/` (the first `.csv`/`.xlsx`/`.xls`
found); if you need to swap datasets, either replace that file or use the
in-app upload instead.

## Uploading your own dataset

Use the **Data Source** card right under the header:

1. Choose **Upload my own**, then pick a `.csv` or `.xlsx` export.
2. AURA auto-detects which of your columns map to its canonical fields
   (Number, Created, Priority, State, Assignment group, Country, etc.) based
   on common header names — including exactly the ones ServiceNow-style
   exports use (`Short description`, `Assignment group`, `Assigned to`,
   `Configuration item`, `Master Incident`, `Owned by`, ...).
3. Review the mapping in the expander, fix anything mis-detected (only
   Number / Created / Priority / State are required), then click
   **Use this dataset**.
4. Every KPI, chart, filter, and copilot answer immediately reflects the
   uploaded data. Missing optional columns (e.g. no CSAT survey field)
   are handled gracefully — the CSAT tile/chart swaps to an Open Tickets /
   State Distribution view automatically.

Click **Reset to backend dataset** in the same card to go back to whatever's
in `data/` (or the synthetic fallback).

## AI Copilot scope

The copilot (bottom of page) only answers questions about the loaded ticket
dataset — SLA, resolution time, priority, categories, agents, countries,
trends. Off-topic questions get a short, direct refusal instead of being
sent to the LLM. Answers are capped at one short sentence plus a one-line
suggested action; there's no small talk or general-knowledge mode.

## Changing the "AURA" branding text

Edit `APP_NAME`, `APP_FULL_NAME`, and `APP_TAGLINE` in `src/config.py`. That's
the only place the app name is defined; every component imports it from there,
so it only ever renders once on the page (in the header).

## A note on custom HTML in Streamlit

Every component that builds multi-line HTML (KPI tiles, header, executive
brief, copilot bubbles) passes its output through
`src/utils/html.py::compact_html()` before rendering. This isn't cosmetic —
Streamlit's `st.markdown(..., unsafe_allow_html=True)` still runs content
through a CommonMark parser first, which treats blank lines + 4-space-indented
text as a literal code block. Skipping `compact_html()` on new HTML-emitting
components is the most common way to reintroduce "raw tags showing up on
screen" bugs.
