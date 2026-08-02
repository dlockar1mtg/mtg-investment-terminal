from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_row_level_reconstruction_certification_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_august1_row_level_reconstruction.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_is_parseable_and_snapshot_bound() -> None:
    payload = load_contract()
    assert payload["contract_name"] == "Collector August 1 Row-Level Reconstruction Certification"
    assert payload["governing_snapshot_id"] == "collector-20260801T211201Z-7688afbd"
    assert payload["expected"]["reconstructed_rows"] == 1215
    assert payload["expected"]["archive_backed_products"] == 49
    assert payload["expected"]["governed_no_history_products"] == 1


def test_contract_keeps_downstream_authorizations_closed() -> None:
    authorization = load_contract()["authorization"]
    assert authorization["row_level_reconstruction_certification_authorized"] is True
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
        "PASS_COLLECTOR_AUGUST1_ROW_LEVEL_RECONSTRUCTION_CERTIFICATION",
        "RECONSTRUCTION_PREREQUISITE_NOT_PASS",
        "DUPLICATE_CANDIDATE_KEYS",
        "DUPLICATE_SOURCE_KEYS",
        "SOURCE_ROWS_MISSING_FROM_CANDIDATE",
        "CANDIDATE_ROWS_NOT_IN_SOURCE",
        "ROW_FINGERPRINT_MISMATCH",
        "CANDIDATE_SOURCE_HASH_MISMATCH",
        '"purchase_recommendations_authorized": False',
    ]
    assert all(token in text for token in required)


def test_certifier_compares_source_semantics_and_does_not_use_current_prices() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "semantic_fields" in text
    assert '"selected_price"' in text
    assert '"selection_method"' in text
    assert '"price_data_quality"' in text
    assert "identity__market_price" not in text
    assert "price__fresh_market_price" not in text
