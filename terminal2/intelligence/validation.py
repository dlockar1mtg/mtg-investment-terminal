from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from terminal2.intelligence.contracts import (
    INTELLIGENCE_DATASET_CONTRACTS,
)
from terminal2.warehouse_core import (
    get_warehouse_config,
)


@dataclass(frozen=True)
class IntelligenceValidationResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    datasets_checked: int
    products_checked: int


def validate_core_intelligence(
    project_root: Path | None = None,
) -> IntelligenceValidationResult:
    config = get_warehouse_config(project_root)
    manifest_path = (
        config.manifests_root
        / "dataset_manifest.csv"
    )
    errors: list[str] = []
    warnings: list[str] = []
    products_checked = 0

    if not manifest_path.exists():
        return IntelligenceValidationResult(
            False,
            (
                f"Dataset manifest is missing: "
                f"{manifest_path}",
            ),
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
    for (
        name,
        contract,
    ) in INTELLIGENCE_DATASET_CONTRACTS.items():
        row = manifest.get(name)
        if row is None:
            errors.append(
                f"Required intelligence dataset "
                f"is missing: {name}"
            )
            continue

        path = Path(row["current_path"])
        if not path.exists():
            errors.append(
                f"Intelligence dataset file "
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
                f"Dataset '{name}' is missing "
                f"columns: {missing}"
            )

        if (
            contract.primary_key
            and not frame.empty
        ):
            keys = frame[
                list(contract.primary_key)
            ]
            if keys.isna().any(axis=None):
                errors.append(
                    f"Dataset '{name}' contains "
                    "null key values."
                )
            duplicate_count = int(
                keys.duplicated().sum()
            )
            if duplicate_count:
                errors.append(
                    f"Dataset '{name}' has "
                    f"{duplicate_count} duplicate "
                    "primary-key row(s)."
                )

    recommendations = frames.get(
        "intelligence_recommendations"
    )
    if recommendations is not None:
        products_checked = len(recommendations)
        if recommendations.empty:
            errors.append(
                "The intelligence recommendation "
                "dataset is empty."
            )
        else:
            invalid_recommendations = (
                recommendations[
                    ~recommendations[
                        "recommendation"
                    ].isin(
                        [
                            "Strong Buy",
                            "Buy",
                            "Watch",
                            "Hold",
                            "Avoid",
                            "Insufficient Data",
                        ]
                    )
                ]
            )
            if not invalid_recommendations.empty:
                errors.append(
                    "Recommendation output contains "
                    "unsupported labels."
                )

            confidence = pd.to_numeric(
                recommendations[
                    "overall_confidence_score"
                ],
                errors="coerce",
            )
            risk = pd.to_numeric(
                recommendations[
                    "overall_risk_score"
                ],
                errors="coerce",
            )
            if (
                confidence.lt(0).any()
                or confidence.gt(100).any()
                or risk.lt(0).any()
                or risk.gt(100).any()
            ):
                errors.append(
                    "Risk or confidence scores are "
                    "outside the 0-100 range."
                )

            insufficient = int(
                recommendations[
                    "recommendation"
                ].eq("Insufficient Data").sum()
            )
            if insufficient:
                warnings.append(
                    f"{insufficient} product(s) have "
                    "insufficient evidence for an "
                    "actionable recommendation."
                )

    return IntelligenceValidationResult(
        passed=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        datasets_checked=len(
            INTELLIGENCE_DATASET_CONTRACTS
        ),
        products_checked=products_checked,
    )
