"""Legacy dashboard-to-warehouse migration subsystem."""

from .catalog import MigrationCandidate, discover_legacy_datasets
from .migration import (
    MigrationResult,
    WarehouseMigration,
    migrate_legacy_dashboard_outputs,
)
from .validation import MigrationValidationResult, validate_migration

__all__ = [
    "MigrationCandidate",
    "MigrationResult",
    "MigrationValidationResult",
    "WarehouseMigration",
    "discover_legacy_datasets",
    "migrate_legacy_dashboard_outputs",
    "validate_migration",
]
