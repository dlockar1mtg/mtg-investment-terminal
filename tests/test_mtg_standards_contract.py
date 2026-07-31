from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

STANDARD_PATH = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "mtg_forecasting_standard_v1.json"
)


def load_standard() -> dict:
    return json.loads(
        STANDARD_PATH.read_text(
            encoding="utf-8-sig"
        )
    )


def test_standard_has_three_required_lanes() -> None:
    standard = load_standard()

    assert set(standard["lanes"]) == {
        "COLLECTOR_BOOSTER",
        "PRE_COLLECTOR_BOOSTER",
        "SECRET_LAIR",
    }


def test_comparable_method_is_governed() -> None:
    standard = load_standard()

    assert (
        "COMPARABLE_PRODUCT_ADJUSTED"
        in standard["common_methods"]
    )

    assert (
        "COMPARABLE_PRODUCT_ADJUSTED"
        in standard[
            "lanes"
        ]["COLLECTOR_BOOSTER"]["supported_methods"]
    )


def test_direct_history_and_total_forecast_are_distinct() -> None:
    standard = load_standard()

    fields = set(
        standard["required_eligibility_fields"]
    )

    assert "direct_history_method_allowed" in fields
    assert "comparable_method_allowed" in fields
    assert "forecast_output_allowed" in fields
    assert "purchase_analysis_allowed" in fields
    assert (
        "purchase_recommendation_authorized"
        in fields
    )


def test_required_horizons_are_one_three_five() -> None:
    standard = load_standard()

    assert standard[
        "forecast_horizons_years"
    ] == [1, 3, 5]


def test_required_scenarios_are_governed() -> None:
    standard = load_standard()

    assert standard["scenario_names"] == [
        "DOWNSIDE",
        "BASE",
        "UPSIDE",
    ]


def test_required_output_discloses_method_and_evidence() -> None:
    standard = load_standard()
    fields = set(
        standard["required_product_output_fields"]
    )

    required = {
        "forecast_method",
        "forecast_method_version",
        "method_reason",
        "comparable_products_used",
        "comparable_selection_basis",
        "confidence_score",
        "confidence_class",
        "limitations",
        "source_summary",
    }

    assert required.issubset(fields)


def test_purchase_authorization_is_separate() -> None:
    standard = load_standard()
    fields = set(
        standard["required_product_output_fields"]
    )

    assert "forecast_output_allowed" in fields
    assert "purchase_analysis_allowed" in fields
    assert (
        "purchase_recommendation_authorized"
        in fields
    )