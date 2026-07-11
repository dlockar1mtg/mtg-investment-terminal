# MTG Investment Terminal 2.0 Changelog

## Added
- SQLite-first database.
- Terminal 2 package.
- Product sync from Product Master to SQLite.
- Historical archive ingestion directly to SQLite.
- Rolling price feature computation from SQLite.
- Investment scoring table.
- Dashboard-ready exports.

## New package
- `terminal2/`

## New scripts
- `terminal2_init.py`
- `terminal2_sync_products.py`
- `terminal2_backfill_monthly.py`
- `terminal2_compute_features.py`
- `terminal2_score.py`
- `terminal2_export.py`
- `terminal2_run_all.py`

## Purpose
Move from CSV-centered scripts to a durable market database and analytics platform.
