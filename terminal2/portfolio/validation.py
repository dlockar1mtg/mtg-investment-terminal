from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from terminal2.portfolio.contracts import PORTFOLIO_DATASET_CONTRACTS
from terminal2.warehouse_core import get_warehouse_config


@dataclass(frozen=True)
class PortfolioValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int


def validate_portfolio_warehouse(
    project_root: Path | None = None,
) -> PortfolioValidationResult:
    config = get_warehouse_config(project_root)
    manifest_path = config.manifests_root / "dataset_manifest.csv"
    errors: list[str] = []
    warnings: list[str] = []

    if not manifest_path.exists():
        return PortfolioValidationResult(
            False,
            (f"Dataset manifest is missing: {manifest_path}",),
            (),
            0,
        )

    with manifest_path.open(
        "r", newline="", encoding="utf-8"
    ) as handle:
        manifest = {
            row["dataset_name"]: row
            for row in csv.DictReader(handle)
        }

    for name, contract in PORTFOLIO_DATASET_CONTRACTS.items():
        row = manifest.get(name)
        if row is None:
            errors.append(
                f"Required portfolio dataset is missing: {name}"
            )
            continue

        path = Path(row["current_path"])
        if not path.exists():
            errors.append(
                f"Portfolio dataset file is missing: {path}"
            )
            continue

        frame = pd.read_csv(path)
        missing = sorted(
            set(contract.required_columns) - set(frame.columns)
        )
        if missing:
            errors.append(
                f"Dataset '{name}' is missing columns: {missing}"
            )

        if contract.primary_key and not frame.empty:
            duplicate_count = int(
                frame[list(contract.primary_key)]
                .duplicated()
                .sum()
            )
            if duplicate_count:
                errors.append(
                    f"Dataset '{name}' has {duplicate_count} "
                    "duplicate primary-key row(s)."
                )

        if frame.empty and name not in {
            "portfolio_positions",
            "portfolio_allocation",
        }:
            warnings.append(
                f"Portfolio dataset '{name}' contains zero rows."
            )

    return PortfolioValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        datasets_checked=len(PORTFOLIO_DATASET_CONTRACTS),
    )
