from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv

import pandas as pd

from terminal2.warehouse_core import get_warehouse_config

from .contracts import RETURN_ANALYTICS_CONTRACTS


@dataclass(frozen=True)
class ReturnAnalyticsValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int
    products: int
    asset_classes: int
    analytics_ready: int
    rolling_12m_ready: int
    rolling_24m_ready: int


def validate_universal_return_analytics(project_root=None):
    config = get_warehouse_config(project_root)
    manifest_path = config.manifests_root / "dataset_manifest.csv"
    errors = []
    warnings = []
    frames = {}

    if not manifest_path.exists():
        return ReturnAnalyticsValidationResult(
            False,
            (f"Missing dataset manifest: {manifest_path}",),
            (),
            0,
            0,
            0,
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

    for name, contract in RETURN_ANALYTICS_CONTRACTS.items():
        row = manifest.get(name)
        if row is None:
            errors.append(f"Missing return analytics dataset: {name}")
            continue
        path = Path(row["current_path"])
        if not path.exists():
            errors.append(f"Missing return analytics file: {path}")
            continue
        frame = pd.read_csv(path)
        frames[name] = frame
        missing = set(contract.required_columns) - set(frame.columns)
        if missing:
            errors.append(
                f"{name} missing columns: {sorted(missing)}"
            )
        if contract.primary_key and not frame.empty:
            keys = frame[list(contract.primary_key)]
            if keys.isna().any(axis=None):
                errors.append(f"{name} has null primary-key values.")
            if keys.duplicated().any():
                errors.append(f"{name} has duplicate primary keys.")

    executive = frames.get(
        "universal_return_analytics_summary",
        pd.DataFrame(),
    )
    products = asset_classes = ready = r12 = r24 = 0
    if len(executive) != 1:
        errors.append(
            "Universal return analytics summary must contain one row."
        )
    else:
        row = executive.iloc[0]
        products = int(row["product_count"])
        asset_classes = int(row["asset_class_count"])
        ready = int(row["analytics_ready_count"])
        r12 = int(row["rolling_12m_ready_count"])
        r24 = int(row["rolling_24m_ready_count"])
        if asset_classes < 2:
            warnings.append(
                "Universal analytics currently contains fewer than two asset classes."
            )
        if ready == 0:
            warnings.append(
                "No products meet return-analytics readiness."
            )

    summary = frames.get(
        "universal_return_summary",
        pd.DataFrame(),
    )
    if not summary.empty:
        volatility = pd.to_numeric(
            summary["annualized_volatility"],
            errors="coerce",
        ).dropna()
        if volatility.lt(0).any():
            errors.append("Annualized volatility contains negatives.")
        drawdown = pd.to_numeric(
            summary["maximum_drawdown"],
            errors="coerce",
        ).dropna()
        if drawdown.gt(0).any():
            errors.append("Maximum drawdown contains positives.")

    rolling = frames.get(
        "universal_rolling_returns",
        pd.DataFrame(),
    )
    if not rolling.empty:
        returns = pd.to_numeric(
            rolling["monthly_return"],
            errors="coerce",
        ).dropna()
        if returns.lt(-1).any():
            errors.append("Monthly returns contain values below -100%.")

    rankings = frames.get(
        "universal_return_rankings",
        pd.DataFrame(),
    )
    coverage = frames.get(
        "universal_return_coverage",
        pd.DataFrame(),
    )
    if not rankings.empty and not coverage.empty:
        insufficient = set(
            coverage.loc[
                coverage["coverage_tier"].isin(
                    ["Emerging", "Insufficient"]
                ),
                "investment_product_id",
            ]
        )
        invalid = rankings[
            rankings["investment_product_id"].isin(insufficient)
            & rankings["composite_return_score"].notna()
        ]
        if not invalid.empty:
            errors.append(
                "Insufficient-history products received composite rankings."
            )

    return ReturnAnalyticsValidationResult(
        not errors,
        tuple(errors),
        tuple(warnings),
        len(RETURN_ANALYTICS_CONTRACTS),
        products,
        asset_classes,
        ready,
        r12,
        r24,
    )
