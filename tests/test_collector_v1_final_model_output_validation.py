from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_final_model_output_validation_contract_v1.json"
SCRIPT = ROOT / "scripts/build_collector_v1_final_model_output_validation.py"


def test_contract_exists_and_has_complete_horizons():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["horizons_days"] == [90, 180, 365, 730, 1095, 1825]
    assert contract["required_forecast_products"] == 49
    assert contract["required_forecast_rows"] == 294
    assert contract["required_coverage_rows"] == 300
    assert contract["simulation_count"] == 10000


def test_contract_separates_growth_tiers():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    early = contract["early_awareness"]
    assert early["strong_growth_return_floor"] == 0.50
    assert early["exceptional_breakout_quantile"] == 0.75
    assert early["day30_status"] == "INSUFFICIENT_DIFFERENTIATING_EVIDENCE"
    assert contract["governance"]["strong_growth_and_exceptional_breakout_must_be_separate"] is True
    assert contract["governance"]["edge_of_eternities_must_be_evaluated_as_strong_growth"] is True


def test_governance_stays_fail_closed():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    governance = contract["governance"]
    assert governance["generic_method_prohibited"] is True
    assert governance["every_forecast_requires_explicit_method"] is True
    assert governance["every_forecast_requires_monte_carlo"] is True
    assert governance["lorwyn_supply_overlay_neutral"] is True
    assert governance["lotr_special_edition_user_exclusion_preserved"] is True
    assert governance["production_forecast_authorized"] is False
    assert governance["ranking_authorized"] is False
    assert governance["purchase_recommendations_authorized"] is False


def test_script_contains_required_output_and_validation_controls():
    text = SCRIPT.read_text(encoding="utf-8")
    required_tokens = [
        "collector_final_integrated_49_product_forecasts.csv",
        "collector_final_first_year_growth_truth_registry.csv",
        "collector_final_early_awareness_tier_metrics.csv",
        "collector_final_forecast_reasonableness_review.csv",
        "EDGE_OF_ETERNITIES_NOT_CLASSIFIED_AS_STRONG_GROWTH",
        "NON_MONOTONIC_FORECAST_QUANTILES",
        "EXTREME_FIVE_YEAR_MEDIAN_CAGR_REVIEW",
        "FINAL_BLOCKED_COVERAGE_MUST_BE_ONE_PRODUCT_SIX_HORIZONS",
    ]
    for token in required_tokens:
        assert token in text
