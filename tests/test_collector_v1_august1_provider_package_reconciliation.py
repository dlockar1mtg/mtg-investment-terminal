from __future__ import annotations

import json
from pathlib import Path

import scripts.reconcile_collector_v1_august1_provider_package as reconcile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_provider_package_reconciliation_contract_v1.json"
SCRIPT = ROOT / "scripts/reconcile_collector_v1_august1_provider_package.py"


def test_contract_preserves_governance_boundaries() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["governing_snapshot"]["snapshot_id"] == reconcile.SNAPSHOT_ID
    assert contract["governing_snapshot"]["operating_date"] == "2026-08-01"
    assert contract["governing_snapshot"]["certified_product_count"] == 50
    controls = contract["required_controls"]
    assert controls["snapshot_manifest_is_only_discovery_authority"] is True
    assert controls["historical_rows_inside_august_1_artifact_allowed"] is True
    assert controls["older_uncertified_artifact_prohibited"] is True
    assert controls["broad_repository_scan_prohibited"] is True
    authorization = contract["authorization"]
    assert authorization["provider_package_reconciliation_authorized"] is True
    assert authorization["historical_source_reconstruction_authorized"] is False
    assert authorization["historical_observation_ledger_build_authorized"] is False
    assert authorization["model_tournament_authorized"] is False
    assert authorization["purchase_recommendations_authorized"] is False


def test_script_uses_snapshot_manifest_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'rglob(' not in text
    assert 'glob(' not in text
    assert "FROZEN_MANIFEST" not in text
    assert reconcile.SNAPSHOT_ID in text
    assert reconcile.BUNDLE_SHA in text
    assert '"snapshot_manifest_only_discovery": True' in text
    assert '"historical_source_reconstruction_authorized": False' in text
    assert '"historical_observation_ledger_build_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text


def test_provider_domain_classification() -> None:
    assert reconcile.provider_domain("data/tcgcsv/history.csv", "prices") == "TCGPLAYER_TCGCSV"
    assert reconcile.provider_domain("data/wizards/releases.csv", "release_metadata") == "WIZARDS"
    assert reconcile.provider_domain("data/ebay/listings.csv", "supply") == "EBAY"
    assert reconcile.provider_domain("data/features.csv", "feature_matrix") == "COLLECTOR_FOUNDATION"


def test_august1_artifact_can_contain_older_historical_rows(tmp_path: Path) -> None:
    source = tmp_path / "history.csv"
    source.write_text(
        "canonical_product_id,observation_date,market_price\n"
        "a,2024-01-01,100\n"
        "a,2026-08-01,200\n",
        encoding="utf-8",
    )
    result = reconcile.inspect_csv(source)
    assert result["contains_multi_date_history"] is True
    assert result["minimum_embedded_date"] == "2024-01-01"
    assert result["maximum_embedded_date"] == "2026-08-01"


def test_single_date_artifact_is_not_historical_series(tmp_path: Path) -> None:
    source = tmp_path / "current.csv"
    source.write_text(
        "tcgplayer_product_id,source_timestamp,market_price\n"
        "1,2026-08-01T12:00:00+00:00,100\n"
        "2,2026-08-01T12:00:00+00:00,200\n",
        encoding="utf-8",
    )
    result = reconcile.inspect_csv(source)
    assert result["contains_multi_date_history"] is False
    assert result["distinct_date_count"] == 1
