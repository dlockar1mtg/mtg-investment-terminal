from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from terminal2.secret_lair.pricing_contracts import (
    SECRET_LAIR_PRICING_CONTRACTS,
)
from terminal2.warehouse_core import get_warehouse_config


@dataclass(frozen=True)
class SecretLairPricingValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int
    observation_count: int


def validate_secret_lair_pricing(
    project_root: Path | None = None,
) -> SecretLairPricingValidationResult:
    config = get_warehouse_config(project_root)
    manifest_path = (
        config.manifests_root / "dataset_manifest.csv"
    )
    errors: list[str] = []
    warnings: list[str] = []
    observation_count = 0

    if not manifest_path.exists():
        return SecretLairPricingValidationResult(
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
    for name, contract in (
        SECRET_LAIR_PRICING_CONTRACTS.items()
    ):
        row = manifest.get(name)
        if row is None:
            errors.append(
                f"Required Secret Lair pricing dataset "
                f"is missing: {name}"
            )
            continue

        path = Path(row["current_path"])
        if not path.exists():
            errors.append(
                f"Secret Lair pricing dataset file "
                f"is missing: {path}"
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
            duplicate_count = int(
                keys.duplicated().sum()
            )
            if duplicate_count:
                errors.append(
                    f"Dataset '{name}' has "
                    f"{duplicate_count} duplicate key row(s)."
                )

    observations = frames.get(
        "secret_lair_price_observations"
    )
    if observations is not None:
        observation_count = len(observations)
        if observations.empty:
            warnings.append(
                "Secret Lair price history is empty. "
                "Import curated observations before scoring."
            )

    quality = frames.get("secret_lair_price_quality")
    if quality is not None and not quality.empty:
        error_findings = quality[
            quality["severity"].eq("Error")
        ]
        if not error_findings.empty:
            errors.append(
                "Secret Lair price-quality output contains "
                f"{len(error_findings)} error finding(s)."
            )

    return SecretLairPricingValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        datasets_checked=len(
            SECRET_LAIR_PRICING_CONTRACTS
        ),
        observation_count=observation_count,
    )
