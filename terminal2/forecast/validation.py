from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from terminal2.forecast.contracts import FORECAST_DATASET_CONTRACTS
from terminal2.warehouse_core import get_warehouse_config


@dataclass(frozen=True)
class ForecastValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int


def validate_forecast_warehouse(
    project_root: Path | None = None,
) -> ForecastValidationResult:
    config = get_warehouse_config(project_root)
    manifest_path = config.manifests_root / "dataset_manifest.csv"
    errors: list[str] = []
    warnings: list[str] = []

    if not manifest_path.exists():
        return ForecastValidationResult(
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

    for name, contract in FORECAST_DATASET_CONTRACTS.items():
        row = manifest.get(name)
        if row is None:
            errors.append(f"Required forecast dataset is missing: {name}")
            continue

        path = Path(row["current_path"])
        if not path.exists():
            errors.append(f"Forecast dataset file is missing: {path}")
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
                frame[list(contract.primary_key)].duplicated().sum()
            )
            if duplicate_count:
                errors.append(
                    f"Dataset '{name}' has {duplicate_count} "
                    "duplicate primary-key row(s)."
                )

        if frame.empty:
            warnings.append(f"Forecast dataset '{name}' contains zero rows.")

        for column in (
            "forecast_confidence",
            "conviction_score",
            "uncertainty_score",
            "regime_score",
        ):
            if column in frame.columns and not frame.empty:
                values = pd.to_numeric(frame[column], errors="coerce")
                if values.isna().any():
                    errors.append(
                        f"Dataset '{name}' has nonnumeric values in {column}."
                    )
                if ((values < 0) | (values > 100)).any():
                    errors.append(
                        f"Dataset '{name}' has out-of-range values in {column}."
                    )

    return ForecastValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        datasets_checked=len(FORECAST_DATASET_CONTRACTS),
    )
