# Secret Lair Price Import Guide

Required fields:

- `observation_date`
- `secret_lair_id`
- `source_name`
- `market_price`

Recommended fields:

- `low_price`
- `listing_count`
- `sales_count_30d`
- `currency`
- `source_url`
- `source_record_id`
- `price_data_quality`
- `notes`

Use one row per asset, observation date, and source. Price variants must use the
exact `secret_lair_id` from the registry. Dates use `YYYY-MM-DD`; prices use
plain numeric values without currency symbols.
