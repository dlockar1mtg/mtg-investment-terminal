# Terminal 2.5.5 — Forecast Intelligence Engine

This release adds multi-horizon forecasts, market regimes, trend persistence,
forecast uncertainty, drawdown and loss estimates, risk-adjusted rankings, and
a unified conviction score.

## Publish and validate

```bat
python terminal2_publish_forecast_intelligence.py
python terminal2_forecast_warehouse_validate.py
```

Forecast horizons are 6, 12, 36, and 60 months. Canonical datasets publish
through the Dashboard Publisher into the centralized warehouse.
