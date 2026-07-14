from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from terminal2.calibration.contracts import (
    CALIBRATION_DATASET_CONTRACTS,
)
from terminal2.warehouse_core import (
    get_warehouse_config,
)


@dataclass(frozen=True)
class CalibrationValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int
    archived_forecasts: int
    matured_forecasts: int


def validate_model_calibration(
    project_root: Path | None = None,
) -> CalibrationValidationResult:
    config = get_warehouse_config(project_root)
    manifest_path = (
        config.manifests_root
        / "dataset_manifest.csv"
    )
    errors: list[str] = []
    warnings: list[str] = []
    archived = 0
    matured = 0

    if not manifest_path.exists():
        return CalibrationValidationResult(
            False,
            (
                f"Dataset manifest is missing: "
                f"{manifest_path}",
            ),
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

    frames = {}
    for (
        name,
        contract,
    ) in CALIBRATION_DATASET_CONTRACTS.items():
        row = manifest.get(name)
        if row is None:
            errors.append(
                f"Required calibration dataset "
                f"is missing: {name}"
            )
            continue

        path = Path(row["current_path"])
        if not path.exists():
            errors.append(
                f"Calibration dataset file is "
                f"missing: {path}"
            )
            continue

        frame = pd.read_csv(path)
        frames[name] = frame
        missing = sorted(
            set(contract.required_columns)
            - set(frame.columns)
        )
        if missing:
            errors.append(
                f"Dataset '{name}' is missing "
                f"columns: {missing}"
            )

        if contract.primary_key and not frame.empty:
            keys = frame[
                list(contract.primary_key)
            ]
            if keys.isna().any(axis=None):
                errors.append(
                    f"Dataset '{name}' contains "
                    "null primary-key values."
                )
            duplicates = int(
                keys.duplicated().sum()
            )
            if duplicates:
                errors.append(
                    f"Dataset '{name}' contains "
                    f"{duplicates} duplicate "
                    "primary-key row(s)."
                )

    vintages = frames.get(
        "calibration_forecast_vintages"
    )
    if vintages is not None:
        archived = len(vintages)
        if vintages.empty:
            errors.append(
                "No forecast vintages were archived."
            )

    outcomes = frames.get(
        "calibration_realized_outcomes"
    )
    if outcomes is not None and not outcomes.empty:
        matured = int(
            outcomes["maturity_status"]
            .eq("matured")
            .sum()
        )

    if matured == 0:
        warnings.append(
            "No forecasts have matured yet. "
            "This is expected on the first calibration runs."
        )
    elif matured < 25:
        warnings.append(
            f"Only {matured} forecasts have matured; "
            "calibration metrics remain preliminary."
        )

    summary = frames.get(
        "calibration_executive_summary"
    )
    if summary is not None and len(summary) != 1:
        errors.append(
            "Calibration executive summary must "
            "contain exactly one row."
        )

    return CalibrationValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        datasets_checked=len(
            CALIBRATION_DATASET_CONTRACTS
        ),
        archived_forecasts=archived,
        matured_forecasts=matured,
    )
