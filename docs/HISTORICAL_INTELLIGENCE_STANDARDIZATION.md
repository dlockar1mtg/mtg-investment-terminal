# Historical Intelligence Standardization

Terminal 2.5.3 formalizes the historical data layer around the SQLite
`price_observations` and `product_features` tables.

Seven canonical datasets are published through the Dashboard Publisher:

- historical_prices
- monthly_price_history
- historical_returns
- historical_price_features
- historical_coverage
- historical_source_quality
- historical_summary

The monthly backfill workflow now recomputes features and republishes the
historical warehouse after importing archive data.
