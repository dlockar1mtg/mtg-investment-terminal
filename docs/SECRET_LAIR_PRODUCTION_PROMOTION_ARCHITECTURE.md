# Production Promotion Architecture

Master Database records remain staging data until an explicit apply command is
issued. Preview and publication are read-only. Apply creates backups, merges
eligible products and prices, checks referential integrity, and only then writes
the production CSV files.

Default safeguards:
- source confidence at least 75
- valid production finish
- no duplicate IDs or canonical identities
- no unresolved review-queue match
- required identity fields present
- positive real market prices
