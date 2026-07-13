from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from terminal2.market.contracts import MARKET_DATASET_CONTRACTS
from terminal2.warehouse_core import get_warehouse_config


@dataclass(frozen=True)
class MarketValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int


def validate_market_warehouse(
    project_root: Path | None = None,
) -> MarketValidationResult:
    config = get_warehouse_config(project_root)
    manifest_path = config.manifests_root / "dataset_manifest.csv"

    errors: list[str] = []
    warnings: list[str] = []

    if not manifest_path.exists():
        return MarketValidationResult(
            False,
            (f"Dataset manifest is missing: {manifest_path}",),
            (),
            0,
        )

    with manifest_path.open("r", newline="", encoding="utf-8") as handle:
        rows = {
            row["dataset_name"]: row
            for row in csv.DictReader(handle)
        }

    for name, contract in MARKET_DATASET_CONTRACTS.items():
        row = rows.get(name)
        if row is None:
            errors.append(f"Required market dataset is missing: {name}")
            continue

        current_path = Path(row["current_path"])
        if not current_path.exists():
            errors.append(
                f"Market dataset file is missing: {current_path}"
            )

        if row.get("category") != contract.category:
            errors.append(
                f"Dataset '{name}' category is "
                f"{row.get('category')}, expected {contract.category}."
            )

        if int(row.get("column_count") or 0) == 0:
            warnings.append(f"Dataset '{name}' has zero columns.")

    return MarketValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        datasets_checked=len(MARKET_DATASET_CONTRACTS),
    )
