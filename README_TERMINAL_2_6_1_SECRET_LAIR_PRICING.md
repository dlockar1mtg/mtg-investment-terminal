# Terminal 2.6.1 — Secret Lair Pricing & Historical Intelligence

This release adds curated Secret Lair price observations, current pricing,
monthly history, MSRP premiums, historical returns, coverage, quality findings,
and an executive market summary.

## Create the local price file

```bat
python terminal2_create_secret_lair_price_template.py
```

## Import completed observations

```bat
python terminal2_import_secret_lair_prices.py path\to\prices.csv
```

Every `secret_lair_id` must already exist in the 2.6.0 registry.

## Publish and validate

```bat
python terminal2_publish_secret_lair_pricing.py
python terminal2_secret_lair_pricing_validate.py
```

An empty price history is valid but produces a warning. Scoring is deferred
until curated observations are available.
