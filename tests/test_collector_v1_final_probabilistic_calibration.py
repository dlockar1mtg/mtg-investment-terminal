from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_final_probabilistic_calibration_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_final_probabilistic_calibration.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_contract_requires_exact_final_universe() -> None:
    contract = load_contract()
    assert contract["required_forecast_products"] == 49
    assert contract["required_forecast_rows"] == 294
    assert contract["required_lineage_rows"] == 294
    assert contract["required_horizons_days"] == [90, 180, 365, 730, 1095, 1825]


def test_contract_authorities_exist() -> None:
    for relative in load_contract()["authorities"].values():
        assert (ROOT / relative).is_file(), relative


def test_contract_preserves_forecasts_and_blocks_decisions() -> None:
    rules = load_contract()["rules"]
    assert rules["forecast_values_must_not_be_modified"] is True
    assert rules["identity_and_current_price_must_reconcile"] is True
    assert rules["quantiles_must_be_ordered"] is True
    assert rules["probabilities_must_be_bounded"] is True
    assert rules["prices_must_be_positive_and_finite"] is True
    assert rules["lineage_must_be_closed"] is True
    assert rules["duplicate_product_horizon_keys_prohibited"] is True
    assert rules["insufficient_realized_validation_must_be_explicit"] is True
    assert rules["reasonableness_flags_do_not_silently_change_forecasts"] is True
    assert rules["ranking_authorized"] is False
    assert rules["purchase_recommendations_authorized"] is False


def test_contract_has_all_required_statuses() -> None:
    assert set(load_contract()["allowed_row_statuses"]) == {
        "CALIBRATED",
        "CALIBRATED_WITH_LIMITATIONS",
        "REASONABLENESS_REVIEW_REQUIRED",
        "INSUFFICIENT_REALIZED_VALIDATION",
        "BLOCKED",
    }


def test_script_has_required_structural_checks_and_outputs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "QUANTILE_ORDER_INVALID",
        "INVALID_PROBABILITY",
        "CURRENT_PRICE_AUTHORITY_MISMATCH",
        "DUPLICATE_PRODUCT_HORIZON_KEYS",
        "LINEAGE_NOT_CLOSED",
        "collector_final_forecast_row_validation.csv",
        "collector_probability_calibration_by_horizon.csv",
        "collector_probability_calibration_by_method.csv",
        "collector_historical_interval_coverage.csv",
        "collector_horizon_coherence_audit.csv",
        "collector_extreme_forecast_review_queue.csv",
        "collector_product_calibration_status.csv",
        "collector_lorwyn_reasonableness_review.csv",
        "collector_probabilistic_calibration_summary.json",
    ]:
        assert token in text


def test_script_uses_no_hardcoded_product_identity() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any(value.startswith("MTG-CANON-TCGPLAYER-") for value in strings)


def test_weights_or_forecasts_are_not_rewritten() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"forecast_values_modified": False' in text
    assert "write_csv(paths[\"final_forecasts\"]" not in text
    assert "write_text(paths[\"final_forecasts\"]" not in text
