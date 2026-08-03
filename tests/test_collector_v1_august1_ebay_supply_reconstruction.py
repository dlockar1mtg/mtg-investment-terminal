from __future__ import annotations

import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_ebay_supply_reconstruction_contract_v1.json"
SCRIPT = ROOT / "scripts/build_collector_v1_august1_ebay_supply_reconstruction.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_exact_snapshot_and_counts() -> None:
    c = load_contract()
    assert c["snapshot_id"] == "collector-20260801T211201Z-7688afbd"
    assert c["required_product_rows"] == 50
    assert c["required_accepted_listing_rows"] == 562


def test_supply_categories_are_exact() -> None:
    c = load_contract()
    assert c["supply_categories"] == [
        "ZERO_OBSERVED_SUPPLY",
        "ULTRA_THIN_SUPPLY",
        "THIN_SUPPLY",
        "MODERATE_SUPPLY",
        "DEEP_SUPPLY",
    ]
    assert c["category_method"] == "POSITIVE_LISTING_COUNT_QUARTILES_WITH_ZERO_SEPARATE"


def test_governance_is_fail_closed() -> None:
    g = load_contract()["governance"]
    assert g["bounded_search_only"] is True
    assert g["accepted_listings_only"] is True
    assert g["all_products_retained"] is True
    assert g["unknown_product_ids_fail_closed"] is True
    assert g["zero_listings_are_valid_supply_evidence"] is True
    assert g["seller_metrics_only_when_seller_identity_available"] is True
    assert g["historical_backtest_use_allowed"] is False
    assert g["point_forecast_rewrite_allowed"] is False
    assert g["purchase_recommendations_authorized"] is False


def test_canonical_output_path_is_production_path() -> None:
    assert load_contract()["canonical_output_path"] == (
        "data/governance/permanence/certification/"
        "collector_v1_august1_current_data_package/"
        "collector_ebay_product_supply_snapshot.csv"
    )


def test_script_contains_required_reconciliation_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "NO_562_ROW_ACCEPTED_LISTING_LEDGER_FOUND",
        "UNKNOWN_LISTING_PRODUCT_IDS",
        "AGGREGATED_LISTING_COUNT_DOES_NOT_RECONCILE",
        "ZERO_OBSERVED_SUPPLY",
        "ULTRA_THIN_SUPPLY",
        "DEEP_SUPPLY",
        "source_listing_ledger_sha256",
        "purchase_recommendation_authorized",
    ]:
        assert token in text
