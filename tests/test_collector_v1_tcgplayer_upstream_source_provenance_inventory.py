from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_tcgplayer_upstream_source_provenance_inventory_contract_v1.json"
SCRIPT = ROOT / "scripts/audit_collector_v1_tcgplayer_upstream_source_provenance_inventory.py"


def test_contract_exists_and_is_parseable() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["contract_name"] == "Collector TCGplayer Upstream Source Provenance Inventory"
    assert payload["governing_snapshot"]["certified_product_count"] == 50
    assert payload["prerequisite_status"] == "PASS_COLLECTOR_TCGPLAYER_HISTORY_LINEAGE_AND_REPRODUCIBILITY"


def test_contract_is_read_only_and_bounded() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    controls = payload["required_controls"]
    assert controls["read_only"] is True
    assert controls["broad_repository_scan_prohibited"] is True
    assert controls["source_file_references_only"] is True
    assert controls["archived_helper_execution_prohibited"] is True


def test_provider_semantics_remain_separate() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    controls = payload["required_controls"]
    assert controls["ebay_listing_price_as_market_price_prohibited"] is True
    assert controls["tcgplayer_market_price_semantics_required"] is True
    assert controls["source_provided_observation_dates_required"] is True


def test_downstream_authorizations_remain_false() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    authorization = payload["authorization"]
    blocked = [
        "raw_source_certification_authorized",
        "historical_reconstruction_execution_authorized",
        "historical_observation_ledger_build_authorized",
        "raw_historical_price_authority_certified",
        "historical_coverage_assessment_authorized",
        "lifecycle_panel_build_authorized",
        "model_tournament_authorized",
        "production_forecasting_authorized",
        "uip_delivery_authorized",
        "purchase_recommendations_authorized",
    ]
    assert all(authorization[key] is False for key in blocked)


def test_required_classifications_are_present() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    allowed = set(payload["allowed_source_classifications"])
    assert "CANDIDATE_RAW_TCGPLAYER_HISTORY_SOURCE" in allowed
    assert "DERIVED_SOURCE_NOT_AUTHORITY" in allowed
    assert "LISTING_OR_SUPPLY_SOURCE_NOT_PRICE_AUTHORITY" in allowed
    assert "REFERENCED_SOURCE_FILE_MISSING" in allowed
    assert "UNRESOLVED_SOURCE_REFERENCE" in allowed


def test_script_contains_fail_closed_boundaries() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "PASS_COLLECTOR_TCGPLAYER_UPSTREAM_SOURCE_PROVENANCE_INVENTORY" in text
    assert '"raw_source_certification_authorized": False' in text
    assert '"historical_observation_ledger_build_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text
    assert "source_groups" in text
    assert "resolve_reference" in text
    assert "sha256" in text
