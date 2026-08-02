from __future__ import annotations

import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_product_specific_forecast_refit_contract_v1.json"
SCRIPT = ROOT / "scripts/build_collector_v1_product_specific_forecast_refit.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_and_script_exist_and_compile() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_exact_snapshot_and_counts() -> None:
    contract = load_contract()
    assert contract["snapshot_id"] == "collector-20260801T211201Z-7688afbd"
    assert contract["required_product_rows"] == 50
    assert contract["required_forecasted_products"] == 48
    assert contract["required_blocked_products"] == 2
    assert contract["required_forecast_rows"] == 115
    assert contract["required_certified_champion_groups"] == 6


def test_differentiation_thresholds_are_frozen() -> None:
    contract = load_contract()
    assert contract["minimum_within_route_unique_return_ratio"] == 0.35
    assert contract["maximum_single_return_share"] == 0.35


def test_product_specific_governance_is_fail_closed() -> None:
    governance = load_contract()["governance"]
    assert governance["champion_model_family_must_be_preserved"] is True
    assert governance["direct_history_uses_target_product_history_only"] is True
    assert governance["comparable_route_uses_target_specific_comparable_pool"] is True
    assert governance["lifecycle_matched_forecast_uses_target_age"] is True
    assert governance["global_route_return_as_final_forecast_prohibited"] is True
    assert governance["identical_returns_require_explicit_provenance"] is True
    assert governance["current_supply_demand_post_forecast_only"] is True
    assert governance["current_supply_demand_used_in_refit"] is False
    assert governance["production_forecast_authorized"] is False
    assert governance["ranking_authorized"] is False
    assert governance["purchase_recommendations_authorized"] is False


def test_only_certified_model_families_are_allowed() -> None:
    assert load_contract()["allowed_models"] == [
        "NAIVE_LAST_VALUE",
        "ROBUST_LOG_TREND",
        "COMPARABLE_MEDIAN_GROWTH",
        "COMPARABLE_LIFECYCLE_MATCHED",
    ]


def test_script_contains_required_product_specific_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "PRODUCT_HISTORY_ROBUST_LOG_TREND",
        "TARGET_SPECIFIC_RECENT_COMPARABLE_POOL_MEDIAN",
        "TARGET_SPECIFIC_LIFECYCLE_MATCHED_COMPARABLE_POOL",
        "DIFFERENTIATION_GATE_FAILED",
        "CURRENT_SUPPLY_DEMAND_ENTERED_REFIT",
        "collector_product_specific_forecast_provenance.csv",
        "collector_product_specific_forecast_dispersion.csv",
        "production_forecast_authorized",
        "purchase_recommendations_authorized",
    ]:
        assert token in text
