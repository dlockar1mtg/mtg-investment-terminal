from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from terminal2.secret_lair.contracts import (
    SECRET_LAIR_DATASET_CONTRACTS,
)
from terminal2.warehouse_core import get_warehouse_config


@dataclass(frozen=True)
class SecretLairValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int
    registry_assets: int


def validate_secret_lair_warehouse(
    project_root: Path | None = None,
) -> SecretLairValidationResult:
    config = get_warehouse_config(project_root)
    manifest_path = (
        config.manifests_root / "dataset_manifest.csv"
    )
    errors: list[str] = []
    warnings: list[str] = []
    registry_assets = 0

    if not manifest_path.exists():
        return SecretLairValidationResult(
            False,
            (f"Dataset manifest is missing: {manifest_path}",),
            (),
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
    for name, contract in SECRET_LAIR_DATASET_CONTRACTS.items():
        row = manifest.get(name)
        if row is None:
            errors.append(
                f"Required Secret Lair dataset is missing: {name}"
            )
            continue

        path = Path(row["current_path"])
        if not path.exists():
            errors.append(
                f"Secret Lair dataset file is missing: {path}"
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
                f"Dataset '{name}' is missing columns: {missing}"
            )

        if contract.primary_key and not frame.empty:
            keys = frame[list(contract.primary_key)]
            if keys.isna().any(axis=None):
                errors.append(
                    f"Dataset '{name}' contains null key values."
                )
            duplicates = int(keys.duplicated().sum())
            if duplicates:
                errors.append(
                    f"Dataset '{name}' has {duplicates} "
                    "duplicate primary-key row(s)."
                )

    registry = frames.get("secret_lair_registry")
    if registry is not None:
        registry_assets = len(registry)
        if registry.empty:
            warnings.append(
                "Secret Lair registry is empty. Import curated "
                "assets before pricing work begins."
            )

    quality = frames.get("secret_lair_data_quality")
    if quality is not None and not quality.empty:
        error_findings = quality[
            quality["severity"].eq("Error")
        ]
        if not error_findings.empty:
            errors.append(
                f"Secret Lair data-quality output contains "
                f"{len(error_findings)} error finding(s)."
            )

    return SecretLairValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        datasets_checked=len(
            SECRET_LAIR_DATASET_CONTRACTS
        ),
        registry_assets=registry_assets,
    )
