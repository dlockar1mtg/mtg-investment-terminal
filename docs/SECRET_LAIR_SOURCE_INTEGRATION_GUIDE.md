# Secret Lair Source Integration Guide

Populate:

- `data/terminal2/secret_lair_source_catalog.csv`
- `data/terminal2/secret_lair_source_prices.csv`

Keep the source's stable record ID. The same `source_name` and
`source_record_id` must be used in both files.

Use `secret_lair_match_overrides.csv` only when the automatic decision needs to
be changed. Supported `override_action` values:

- `match` or `accept` with a valid `secret_lair_id`
- `reject`

Review the warehouse file `secret_lair_unmatched_review.csv` after every dry
run. Apply only after that file is empty.
