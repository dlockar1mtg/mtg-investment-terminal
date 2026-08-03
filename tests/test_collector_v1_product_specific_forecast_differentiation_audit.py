from __future__ import annotations

import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_product_specific_forecast_differentiation_contract_v1.json"
SCRIPT = ROOT / "scripts/audit_collector_v1_product_specific_forecast_differentiation.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_and_script_exist_and_compile() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_contract_freezes_product_specific_governance() -> None:
    contract = load_contract()
    assert contract["snapshot_id"] == "collector-20260801T211201Z-7688afbd"
    assert contract["required_product_rows"] == 50
    assert contract["required_forecasted_products"] == 48
    assert contract["required_blocked_products"] == 2
    assert contract["required_horizons"] == [90, 180, 365]
    governance = contract["governance"]
    assert governance["product_specific_inputs_required"] is True
    assert governance["direct_history_uses_product_history_only"] is True
    assert governance["comparable_route_uses_target_specific_comparable_set"] is True
    assert governance["global_route_median_as_final_forecast_prohibited"] is True
    assert governance["identical_returns_require_provenance_explanation"] is True
    assert governance["production_forecast_authorized"] is False
    assert governance["ranking_authorized"] is False
    assert governance["purchase_recommendations_authorized"] is False


def test_audit_contains_required_fail_closed_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "CURRENT_PRODUCTION_FORECASTS_NOT_PRODUCT_SPECIFIC",
        "IDENTICAL_RETURNS_LACK_PRODUCT_LEVEL_PROVENANCE",
        "HISTORY_SCHEMA_INCOMPLETE_FOR_PRODUCT_SPECIFIC_REFIT",
        "COMPARABLE_SCHEMA_INCOMPLETE_FOR_TARGET_SPECIFIC_FORECAST",
        "collector_current_forecast_return_dispersion.csv",
        "collector_identical_return_groups.csv",
        "collector_product_specific_source_schema_inventory.csv",
        "production_forecast_authorized",
        "purchase_recommendations_authorized",
    ]:
        assert token in text


def test_dispersion_thresholds_are_material() -> None:
    contract = load_contract()
    assert contract["minimum_within_route_unique_return_ratio"] >= 0.35
    assert contract["maximum_single_return_share"] <= 0.35
