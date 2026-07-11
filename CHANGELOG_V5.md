# v5 Changelog

## Added
- SQLite database at `data/database/mtg_prices.sqlite`
- `product_mapping`, `price_snapshots`, and `source_runs` tables
- `update_prices.py`
- `source_health.py`
- TCGCSV collector
- Optional TCGplayer API collector
- MTGJSON metadata collector
- Scryfall chase-card summary collector
- Source cache written to `data/source_cache/latest_prices.csv`

## Changed
- `run.py` now refreshes source data before scoring when enabled.
- `models/source_data.py` now prefers SQLite/latest source cache over manual CSV prices.

## Notes
- TCGplayer API access is optional because new API access is not currently being granted.
- TCGCSV automation requires `tcgcsv_group_id` values in `data/reference/product_map.csv`.
