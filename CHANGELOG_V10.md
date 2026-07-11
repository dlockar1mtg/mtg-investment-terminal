# v10 Changelog

## Added
- Historical investment feature engine.
- `models/investment_features.py`
- `review_investment_features.py`
- `data/investment/investment_features.csv`
- `data/investment/historical_metrics.csv`
- `data/reference/release_metadata.csv`

## Changed
- Scoring now includes `investment_feature_score` at a conservative 10% weight.
- Projection confidence now lightly considers history confidence.
- Daily price snapshots include product IDs and investment features.

## Notes
- First run has limited history; metrics improve after repeated daily runs.
