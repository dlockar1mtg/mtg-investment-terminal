from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.certify_collector_booster_history import (
    quality_band,
    run,
)


REGISTRY_FIELDS = [
    "investment_product_id",
    "set_name",
    "box_name",
    "approved_tcgplayer_product_id",
    "approved_product_name",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "investment_product_type",
    "approval_status",
    "approval_method",
    "notes",
]


MODEL_FIELDS = [
    "investment_product_id",
    "tcgplayer_product_id",
    "investment_product_type",
    "current_price",
]


HISTORY_FIELDS = [
    "investment_product_id",
    "tcgplayer_product_id",
    "observation_date",
    "consolidated_market_price",
]


def write_csv(
    path: Path,
    fields: list[str],
    rows: list[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_policy(path: Path) -> None:
    payload = {
        "policy_name": "collector_booster_history_certification",
        "policy_version": "1.0.0",
        "lane": "COLLECTOR_BOOSTER_BOX",
        "history_quality_bands": {
            "NONE": {
                "minimum_distinct_dates": 0,
                "maximum_distinct_dates": 1,
                "direct_forecast_allowed": False,
            },
            "VERY_LIMITED": {
                "minimum_distinct_dates": 2,
                "maximum_distinct_dates": 4,
                "direct_forecast_allowed": False,
            },
            "LIMITED": {
                "minimum_distinct_dates": 5,
                "maximum_distinct_dates": 11,
                "direct_forecast_allowed": False,
            },
            "MODERATE": {
                "minimum_distinct_dates": 12,
                "maximum_distinct_dates": 29,
                "direct_forecast_allowed": True,
            },
            "STRONG": {
                "minimum_distinct_dates": 30,
                "maximum_distinct_dates": None,
                "direct_forecast_allowed": True,
            },
        },
        "quality_thresholds": {
            "maximum_current_vs_history_discontinuity_pct": 50.0,
            "maximum_single_period_increase_pct": 100.0,
            "maximum_single_period_decrease_pct": -50.0,
            "maximum_annualized_volatility": 1.0,
            "minimum_positive_price": 1.0,
            "maximum_duplicate_date_rows": 0,
        },
        "product_universe": {
            "required_product_type": (
                "Collector Booster Display"
            ),
            "required_name_terms": [
                "collector booster",
                "display",
            ],
            "excluded_name_terms": [
                "master case",
                "box case",
                "display case",
                "collector booster case",
                "booster case",
                "case of",
                "mastercase",
                "booster pack",
                "single pack",
                "sample pack",
                "collector sample",
                "bundle",
            ],
            "require_model_input_reconciliation": True,
            "allow_filtered_registry_ids_missing_from_model": False,
            "allow_model_ids_missing_from_filtered_registry": False,
        },
    }

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def registry_row() -> dict[str, str]:
    return {
        "investment_product_id": "MTG:TEST:1",
        "set_name": "Test Set",
        "box_name": "Test Set Collector Booster Display",
        "approved_tcgplayer_product_id": "1001",
        "approved_product_name": (
            "Test Set - Collector Booster Display"
        ),
        "tcgcsv_category_id": "1",
        "tcgcsv_group_id": "100",
        "investment_product_type": (
            "Collector Booster Display"
        ),
        "approval_status": "approved",
        "approval_method": "governed_auto_admission_v1",
        "notes": "",
    }


def test_quality_bands() -> None:
    bands = {
        "NONE": {
            "minimum_distinct_dates": 0,
            "maximum_distinct_dates": 1,
        },
        "VERY_LIMITED": {
            "minimum_distinct_dates": 2,
            "maximum_distinct_dates": 4,
        },
        "LIMITED": {
            "minimum_distinct_dates": 5,
            "maximum_distinct_dates": 11,
        },
        "MODERATE": {
            "minimum_distinct_dates": 12,
            "maximum_distinct_dates": 29,
        },
        "STRONG": {
            "minimum_distinct_dates": 30,
            "maximum_distinct_dates": None,
        },
    }

    assert quality_band(1, bands) == "NONE"
    assert quality_band(4, bands) == "VERY_LIMITED"
    assert quality_band(11, bands) == "LIMITED"
    assert quality_band(29, bands) == "MODERATE"
    assert quality_band(30, bands) == "STRONG"


def test_strong_clean_history_is_forecast_eligible(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.csv"
    model = tmp_path / "model.csv"
    history = tmp_path / "history.csv"
    policy = tmp_path / "policy.json"
    output = tmp_path / "output"

    write_csv(
        registry,
        REGISTRY_FIELDS,
        [registry_row()],
    )

    write_csv(
        model,
        MODEL_FIELDS,
        [{
            "investment_product_id": "MTG:TEST:1",
            "tcgplayer_product_id": "1001",
            "investment_product_type": (
                "Collector Booster Display"
            ),
            "current_price": "158.00",
        }],
    )

    rows = []

    for month in range(1, 31):
        year = 2024 + ((month - 1) // 12)
        month_number = ((month - 1) % 12) + 1

        rows.append({
            "investment_product_id": "MTG:TEST:1",
            "tcgplayer_product_id": "1001",
            "observation_date": (
                f"{year}-{month_number:02d}-01"
            ),
            "consolidated_market_price": (
                f"{100 + month * 2:.2f}"
            ),
        })

    write_csv(
        history,
        HISTORY_FIELDS,
        rows,
    )
    write_policy(policy)

    manifest = run(
        registry_path=registry,
        model_path=model,
        history_path=history,
        policy_path=policy,
        output_root=output,
    )

    assert manifest["forecast_allowed_count"] == 1
    assert manifest["anomaly_product_count"] == 0


def test_large_price_jump_is_quarantined(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.csv"
    model = tmp_path / "model.csv"
    history = tmp_path / "history.csv"
    policy = tmp_path / "policy.json"
    output = tmp_path / "output"

    write_csv(
        registry,
        REGISTRY_FIELDS,
        [registry_row()],
    )

    write_csv(
        model,
        MODEL_FIELDS,
        [{
            "investment_product_id": "MTG:TEST:1",
            "tcgplayer_product_id": "1001",
            "investment_product_type": (
                "Collector Booster Display"
            ),
            "current_price": "500.00",
        }],
    )

    rows = [
        {
            "investment_product_id": "MTG:TEST:1",
            "tcgplayer_product_id": "1001",
            "observation_date": f"2024-{month:02d}-01",
            "consolidated_market_price": (
                "500.00"
                if month == 12
                else "100.00"
            ),
        }
        for month in range(1, 13)
    ]

    write_csv(
        history,
        HISTORY_FIELDS,
        rows,
    )
    write_policy(policy)

    manifest = run(
        registry_path=registry,
        model_path=model,
        history_path=history,
        policy_path=policy,
        output_root=output,
    )

    assert manifest["forecast_allowed_count"] == 0
    assert manifest["anomaly_product_count"] == 1


def test_new_product_remains_history_accumulating(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.csv"
    model = tmp_path / "model.csv"
    history = tmp_path / "history.csv"
    policy = tmp_path / "policy.json"
    output = tmp_path / "output"

    write_csv(
        registry,
        REGISTRY_FIELDS,
        [registry_row()],
    )

    write_csv(
        model,
        MODEL_FIELDS,
        [{
            "investment_product_id": "MTG:TEST:1",
            "tcgplayer_product_id": "1001",
            "investment_product_type": (
                "Collector Booster Display"
            ),
            "current_price": "150.00",
        }],
    )

    write_csv(
        history,
        HISTORY_FIELDS,
        [{
            "investment_product_id": "MTG:TEST:1",
            "tcgplayer_product_id": "1001",
            "observation_date": "2026-07-31",
            "consolidated_market_price": "150.00",
        }],
    )

    write_policy(policy)

    manifest = run(
        registry_path=registry,
        model_path=model,
        history_path=history,
        policy_path=policy,
        output_root=output,
    )

    assert manifest["forecast_allowed_count"] == 0
    assert manifest["forecast_blocked_count"] == 1