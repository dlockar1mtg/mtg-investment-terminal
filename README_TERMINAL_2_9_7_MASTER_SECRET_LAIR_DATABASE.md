# Terminal 2.9.7 — Master Secret Lair Database

Builds a persistent, source-grounded product catalog using the official Secret
Lair storefront, TCGCSV product and price feeds, and Scryfall bulk card metadata.
It preserves current price snapshots as history, creates stable product mappings
for TCGCSV archive backfills, and routes uncertain identities to manual review.

```bat
python terminal2_build_master_secret_lair_database.py --refresh
python terminal2_master_secret_lair_validate.py
```
