from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from terminal2.secret_lair.backfill.contracts import (
    SECRET_LAIR_BACKFILL_CONTRACTS,
)
from terminal2.warehouse_core import get_warehouse_config


@dataclass(frozen=True)
class SecretLairBackfillValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int
    catalog_rows: int
    review_rows: int


def validate_secret_lair_backfill(
    project_root: Path | None = None,
) -> SecretLairBackfillValidationResult:
    config = get_warehouse_config(project_root)
    manifest_path = (
        config.manifests_root / "dataset_manifest.csv"
    )
    errors: list[str] = []
    warnings: list[str] = []
    catalog_rows = 0
    review_rows = 0

    if not manifest_path.exists():
        return SecretLairBackfillValidationResult(
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

    frames = {}
    for name, contract in (
        SECRET_LAIR_BACKFILL_CONTRACTS.items()
    ):
        row = manifest.get(name)
        if row is None:
            errors.append(
                f"Required Secret Lair backfill dataset "
                f"is missing: {name}"
            )
            continue

        path = Path(row["current_path"])
        if not path.exists():
            errors.append(
                f"Secret Lair backfill dataset file "
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

    catalog = frames.get("secret_lair_source_catalog")
    if catalog is not None:
        catalog_rows = len(catalog)
        if catalog.empty:
            warnings.append(
                "Secret Lair source catalog is empty. "
                "Populate the source templates before applying."
            )

    review = frames.get("secret_lair_unmatched_review")
    if review is not None:
        review_rows = len(review)
        if review_rows:
            warnings.append(
                f"{review_rows} source row(s) require manual review."
            )

    matches = frames.get("secret_lair_match_results")
    if matches is not None and not matches.empty:
        rejected = int(
            matches["match_status"].eq("rejected").sum()
        )
        if rejected:
            warnings.append(
                f"{rejected} source row(s) were explicitly rejected."
            )

    return SecretLairBackfillValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        datasets_checked=len(
            SECRET_LAIR_BACKFILL_CONTRACTS
        ),
        catalog_rows=catalog_rows,
        review_rows=review_rows,
    )
