# Phase 10.10 — Universal Export Package

## Purpose

Phase 10.10 packages the certified MTG production universe for import into the Universal Investment Platform.

The export is generated from the Phase 10.9 certified registry, intelligence interface, portfolio lane summary, and production-closeout manifest.

## Export interface

- Interface: `mtg-universal-export-v1`
- Contract version: `1`
- Platform: `MTG`
- Currency: `USD`
- Product universe: 1,141

## Package files

- `asset_master.csv`
- `forecasts.csv`
- `recommendations.csv`
- `risk_metrics.csv`
- `portfolio_summary.csv`
- `platform_status.csv`
- `diagnostics.csv`
- `package_summary.json`
- `export_manifest.json`

## Privacy boundary

The public export includes only lane-level portfolio totals. It excludes position-level quantity, acquisition date, holding identifiers, cost basis by holding, notes, and other private holdings details.

## Execution

```powershell
powershell -ExecutionPolicy Bypass `
    -File `
    ".\scripts\run_phase_10_10_universal_export.ps1"
```

## Required results

- Build status: `PASS`
- Validation status: `CERTIFIED`
- Asset rows: 1,141
- Forecast rows: 1,141
- Recommendation rows: 1,141
- Risk rows: 1,141
- Portfolio summary rows: 3
- Diagnostics: 0
- Private position fields: excluded
- API quota calls: 0
- Focused tests: 4 passed

## Generated outputs

Generated packages are written under:

`data/validation/phase_10/universal_export/`

The timestamped package and `latest` directory remain local and must not be staged.
