from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT_PATH = (
    ROOT
    / "config"
    / "mtg"
    / "evidence"
    / "collector_evidence_contract_v1.json"
)


def load_contract() -> dict:
    return json.loads(
        CONTRACT_PATH.read_text(
            encoding="utf-8-sig"
        )
    )


def test_contract_uses_governed_standard() -> None:
    contract = load_contract()

    assert (
        contract["standard_name"]
        == "MTG Forecasting and Decision Standard"
    )
    assert contract["standard_version"] == "1.0.0"
    assert contract["lane"] == "COLLECTOR_BOOSTER"


def test_supply_contract_contains_required_dimensions() -> None:
    contract = load_contract()
    fields = set(contract["required_supply_fields"])

    required = {
        "print_structure_class",
        "supply_profile_class",
        "restock_status",
        "retail_availability_score",
        "marketplace_listing_count",
        "marketplace_listing_trend",
        "sealed_supply_trend",
        "reprint_exposure_score",
        "supply_evidence_type",
        "supply_confidence_class",
        "supply_source_summary",
        "supply_observed_at",
    }

    assert required.issubset(fields)


def test_demand_contract_contains_required_dimensions() -> None:
    contract = load_contract()
    fields = set(contract["required_demand_fields"])

    required = {
        "sales_velocity_score",
        "transaction_count",
        "listing_absorption_score",
        "price_resilience_score",
        "franchise_strength_score",
        "gameplay_demand_score",
        "premium_contents_score",
        "chase_card_strength_score",
        "expected_value_support_score",
        "demand_evidence_type",
        "demand_confidence_class",
        "demand_source_summary",
        "demand_observed_at",
    }

    assert required.issubset(fields)


def test_liquidity_contract_contains_required_dimensions() -> None:
    contract = load_contract()
    fields = set(contract["required_liquidity_fields"])

    required = {
        "liquidity_score",
        "transaction_frequency_score",
        "market_depth_score",
        "estimated_exit_days",
        "liquidity_evidence_type",
        "liquidity_confidence_class",
        "liquidity_source_summary",
        "liquidity_observed_at",
    }

    assert required.issubset(fields)


def test_comparable_contract_contains_required_dimensions() -> None:
    contract = load_contract()
    fields = set(contract["required_comparable_fields"])

    required = {
        "release_era_class",
        "lifecycle_stage",
        "price_band_class",
        "franchise_class",
        "premium_contents_class",
        "supply_profile_class",
        "liquidity_class",
        "reprint_exposure_class",
    }

    assert required.issubset(fields)


def test_missing_values_cannot_be_hidden() -> None:
    rules = load_contract()["rules"]

    assert rules[
        "missing_values_must_not_be_silently_imputed"
    ] is True

    assert rules[
        "unknown_print_run_must_remain_unknown"
    ] is True

    assert rules[
        "all_estimates_require_method_and_source"
    ] is True


def test_comparable_forecast_requires_all_evidence_groups() -> None:
    rules = load_contract()["rules"]

    assert rules[
        "comparable_forecast_requires_supply_evidence"
    ] is True

    assert rules[
        "comparable_forecast_requires_demand_evidence"
    ] is True

    assert rules[
        "comparable_forecast_requires_liquidity_evidence"
    ] is True

    assert rules[
        "comparable_forecast_requires_comparable_dimensions"
    ] is True


def test_purchase_authorization_remains_false() -> None:
    contract = load_contract()

    assert contract["rules"][
        "purchase_recommendation_authorized"
    ] is False