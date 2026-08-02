from __future__ import annotations

import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_early_awareness_lorwyn_forecast_contract_v1.json"
SCRIPT = ROOT / "scripts/build_collector_v1_early_awareness_lorwyn_forecast.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_files_exist_and_script_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_early_awareness_checkpoints_are_exact() -> None:
    c = load_contract()["early_awareness"]
    assert c["checkpoint_days"] == [30, 60, 90, 120, 180]
    assert c["truth_horizon_days"] == 365
    assert c["selection_cutoffs"] == [3, 5, 10]
    assert c["minimum_recall_at_top5"] == 0.5


def test_lorwyn_contract_requests_resolution_without_asserting_identity() -> None:
    c = load_contract()["lorwyn"]
    assert c["requested_product_name"] == "Lorwyn Eclipsed - Collector Booster Display"
    assert c["identity_resolution_authority"] == "collector_final_current_price_authority.csv"
    assert c["identity_resolution_mode"] == "EXACT_NORMALIZED_NAME_SINGLE_AUTHORITY_ROW"
    assert "canonical_product_id" not in c
    assert "tcgplayer_product_id" not in c
    assert "investment_product_id" not in c


def test_lorwyn_has_six_distinct_horizon_methods() -> None:
    c = load_contract()["lorwyn"]
    assert c["horizons_days"] == [90, 180, 365, 730, 1095, 1825]
    assert c["simulation_count"] == 10000
    assert len(c["method_ids"]) == 6
    assert len(set(c["method_ids"].values())) == 6


def test_lorwyn_supply_ambiguity_is_not_zero_supply() -> None:
    c = load_contract()["lorwyn"]
    assert c["supply_status"] == "EBAY_SUPPLY_IDENTITY_AMBIGUOUS"
    assert c["supply_overlay_status"] == "SUPPLY_OVERLAY_DEFERRED_IDENTITY_AMBIGUITY"
    assert c["forecast_status"] == "FORECAST_AUTHORIZED_WITH_ELEVATED_UNCERTAINTY"


def test_governance_is_fail_closed() -> None:
    g = load_contract()["governance"]
    assert g["strict_temporal_cutoffs_required"] is True
    assert g["future_observations_prohibited"] is True
    assert g["current_ebay_data_in_early_awareness_prohibited"] is True
    assert g["current_ebay_data_in_lorwyn_forecast_prohibited"] is True
    assert g["generic_route_return_prohibited"] is True
    assert g["lorwyn_must_have_distinct_method_per_horizon"] is True
    assert g["lorwyn_supply_ambiguity_must_not_block_price_forecast"] is True
    assert g["product_specific_contract_identity_assertions_prohibited"] is True
    assert g["identity_must_be_resolved_exclusively_from_certified_authority"] is True
    assert g["semantic_certification_required_before_simulation"] is True
    assert g["lotr_special_edition_user_exclusion_preserved"] is True
    assert g["production_forecast_authorized"] is False
    assert g["ranking_authorized"] is False
    assert g["purchase_recommendations_authorized"] is False


def test_script_contains_required_outputs_and_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "collector_first_year_breakout_truth_registry.csv",
        "collector_early_awareness_checkpoint_predictions.csv",
        "collector_early_awareness_metric_summary.csv",
        "collector_early_awareness_false_positives.csv",
        "collector_early_awareness_false_negatives.csv",
        "collector_lorwyn_standalone_probabilistic_forecasts.csv",
        "EARLY_AWARENESS_SELECTION_GATE_NOT_MET",
        "LORWYN_SIX_HORIZON_FORECAST_COUNT_MISMATCH",
        "future_observations_used",
        "current_ebay_data_used",
    ]:
        assert token in text
