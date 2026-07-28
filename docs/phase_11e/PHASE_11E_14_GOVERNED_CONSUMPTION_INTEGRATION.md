# Phase 11E.14 — Governed Forecast, Ranking, Recommendation, and Dashboard Consumption

This milestone joins the 1,141-row governed market valuation contract to the
existing unified MTG intelligence interface.

It reuses certified legacy forecast scenarios and recommendations only when
the new valuation layer permits model consumption.

## Guardrails

- Direct historical valuations may consume existing eligible forecasts.
- Current asking references remain dashboard-only.
- Current asking references never become forecasts or recommendations.
- Valuation-unavailable products remain suppressed.
- Ranking is limited to governed forecast-eligible products.
- No new forecast values are fabricated.

## Outputs

- `universal_mtg_consumption_interface.csv`
- `universal_mtg_dashboard_consumption.csv`
- `universal_mtg_governed_forecasts.csv`
- `universal_mtg_governed_recommendations.csv`
- `universal_mtg_guarded_ranking.csv`
- `universal_mtg_consumption_exclusions.csv`
- `universal_mtg_consumption_summary.json`

## Full integration command

```powershell
python .\scripts\run_phase_11e_14_consumption_integration.py
```
