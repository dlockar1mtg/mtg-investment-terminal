from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from terminal2.history.contracts import HISTORICAL_DATASET_CONTRACTS
from terminal2.warehouse_core import get_warehouse_config


@dataclass(frozen=True)
class HistoricalValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int
    duplicate_key_rows: int
    invalid_date_rows: int


def validate_historical_warehouse(
    project_root: Path | None = None,
) -> HistoricalValidationResult:
    config = get_warehouse_config(project_root)
    manifest_path = (
        config.manifests_root / "dataset_manifest.csv"
    )

    errors: list[str] = []
    warnings: list[str] = []
    duplicate_key_rows = 0
    invalid_date_rows = 0

    if not manifest_path.exists():
        return HistoricalValidationResult(
            False,
            (f"Dataset manifest is missing: {manifest_path}",),
            (),
            0,
            0,
            0,
        )

    with manifest_path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        manifest = {
            row["dataset_name"]: row
            for row in csv.DictReader(handle)
        }

    for name, contract in HISTORICAL_DATASET_CONTRACTS.items():
        row = manifest.get(name)
        if row is None:
            errors.append(
                f"Required historical dataset is missing: {name}"
            )
            continue

        path = Path(row["current_path"])
        if not path.exists():
            errors.append(
                f"Historical dataset file is missing: {path}"
            )
            continue

        dataframe = pd.read_csv(path)
        missing_columns = sorted(
            set(contract.required_columns)
            - set(dataframe.columns)
        )
        if missing_columns:
            errors.append(
                f"Dataset '{name}' is missing columns: "
                f"{missing_columns}"
            )

        if contract.primary_key and not dataframe.empty:
            duplicates = int(
                dataframe[
                    list(contract.primary_key)
                ].duplicated().sum()
            )
            duplicate_key_rows += duplicates
            if duplicates:
                errors.append(
                    f"Dataset '{name}' has {duplicates} duplicate "
                    "primary-key row(s)."
                )

        date_columns = [
            column
            for column in (
                "observation_date",
                "first_observation_date",
                "latest_observation_date",
                "snapshot_date",
            )
            if column in dataframe.columns
        ]
        for column in date_columns:
            values = dataframe[column].replace("", pd.NA).dropna()
            invalid = int(
                pd.to_datetime(
                    values,
                    errors="coerce",
                ).isna().sum()
            )
            invalid_date_rows += invalid
            if invalid:
                errors.append(
                    f"Dataset '{name}' has {invalid} invalid "
                    f"value(s) in {column}."
                )

        if dataframe.empty:
            warnings.append(
                f"Historical dataset '{name}' contains zero rows."
            )

    return HistoricalValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        datasets_checked=len(HISTORICAL_DATASET_CONTRACTS),
        duplicate_key_rows=duplicate_key_rows,
        invalid_date_rows=invalid_date_rows,
    )
