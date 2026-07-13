# Power BI Semantic Layer Architecture

## Star schema

- `semantic_dim_product` filters product snapshot, price history, forecast,
  and portfolio facts through `ProductKey`.
- `semantic_dim_date` filters price history through `DateKey` and executive
  KPIs through `SnapshotDateKey`.
- Fact-to-fact relationships are intentionally avoided.
- Relationship directions should remain single-direction from dimensions to
  facts.

## Dashboard contracts

`semantic_executive_kpis` provides long-form KPI values and business
definitions. `semantic_measure_catalog` provides recommended DAX expressions,
formats, home tables, and measure groups.

## Operational tables

`semantic_refresh_status` exposes publication status and age.
`semantic_field_dictionary` documents every curated field.
`semantic_relationship_map` is the authoritative relationship specification.

## Power BI loading rule

Load only files under `data/warehouse/current/semantic/` for the curated model.
Technical warehouse datasets remain available for research and troubleshooting.
