# Secret Lair Backfill Architecture

## Safety model

The backfill engine is dry-run by default. It publishes proposed registry and
price files to the warehouse but does not alter the local working datasets.

`--apply` is allowed only when:

- at least one catalog row exists
- no source row requires review
- no source row has been rejected

## Matching order

1. Manual override
2. Exact source name and source record ID
3. High-confidence metadata match
4. Deterministic new asset identity
5. Manual-review queue for ambiguous records

Name-only matching is never treated as sufficient evidence.
