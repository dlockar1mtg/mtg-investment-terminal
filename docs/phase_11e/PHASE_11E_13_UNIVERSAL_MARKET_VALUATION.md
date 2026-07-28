# Phase 11E.13 — Universal Market Coverage and Valuation Integration

This milestone builds one governed market-valuation row for every product in
the 1,141-product MTG universe.

## Source priority

1. Latest consolidated direct historical market price
2. Latest quality-approved current asking-price median
3. Explicit valuation-unavailable state

Current asking prices are dashboard references only. They are never marked
model-eligible and are not represented as sold-price history.

## Outputs

- `universal_mtg_market_valuation.csv`
- `universal_mtg_market_provenance.csv`
- `universal_mtg_dashboard_market_dataset.csv`
- `universal_mtg_model_eligible_market_dataset.csv`
- `universal_mtg_valuation_gap_queue.csv`
- `universal_mtg_market_valuation_summary.json`

## One-cycle command

```powershell
python .\scripts\run_phase_11e_13_valuation_integration.py
```
