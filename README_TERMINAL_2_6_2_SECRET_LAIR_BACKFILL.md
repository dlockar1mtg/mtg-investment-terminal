# Terminal 2.6.2 — Secret Lair Catalog Backfill & Source Integration

This release adds a controlled source-ingestion and matching layer for building
the real Secret Lair registry and price history.

## Create local source templates

```bat
python terminal2_create_secret_lair_backfill_templates.py
```

## Dry-run

```bat
python terminal2_run_secret_lair_backfill.py
python terminal2_secret_lair_backfill_validate.py
```

Dry-run publishes proposed outputs but does not modify the working registry or
price history.

## Apply

Resolve every row in `secret_lair_unmatched_review.csv`, then run:

```bat
python terminal2_run_secret_lair_backfill.py --apply
```

The apply command refuses to write while review or rejected rows remain.
