# v7 Changelog

## Added
- `models/canonical_products.py`
- Canonical Collector Booster Display selector
- `collector_booster_displays_canonical.csv`

## Changed
- Model now scores one canonical display per set/group.
- Discovery still saves raw product-level results for audit.
- `product_map.csv` now uses canonical display rows.
- Target buy formula now uses margin-of-safety logic and is capped below current market price.

## Fixed
- Duplicate LOTR rows caused by multiple TCGCSV collector products.
- Impossible target-buy values caused by inflated fair-value/target logic.
