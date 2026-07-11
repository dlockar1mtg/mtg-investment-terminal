# v7.1 Changelog

## Fixed
- Prevented Collector Booster Display Case prices from being selected as individual display prices.
- Prevented raw product-level price rows from being saved under shared set-level box names.
- Overwrites latest source cache using canonical individual display rows only.

## Added
- `reset_source_cache.py` to delete stale database/cache records after upgrading.
