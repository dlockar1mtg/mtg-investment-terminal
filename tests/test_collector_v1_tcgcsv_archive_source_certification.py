from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_tcgcsv_archive_source_certification_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_tcgcsv_archive_source.py"


def test_contract_exists_and_is_parseable() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["contract_name"] == "Collector TCGCSV Archive Source Certification"
    assert payload["governing_snapshot"]["certified_product_count"] == 50
    assert payload["candidate_source"]["expected_rows"] == 21837
    assert payload["candidate_source"]["expected_distinct_dates"] == 30
    assert payload["candidate_source"]["expected_distinct_identities"] == 989


def test_contract_binds_exact_candidate_hash() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    candidate = payload["candidate_source"]
    assert candidate["path"].endswith("universal_tcgcsv_monthly_archive_observations.csv")
    assert candidate["expected_sha256"] == "479bb921ddd020a02606b407d660f9017cdc45d187b55dc9c0d933383a063819"
    assert candidate["expected_first_date"] == "2024-02-08"
    assert candidate["expected_last_date"] == "2026-07-01"


def test_contract_is_read_only_and_source_specific() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    controls = payload["required_controls"]
    assert controls["read_only"] is True
    assert controls["broad_repository_scan_prohibited"] is True
    assert controls["legacy_helper_execution_prohibited"] is True
    assert controls["network_collection_prohibited"] is True
    assert controls["source_provided_observation_dates_required"] is True
    assert controls["tcgplayer_product_id_required"] is True
    assert controls["positive_selected_price_required"] is True
    assert controls["duplicate_product_date_keys_prohibited"] is True
    assert controls["ledger_subset_reconciliation_required"] is True


def test_downstream_authorizations_remain_false() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    authorization = payload["authorization"]
    assert authorization["raw_tcgcsv_archive_source_certification_authorized"] is True
    assert authorization["governed_historical_reconstruction_authorized_on_pass"] is True
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


def test_script_contains_fail_closed_certification_boundaries() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "PASS_COLLECTOR_TCGCSV_ARCHIVE_SOURCE_CERTIFICATION" in text
    assert '"raw_tcgcsv_archive_source_certified": not failures' in text
    assert '"governed_historical_reconstruction_authorized": not failures' in text
    assert '"historical_observation_ledger_build_authorized": False' in text
    assert '"model_tournament_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text


def test_script_checks_dates_prices_identity_and_reconciliation() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "DUPLICATE_PRODUCT_DATE_KEYS" in text
    assert "MARKET_PRICE_PREFERENCE_VIOLATIONS" in text
    assert "LEDGER_SUBSET_RECONCILIATION_MISMATCH" in text
    assert "SOURCE_SHA256_MISMATCH" in text
    assert "tcgplayer_product_id" in text
    assert "selected_price" in text
