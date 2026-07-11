# MTG Investment Terminal — Module 2: Market Intelligence

Module 2 builds on the completed Module 1 data foundation.

## What Module 2 adds

- Populated market health summary
- Source-health monitoring
- Market intelligence score
- Market-relative strength and alpha
- Price-spread liquidity proxy
- Supply observation database
- Sales-velocity observation database
- Supply and sales input templates
- Confidence-aware signal handling
- Market intelligence alerts
- Dashboard and analytics exports
- Full Module 2 validation workflow

## Important data rule

Module 2 does not invent supply or sales data.

When no external listing or sales source is supplied:

- Supply score remains neutral.
- Sales-velocity score remains neutral.
- Their confidence remains zero.
- `signal_basis` clearly states that the result uses price-history and spread proxies only.

When actual observations are added, those signals are incorporated automatically.

## Full first-time workflow

### 1. Refresh Module 1 data

```bash
python run.py
python terminal2_init.py
python terminal2_discover_assets.py
python terminal2_sync_products.py
python terminal2_backfill_monthly.py
python terminal2_daily_update.py
```

The monthly backfill only needs to be repeated when extending the historical range or adding newly approved products.

### 2. Initialize Module 2

```bash
python terminal2_module2_init.py
```

This creates the Module 2 SQLite tables and the market-input templates:

```text
data/terminal2/market_inputs/supply_observations.csv
data/terminal2/market_inputs/sales_observations.csv
```

### 3. Optional: populate real market inputs

Supply template fields include:

```text
observation_date
investment_product_id
box_name
source_name
listing_count
seller_count
inventory_units
inventory_change_7d
inventory_change_30d
source_confidence
notes
```

Sales template fields include:

```text
observation_date
investment_product_id
box_name
source_name
sales_7d
sales_30d
median_sold_price_30d
sell_through_rate_30d
average_days_to_sale
source_confidence
notes
```

Blank template rows are ignored.

Import populated observations:

```bash
python terminal2_import_market_inputs.py
```

### 4. Run the complete Module 2 workflow

```bash
python terminal2_module2_run_all.py
```

This performs:

```text
Database migration
Product Master sync
Optional supply/sales import
Price-feature refresh
Investment scoring
Market intelligence scoring
Source-health calculation
Market-health calculation
Core exports
Dashboard warehouse refresh
Module 2 dashboard exports
Historical snapshot creation
```

The standard command also includes Module 2:

```bash
python terminal2_run_all.py
```

### 5. Validate

```bash
python terminal2_dashboard_validate.py
python terminal2_module2_validate.py
```

## Daily workflow

```bash
python run.py
python terminal2_daily_update.py
python terminal2_module2_run_all.py
python terminal2_module2_validate.py
```

When you begin collecting listing and sales observations, update the input files before the Module 2 run.

## Module 2 SQLite tables

```text
supply_observations
sales_observations
market_intelligence
market_health_history
source_health_history
```

## Main Module 2 outputs

```text
data/dashboard/market/market_health.csv
data/dashboard/market/market_intelligence.csv
data/dashboard/market/market_signals.csv
data/dashboard/market/source_health.csv
data/dashboard/market/supply_metrics.csv
data/dashboard/market/liquidity.csv
data/dashboard/alerts/market_intelligence_alerts.csv
data/dashboard/executive/market_health_summary.csv
data/analytics/current/market_intelligence.csv
data/analytics/current/market_health.csv
```

## Market health fields

The summary includes:

- Total products tracked
- Products with current prices
- Products updated today
- Average 30-day return
- Average 90-day return
- Median 30-day return
- Average volatility
- Buy/Watch/Wait/Avoid counts
- Products below target
- Products at observed ATH
- Products near observed ATL
- Average confidence
- Average data quality
- Average market-intelligence score
- Positive market breadth

## Market intelligence components

- Market-relative strength
- 30-day alpha
- 90-day alpha
- Price-spread liquidity proxy
- Supply signal
- Sales-velocity signal
- Price freshness
- Data quality
- Confidence
- Signal basis

## Preparing for Terminal 3.0

Module 2 creates the market-layer data needed for:

- Explainable multi-factor scoring
- Analog matching
- Buy-zone and bottom prediction
- Supply-depletion analytics
- Market regime detection
- Advanced alerts
- Portfolio risk and correlation analysis
