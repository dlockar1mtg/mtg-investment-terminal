# Phase 11E.15 — Production Publishing and Terminal Delivery

This milestone publishes the governed valuation and consumption outputs as a
versioned, checksum-certified terminal delivery package.

## Delivery behavior

- Validates source schemas before publishing.
- Requires the universal interface to contain exactly 1,141 products.
- Creates immutable timestamped package directories.
- Updates an atomic `latest` delivery directory.
- Publishes SHA-256 checksums and row counts in the manifest.
- Keeps current asking references explicitly separate from sold history.
- Keeps current asking references model-ineligible.

## Published files

- `universal_mtg_consumption_interface.csv`
- `dashboard.csv`
- `forecasts.csv`
- `recommendations.csv`
- `rankings.csv`
- `exclusions.csv`
- `market_provenance.csv`
- `consumption_summary.json`
- `valuation_summary.json`
- `delivery_manifest.json`

## Complete production command

```powershell
python .\scripts\run_phase_11e_15_production_delivery.py
```
