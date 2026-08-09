from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_forecast_input_assembly_method_certification_contract_v1.json"
BUILDER = ROOT / "scripts/build_precollector_forecast_input_assembly_method_certification.py"
CORRECTED_BUILDER = ROOT / "scripts/build_precollector_forecast_input_assembly_method_certification_v1_1.py"
ADAPTER = ROOT / "scripts/build_precollector_comparable_tournament_winner_adapter.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_declares_exact_five_horizons() -> None:
    contract = load_contract()
    assert contract["expected_horizon_count"] == 5
    assert [(h["horizon_code"], h["horizon_days"]) for h in contract["forecast_horizons"]] == [
        ("D90", 90), ("D180", 180), ("D365", 365), ("Y3", 1095), ("Y5", 1825)
    ]


def test_contract_preserves_79_active_and_15_excluded() -> None:
    contract = load_contract()
    assert contract["expected_active_product_count"] == 79
    assert contract["expected_excluded_product_count"] == 15


def test_contract_requires_rank_decay_comparable_model() -> None:
    assert load_contract()["required_selected_comparable_model"] == "RANK_DECAY"


def test_contract_keeps_all_downstream_authority_false() -> None:
    contract = load_contract()
    for key in [
        "forecast_generation_authorized", "ranking_execution_authorized",
        "purchase_analysis_authorized", "purchase_recommendation_authorized",
        "automatic_purchase_execution_authorized", "uip_delivery_authorized",
    ]:
        assert contract[key] is False


def test_contract_advances_only_to_horizon_architecture() -> None:
    assert load_contract()["next_stage_if_certified"] == "PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_ARCHITECTURE"


def test_builder_declares_independent_horizon_tournaments() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert '"independent_horizon_tournament_required": True' in text
    assert '"horizon_winner_selected": False' in text
    assert '"forecast_generation_authorized": False' in text


def test_builder_enforces_exclusion_and_complete_horizon_controls() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert "EXCLUDED_PRODUCT_LEAKAGE" in text
    assert "INCOMPLETE_PRODUCT_HORIZON_COVERAGE" in text
    assert "HORIZON_MATRIX_ROW_COUNT_DRIFT" in text


def test_winner_adapter_is_fail_closed() -> None:
    text = ADAPTER.read_text(encoding="utf-8")
    assert "TOURNAMENT_NOT_CERTIFIED" in text
    assert "TOURNAMENT_WINNER_MISSING" in text
    assert '"forecast_generation_authorized": False' in text


def test_schema_overlap_correction_preserves_selected_evidence_authority() -> None:
    text = CORRECTED_BUILDER.read_text(encoding="utf-8")
    assert "FORECAST_INPUT_BASE_SCHEMA_PATCH_TARGET_NOT_FOUND" in text
    assert '"canonical_product_id", "forecast_method",' in text
    assert '"confidence_penalty_required", "route_version"' in text
    corrected_route_block = text.split("NEW_ROUTE_SUBSET =", 1)[1]
    assert '"historical_rows"' not in corrected_route_block.split("def main", 1)[0]
    assert '"history_span_days"' not in corrected_route_block.split("def main", 1)[0]


def test_builder_module_loads() -> None:
    spec = importlib.util.spec_from_file_location("forecast_input_builder", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


def test_corrected_builder_module_loads() -> None:
    spec = importlib.util.spec_from_file_location("forecast_input_builder_v1_1", CORRECTED_BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
