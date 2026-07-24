# Phase 10.3 — Architecture and Database Integrity

## Canonical production orchestration

The canonical full MTG production orchestration entry point is:

`terminal2_run_all.py`

This entry point coordinates:

- database initialization and migration
- product synchronization
- price feature computation
- product scoring
- historical intelligence
- dashboard and warehouse publishing
- market intelligence
- forecasting
- calibration
- portfolio intelligence
- semantic publishing
- Secret Lair intelligence and population
- universal return analytics

## Operational entry-point classification

### Full production orchestration

- `terminal2_run_all.py`

### Incremental operational workflow

- `terminal2_daily_update.py`

### Database initialization and migration

- `terminal2_init.py`
- `terminal2_module2_init.py`
- `terminal2_warehouse_init.py`

### Compatibility and focused workflows

Other root-level `terminal2_*.py` files remain supported as focused
publishers, validators, importers, migration tools, and compatibility
entry points. They are not replacements for the canonical full
orchestration entry point.

### Legacy application layer

The original application database and market modules under:

- `database/`
- `models/`
- root-level legacy scripts

remain separate from the Terminal 2 SQLite and warehouse architecture.
No legacy implementation is deleted during Phase 10.3.

## Database architecture

Terminal 2 uses SQLite through:

- `terminal2/db/schema.py`
- `terminal2/db/module1_migration.py`
- `terminal2/db/module2_migration.py`

Migrations accept an explicit database path so certification can run
against isolated temporary databases without modifying production data.

## Certification requirements

Phase 10.3 database certification verifies:

- schema creation
- Module 1 migration
- Module 2 migration
- migration idempotency
- required tables
- required indexes
- required product columns
- SQLite integrity
- foreign-key contract behavior