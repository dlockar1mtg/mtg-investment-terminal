# Secret Lair Backfill Validation Checklist

Before dry-run:

- Source name is stable and lowercase-compatible
- Source record IDs are unique within each source
- Drop, variant, and finish are populated
- Dates use YYYY-MM-DD
- Prices are plain positive numbers
- Price rows reference existing catalog source identities

Before apply:

- `secret_lair_unmatched_review.csv` is empty
- Match confidence and methods have been reviewed
- New deterministic IDs do not duplicate existing assets
- Proposed registry row count is plausible
- Proposed price row count is plausible
- Backup or Git-clean source state is available
