# Module 1 Dashboard Analytics Warehouse

The full analytics run now refreshes a curated dashboard data mart automatically:

```bash
python terminal2_run_all.py
```

Rebuild only the dashboard datasets:

```bash
python terminal2_build_dashboard_warehouse.py
```

Validate the outputs:

```bash
python terminal2_dashboard_validate.py
```

## Folder structure

```text
data/
├── analytics/
│   ├── current/
│   ├── history/
│   ├── reports/
│   └── snapshots/
└── dashboard/
    ├── products/
    ├── market/
    ├── lifecycle/
    ├── portfolio/
    ├── seasonality/
    ├── research/
    ├── alerts/
    └── executive/
```

The package includes 62 populated or schema-ready CSV datasets. Terminal 3.0 and 4.0 files already have stable headers, allowing Power BI relationships and layouts to remain intact as new engines are added.

## Key Power BI files

```text
data/dashboard/products/product_summary.csv
data/dashboard/products/historical_prices.csv
data/dashboard/products/product_rankings.csv
data/dashboard/market/magic_market_index.csv
data/dashboard/market/asset_class_indices.csv
data/dashboard/lifecycle/lifecycle_stage.csv
data/dashboard/seasonality/seasonality_month.csv
data/dashboard/research/expected_returns.csv
data/dashboard/alerts/buy_alerts.csv
data/dashboard/executive/dashboard_summary.csv
data/dashboard/executive/top_opportunities.csv
```

## Dataset metadata

```text
data/dashboard/dataset_manifest.csv
data/dashboard/data_dictionary.csv
data/dashboard/warehouse_status.json
```

## Historical snapshots

Each run copies key outputs into:

```text
data/analytics/history/YYYY-MM-DD/
```

Timestamped execution summaries are stored in:

```text
data/analytics/snapshots/YYYYMMDD_HHMMSS/
```
