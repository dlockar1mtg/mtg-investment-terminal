# Terminal 2.0.2 Seasonality

Run after historical backfill:

```bash
python terminal2_seasonality.py
```

Outputs:

```text
data/terminal2/exports/seasonality_monthly_returns.csv
data/terminal2/exports/seasonality_by_month.csv
data/terminal2/exports/seasonality_by_product_month.csv
data/terminal2/exports/seasonality_by_lifecycle_month.csv
```

Use `seasonality_by_month.csv` to identify calendar months where average returns are lower, which may indicate better buying windows.

Use `seasonality_by_lifecycle_month.csv` to see whether sealed products tend to perform differently based on how many months have passed since the first observed price.


# MTG Investment Terminal 2.0

This is a major architecture upgrade from the v13 series.

Instead of treating CSVs as the core system, Terminal 2.0 is **SQLite-first**:

```text
Product Master
↓
SQLite products table
↓
Historical price observations
↓
Feature engineering
↓
Investment scoring
↓
Monte Carlo-style projections
↓
Dashboard-ready exports
```

## What is included

### Core database

```text
data/terminal2/mtg_investment_terminal.sqlite
```

Tables:

- `products`
- `price_observations`
- `source_runs`
- `product_features`
- `investment_scores`

### New scripts

```bash
python terminal2_init.py
python terminal2_sync_products.py
python terminal2_backfill_monthly.py
python terminal2_compute_features.py
python terminal2_score.py
python terminal2_export.py
python terminal2_run_all.py
```

## Recommended workflow on your development laptop

First keep the v13 product master fresh:

```bash
python reset_source_cache.py
python run.py
```

Then initialize Terminal 2.0:

```bash
python terminal2_init.py
python terminal2_sync_products.py
```

Backfill historical monthly TCGCSV archives:

```bash
python terminal2_backfill_monthly.py
```

Then compute and score:

```bash
python terminal2_compute_features.py
python terminal2_score.py
python terminal2_export.py
```

Or after backfill, run the full local analytics workflow:

```bash
python terminal2_run_all.py
```

## 7-Zip requirement

Historical archive backfill requires 7-Zip.

The script searches:

```text
7z on PATH
7za on PATH
C:\Program Files\7-Zip\7z.exe
C:\Program Files (x86)\7-Zip\7z.exe
```

## Exports

Dashboard-ready exports are created in:

```text
data/terminal2/exports/
```

Important files:

```text
ranked_terminal.csv
products.csv
price_observations.csv
product_features.csv
investment_scores.csv
```

## Why Terminal 2.0 is better

The previous versions built the core logic. Terminal 2.0 makes the system durable:

- Product IDs live in a database.
- Historical observations are appended instead of overwritten.
- Features are recomputed from the database.
- Rankings are exportable.
- The project can evolve into a dashboard or app without rebuilding the data model.
