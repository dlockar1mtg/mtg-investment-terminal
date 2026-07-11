# v12.1 Changelog

## Fixed
- Fixed `'int' object has no attribute 'fillna'` crash.
- Rewrote defensive Series handling in `models/market_database.py`.
- Rewrote `update_prices.py` with explicit stage validation.

## Added
- `validate_v12_1_pipeline.py`.

## Result
- Daily price observations, rolling metrics, real signal scores, market intelligence, and Monte Carlo files should now be created in the same run.
