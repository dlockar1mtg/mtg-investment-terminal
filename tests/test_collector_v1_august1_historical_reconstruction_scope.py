from __future__ import annotations

import json
from pathlib import Path

import scripts.certify_collector_v1_august1_historical_reconstruction_scope as scope

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_historical_reconstruction_scope_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_august1_historical_reconstruction_scope.py"


def test_contract_preserves_boundaries() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["governing_snapshot"]["snapshot_id"] == scope.SNAPSHOT_ID
    assert contract["governing_snapshot"]["operating_date"] == "2026-08-01"
    assert contract["governing_snapshot"]["certified_product_count"] == 50
    controls = contract["required_controls"]
    assert controls["certified_august1_identity_universe_only"] is True
    assert controls["older_output_artifact_as_input_prohibited"] is True
    assert controls["broad_repository_scan_prohibited"] is True
    assert controls["current_snapshot_as_history_prohibited"] is True
    assert controls["ebay_listing_price_cannot_become_authoritative_market_price"] is True
    authorization = contract["authorization"]
    assert authorization["historical_source_reconstruction_authorized"] is False
    assert authorization["historical_observation_ledger_build_authorized"] is False
    assert authorization["model_tournament_authorized"] is False
    assert authorization["purchase_recommendations_authorized"] is False


def test_script_is_fail_closed_and_bounded() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "rglob(" not in text
    assert "glob(" not in text
    assert "FROZEN_MANIFEST" not in text
    assert scope.SNAPSHOT_ID in text
    assert scope.BUNDLE_SHA in text
    assert '"older_output_artifact_use_authorized": False' in text
    assert '"historical_observation_ledger_build_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text


def test_scope_keeps_provider_semantics_separate() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "AUTHORITATIVE_MARKET_PRICE_CANDIDATE" in text
    assert "TCGPLAYER_MARKET_PRICE" in text
    assert "CORROBORATING_LISTING_SUPPLY_ONLY" in text
    assert "LISTING_PRICE_AND_SUPPLY_NOT_MARKET_PRICE" in text
    assert "Wizards" not in text or "wizards_reconstruction_required" in text
