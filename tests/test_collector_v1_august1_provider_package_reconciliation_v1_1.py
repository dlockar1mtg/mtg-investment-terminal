from __future__ import annotations

import json
from pathlib import Path

import scripts.reconcile_collector_v1_august1_provider_package_v1_1 as reconcile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_provider_package_reconciliation_contract_v1_1.json"
SCRIPT = ROOT / "scripts/reconcile_collector_v1_august1_provider_package_v1_1.py"


def test_contract_models_wizards_as_embedded_provenance() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["governing_snapshot"]["operating_date"] == "2026-08-01"
    assert contract["governing_snapshot"]["certified_product_count"] == 50
    assert contract["provider_models"]["WIZARDS"] == "WEB_RESEARCH_PROVENANCE_EMBEDDED_IN_CERTIFIED_FOUNDATION"
    controls = contract["required_controls"]
    assert controls["wizards_file_required"] is False
    assert controls["wizards_release_date_provenance_required"] is True
    assert controls["wizards_release_dates_must_be_embedded_in_hash_verified_august1_foundation"] is True
    assert controls["release_date_coverage_must_equal_certified_product_count"] is True
    authorization = contract["authorization"]
    assert authorization["historical_source_reconstruction_authorized"] is False
    assert authorization["historical_observation_ledger_build_authorized"] is False
    assert authorization["model_tournament_authorized"] is False
    assert authorization["purchase_recommendations_authorized"] is False


def test_script_does_not_require_wizards_file_or_scan_broadly() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'rglob(' not in text
    assert 'glob(' not in text
    assert "FROZEN_MANIFEST" not in text
    assert '"wizards_file_required": False' in text
    assert "WIZARDS_COMPONENT_MISSING" not in text
    assert "WIZARDS_RELEASE_DATE_AUTHORITY_NOT_EMBEDDED_FOR_50_PRODUCTS" in text
    assert '"historical_source_reconstruction_authorized": False' in text
    assert '"historical_observation_ledger_build_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text


def test_wizards_is_not_a_file_provider_domain() -> None:
    assert reconcile.provider_domain("data/tcgcsv/products.csv", "prices") == "TCGPLAYER_TCGCSV"
    assert reconcile.provider_domain("data/ebay/listings.csv", "supply") == "EBAY"
    assert reconcile.provider_domain("data/features.csv", "feature_matrix") == "COLLECTOR_FOUNDATION"
    assert reconcile.provider_domain("data/wizards/releases.csv", "release_metadata") == "COLLECTOR_FOUNDATION"


def test_release_date_coverage_is_detected_in_certified_foundation_csv(tmp_path: Path) -> None:
    source = tmp_path / "feature_matrix.csv"
    source.write_text(
        "canonical_product_id,release_date,current_price\n"
        "a,2024-01-01,100\n"
        "b,2025-02-01,200\n",
        encoding="utf-8",
    )
    result = reconcile.inspect_csv(source)
    assert result["release_date_field"] == "release_date"
    assert result["release_date_nonblank_row_count"] == 2
    assert result["release_date_distinct_product_count"] == 2
    assert result["contains_multi_date_history"] is False


def test_embedded_release_dates_are_reference_provenance_not_price_history(tmp_path: Path) -> None:
    source = tmp_path / "foundation.csv"
    source.write_text(
        "canonical_product_id,release_date,market_price\n"
        "a,2024-01-01,100\n"
        "b,2025-02-01,200\n",
        encoding="utf-8",
    )
    result = reconcile.inspect_csv(source)
    assert result["release_date_distinct_product_count"] == 2
    assert result["distinct_date_count"] == 0
    assert result["contains_multi_date_history"] is False
