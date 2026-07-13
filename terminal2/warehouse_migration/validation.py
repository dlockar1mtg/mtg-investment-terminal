from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from terminal2.warehouse_core import Warehouse, get_warehouse_config


@dataclass(frozen=True)
class MigrationValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int
    datasets_missing: int


def validate_migration(
    *,
    project_root: Path | None = None,
) -> MigrationValidationResult:
    warehouse = Warehouse(
        config=get_warehouse_config(project_root)
    )
    report_path = (
        warehouse.config.manifests_root
        / "migration_report.csv"
    )
    status_path = (
        warehouse.config.manifests_root
        / "migration_status.json"
    )

    errors: list[str] = []
    warnings: list[str] = []
    checked = 0
    missing = 0

    if not report_path.exists():
        errors.append(
            f"Migration report is missing: {report_path}"
        )
        return MigrationValidationResult(
            False,
            tuple(errors),
            tuple(warnings),
            0,
            0,
        )

    with report_path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        checked += 1
        path = (
            warehouse.config.project_root
            / row["warehouse_path"]
        )
        if not path.exists():
            missing += 1
            errors.append(
                f"Warehouse dataset is missing: {path}"
            )

    if not rows:
        warnings.append(
            "Migration report contains zero datasets."
        )

    if not status_path.exists():
        errors.append(
            f"Migration status is missing: {status_path}"
        )
    else:
        payload = json.loads(
            status_path.read_text(encoding="utf-8")
        )
        if payload.get("status") not in {
            "success",
            "partial",
        }:
            errors.append(
                f"Migration status is {payload.get('status')}."
            )

    return MigrationValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        datasets_checked=checked,
        datasets_missing=missing,
    )
