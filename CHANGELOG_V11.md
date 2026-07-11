# v11 Changelog

## Added
- `models/market_intelligence.py`
- `review_market_intelligence.py`
- Market intelligence score
- Liquidity proxy score
- Inventory risk proxy score
- Market regime score
- Monte Carlo simulation output
- Probability of doubling/tripling/loss

## Changed
- Scoring now includes `market_intelligence_score` at a conservative 10% weight.
- `run.py` displays Monte Carlo columns when present.

## Notes
- Inventory/liquidity are proxy-based until direct market listing/sales data sources are added.
