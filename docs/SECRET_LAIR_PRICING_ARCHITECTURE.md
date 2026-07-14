# Secret Lair Pricing Architecture

Terminal 2.6.1 uses `secret_lair_id` from the curated registry as the permanent
pricing identity. Foil and nonfoil variants remain separate assets.

## Flow

1. Curated source observations
2. Registry-ID validation and normalization
3. Local price-history file
4. Current, monthly, return, coverage, and quality datasets
5. Warehouse publication
6. Scoring and forecasts in later 2.6 releases

## Source policy

Every observation retains source name, source URL, source record ID, currency,
and optional source-quality score. The system does not blend unknown products
or silently accept asset IDs that are absent from the registry.
