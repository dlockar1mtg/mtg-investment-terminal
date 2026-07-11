# Module 1 — Data Foundation

This package completes the Terminal 2.x data-foundation phase and prepares the codebase for Terminal 3.0 analytics and Terminal 4.0 presentation.

## Supported assets

Included:

- Collector Booster Displays
- Draft Booster Displays
- Traditional Booster Displays from the pre-Collector era
- Masters Booster Displays
- Secret Lair Drops

Excluded:

- Play Booster Displays
- Set Booster Displays
- Cases, individual packs, bundles, Commander decks, and prerelease kits

## 1. Product expansion

Run:

```bash
python terminal2_init.py
python terminal2_discover_assets.py
python terminal2_sync_products.py
```

The discovery script scans the TCGCSV Magic catalog and creates:

```text
data\terminal2\product_discovery_candidates.csv
data\terminal2\audit\product_discovery_audit.csv
```

High-confidence Draft, Traditional, Masters, and Collector displays may be added as approved products. Secret Lairs remain `review_required` by design because marketplace groups may contain foil/nonfoil variants, bundles, or individual cards.

Review the Product Master before using new products in analytics:

```text
data\product_master\investment_products.csv
```

## 2. Historical database

The monthly TCGCSV archive backfill remains the long-history foundation:

```bash
python terminal2_backfill_monthly.py
```

The permanent database remains:

```text
data\terminal2\mtg_investment_terminal.sqlite
```

Prices are stored in:

```text
price_observations
```

## 3. Daily history

Run once per day:

```bash
python terminal2_daily_update.py
```

This pulls the current TCGCSV price for every approved supported product, writes one daily observation into SQLite, and refreshes price features.

## 4. Metadata enrichment

Create a reviewable metadata template:

```bash
python terminal2_create_metadata_template.py
```

It creates:

```text
data\terminal2\product_metadata_template.csv
```

Complete the relevant fields, save a copy as:

```text
data\terminal2\product_metadata.csv
```

Then import it:

```bash
python terminal2_import_metadata.py
```

Metadata fields include:

- Release date and MSRP
- Print status and estimated print window
- Months out of print
- Franchise/IP
- IP strength
- Serialized-card presence
- Premium treatments
- Reprint risk
- Commander, competitive, and collector demand
- Supply class
- Source and confidence

## 5. Lifecycle

Run:

```bash
python terminal2_lifecycle.py
```

It creates:

```text
data\terminal2\exports\lifecycle_report.csv
```

Lifecycle stages:

- Pre-release
- Release / Early Supply
- Supply Peak / Price Discovery
- Stabilization
- Supply Contraction / Growth
- Scarcity
- Legacy

## 6. Seasonality

The existing seasonality module works across all approved product types:

```bash
python terminal2_seasonality.py
```

## 7. Validation

Run:

```bash
python terminal2_module1_validate.py
```

This confirms product, metadata, price-observation, and feature counts and shows products by asset class.

## Recommended workflow

```bash
python run.py
python terminal2_init.py
python terminal2_discover_assets.py
python terminal2_sync_products.py
python terminal2_backfill_monthly.py
python terminal2_daily_update.py
python terminal2_create_metadata_template.py
python terminal2_lifecycle.py
python terminal2_seasonality.py
python terminal2_run_all.py
python terminal2_module1_validate.py
```

Product identity remains the most important rule. The system intentionally favors review and correctness over automatically approving every possible product.
