from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from terminal2.semantic.contracts import SEMANTIC_DATASET_CONTRACTS
from terminal2.warehouse_core import get_warehouse_config


@dataclass(frozen=True)
class SemanticValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int
    orphan_rows: int


def validate_semantic_layer(
    project_root: Path | None = None,
) -> SemanticValidationResult:
    config = get_warehouse_config(project_root)
    manifest_path = config.manifests_root / "dataset_manifest.csv"
    errors: list[str] = []
    warnings: list[str] = []
    orphan_rows = 0

    if not manifest_path.exists():
        return SemanticValidationResult(
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

    frames: dict[str, pd.DataFrame] = {}
    for name, contract in SEMANTIC_DATASET_CONTRACTS.items():
        row = manifest.get(name)
        if row is None:
            errors.append(
                f"Required semantic dataset is missing: {name}"
            )
            continue

        path = Path(row["current_path"])
        if not path.exists():
            errors.append(
                f"Semantic dataset file is missing: {path}"
            )
            continue

        frame = pd.read_csv(path)
        frames[name] = frame

        missing = sorted(
            set(contract.required_columns) - set(frame.columns)
        )
        if missing:
            errors.append(
                f"Dataset '{name}' is missing columns: {missing}"
            )

        if contract.primary_key and not frame.empty:
            keys = frame[list(contract.primary_key)]
            null_keys = int(keys.isna().any(axis=1).sum())
            duplicates = int(keys.duplicated().sum())
            if null_keys:
                errors.append(
                    f"Dataset '{name}' has {null_keys} null key row(s)."
                )
            if duplicates:
                errors.append(
                    f"Dataset '{name}' has {duplicates} "
                    "duplicate primary-key row(s)."
                )

        if frame.empty and name not in {
            "semantic_fact_portfolio",
        }:
            warnings.append(
                f"Semantic dataset '{name}' contains zero rows."
            )

    product_dimension = frames.get("semantic_dim_product")
    if product_dimension is not None:
        valid_products = set(product_dimension["ProductKey"])
        for name in (
            "semantic_fact_product_snapshot",
            "semantic_fact_price_history",
            "semantic_fact_forecast",
            "semantic_fact_portfolio",
        ):
            fact = frames.get(name)
            if fact is None or fact.empty:
                continue
            orphans = int(
                (~fact["ProductKey"].isin(valid_products)).sum()
            )
            orphan_rows += orphans
            if orphans:
                errors.append(
                    f"Dataset '{name}' has {orphans} orphan ProductKey row(s)."
                )

    date_dimension = frames.get("semantic_dim_date")
    if date_dimension is not None:
        valid_dates = set(date_dimension["DateKey"])
        for name, column in (
            ("semantic_fact_price_history", "DateKey"),
            ("semantic_executive_kpis", "SnapshotDateKey"),
        ):
            fact = frames.get(name)
            if fact is None or fact.empty:
                continue
            orphans = int(
                (~fact[column].isin(valid_dates)).sum()
            )
            orphan_rows += orphans
            if orphans:
                errors.append(
                    f"Dataset '{name}' has {orphans} orphan {column} row(s)."
                )

    relationships = frames.get("semantic_relationship_map")
    if relationships is not None:
        known_tables = set(SEMANTIC_DATASET_CONTRACTS)
        referenced = set(relationships["FromTable"]) | set(
            relationships["ToTable"]
        )
        unknown = sorted(referenced - known_tables)
        if unknown:
            errors.append(
                f"Relationship map references unknown tables: {unknown}"
            )

    return SemanticValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        datasets_checked=len(SEMANTIC_DATASET_CONTRACTS),
        orphan_rows=orphan_rows,
    )
