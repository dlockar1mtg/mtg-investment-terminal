from __future__ import annotations

import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_complete_horizon_probabilistic_forecast_contract_v1.json"
SCRIPT = ROOT / "scripts/build_collector_v1_complete_horizon_probabilistic_forecasts.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_and_script_exist_and_compile() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_all_six_horizons_are_required() -> None:
    contract = load_contract()
    assert contract["horizons_days"] == [90, 180, 365, 730, 1095, 1825]
    assert contract["required_authorized_products"] == 48
    assert contract["required_forecast_rows"] == 288
    assert contract["required_coverage_rows"] == 300


def test_monte_carlo_is_required_for_every_horizon() -> None:
    contract = load_contract()
    assert contract["monte_carlo"]["simulations_per_product_horizon"] == 10000
    governance = contract["governance"]
    assert governance["monte_carlo_required_for_every_authorized_product_horizon"] is True
    assert governance["long_horizons_require_monte_carlo"] is True
    assert governance["random_seed_must_be_snapshot_product_horizon_specific"] is True


def test_generic_methods_are_prohibited() -> None:
    governance = load_contract()["governance"]
    assert governance["every_authorized_product_has_every_horizon"] is True
    assert governance["every_product_horizon_has_explicit_method_or_block_reason"] is True
    assert governance["generic_route_return_prohibited"] is True
    assert governance["global_median_as_final_forecast_prohibited"] is True


def test_method_families_are_explicit_and_product_specific() -> None:
    methods = load_contract()["method_families"]
    assert methods == {
        "DIRECT_HISTORY_CALIBRATED": "PRODUCT_DIRECT_EMPIRICAL_RESIDUAL_BOOTSTRAP_MC",
        "DIRECT_HISTORY_LIMITED": "PRODUCT_HIERARCHICAL_SHRUNK_BOOTSTRAP_MC",
        "COMPARABLE_PRODUCT_ADJUSTED": "TARGET_SPECIFIC_COMPARABLE_LIFECYCLE_BOOTSTRAP_MC",
    }


def test_supply_and_authorization_controls_remain_closed() -> None:
    governance = load_contract()["governance"]
    assert governance["current_supply_demand_used_in_forecast"] is False
    assert governance["production_forecast_authorized"] is False
    assert governance["ranking_authorized"] is False
    assert governance["purchase_recommendations_authorized"] is False


def test_script_contains_required_probabilistic_outputs_and_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "deterministic_seed",
        "simulation_count",
        "probability_of_loss",
        "probability_of_50pct_gain",
        "probability_of_doubling",
        "p10_price",
        "median_price",
        "p90_price",
        "INCOMPLETE_HORIZON_COVERAGE",
        "MISSING_EXPLICIT_METHOD_ID",
        "MONTE_CARLO_SIMULATION_COUNT_MISMATCH",
    ]:
        assert token in text
