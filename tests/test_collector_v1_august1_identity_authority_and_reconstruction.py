from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_identity_authority_and_reconstruction_contract_v1.json"
SCRIPT = ROOT / "scripts/build_collector_v1_august1_identity_authority_and_reconstruction.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_exists_and_is_parseable() -> None:
    payload = load_contract()
    assert payload["contract_name"] == "Collector August 1 Identity Authority and Reconstruction"
    assert payload["governing_snapshot"]["certified_product_count"] == 50


def test_identity_authority_is_exactly_bounded() -> None:
    payload = load_contract()
    authority = payload["identity_authority"]
    assert authority["required_rows"] == 50
    assert authority["required_unique_primary_identities"] == 50
    assert authority["required_unique_tcgplayer_ids"] == 50
    assert authority["primary_identity_field"] == "identity__canonical_product_id"
    assert len(authority["sha256"]) == 64


def test_archive_source_and_exception_are_governed() -> None:
    payload = load_contract()
    source = payload["certified_archive_source"]
    exception = payload["governed_exception"]
    assert source["required_archive_backed_products"] == 49
    assert source["required_no_history_products"] == 1
    assert exception["tcgplayer_product_id"] == "706142"
    assert exception["release_date"] == "2026-11-13"
    assert exception["release_state"] == "PRESALE"
    assert exception["direct_history_modeling_allowed"] is False


def test_downstream_authorizations_remain_false() -> None:
    authorization = load_contract()["authorization"]
    assert authorization["identity_authority_certification_authorized"] is True
    assert authorization["governed_reconstruction_execution_authorized"] is True
    blocked = [
        "historical_observation_ledger_build_authorized",
        "historical_coverage_assessment_authorized",
        "lifecycle_panel_build_authorized",
        "model_tournament_authorized",
        "production_forecasting_authorized",
        "uip_delivery_authorized",
        "purchase_recommendations_authorized",
    ]
    assert all(authorization[key] is False for key in blocked)


def test_script_contains_required_fail_closed_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    required = [
        "PASS_COLLECTOR_AUGUST1_IDENTITY_AUTHORITY_AND_RECONSTRUCTION",
        "LEGITIMATE_POST_ARCHIVE_RELEASE_NO_HISTORY",
        "CERTIFIED_TCGCSV_ARCHIVE_HISTORY",
        "ARCHIVE_BACKED_PRODUCT_COUNT_MISMATCH",
        "NO_HISTORY_PRODUCT_COUNT_MISMATCH",
        "DUPLICATE_RECONSTRUCTED_PRODUCT_DATE_KEYS",
        '"historical_observation_ledger_build_authorized": False',
        '"purchase_recommendations_authorized": False',
    ]
    assert all(token in text for token in required)


def test_current_prices_are_not_written_as_history() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "identity__market_price" not in text
    assert "price__fresh_market_price" not in text
    assert '"source_name": "TCGCSV_ARCHIVE_CERTIFIED"' in text
