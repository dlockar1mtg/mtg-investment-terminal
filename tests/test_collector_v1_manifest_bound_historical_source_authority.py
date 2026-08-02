from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import scripts.certify_collector_v1_manifest_bound_historical_source_authority as authority

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_manifest_bound_historical_source_authority_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_manifest_bound_historical_source_authority.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def configure(monkeypatch, tmp_path: Path, source: Path, frozen_role: str) -> Path:
    frozen = tmp_path / "frozen.csv"
    write_csv(frozen, [{
        "source_file": str(source),
        "source_sha256": digest(source),
        "source_exists": True,
        "source_role": frozen_role,
        "frozen_manifest_candidate": True,
        "row_count": 1,
        "distinct_product_count": 1,
        "first_observation_date": "2024-01-01",
        "last_observation_date": "2024-01-01",
        "ledger_row_count": 1,
        "ledger_distinct_product_count": 1,
        "ledger_price_fields": "market_price",
        "ledger_source_names": "TCGCSV",
        "semantic_state": "RAW_CANDIDATE",
        "semantic_reasons": "",
        "adjudication_reason": "TEST",
        "historical_authority_certified": False,
    }])
    frozen_summary = tmp_path / "frozen_summary.json"
    frozen_summary.write_text(json.dumps({
        "status": "PASS_COLLECTOR_V1_FROZEN_HISTORY_SOURCE_MANIFEST",
        "manifest_sha256": digest(frozen),
    }), encoding="utf-8")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}", encoding="utf-8")
    out = tmp_path / "out"

    monkeypatch.setattr(authority, "ROOT", tmp_path)
    monkeypatch.setattr(authority, "SNAPSHOT_MANIFEST", snapshot)
    monkeypatch.setattr(authority, "FROZEN_MANIFEST", frozen)
    monkeypatch.setattr(authority, "FROZEN_SUMMARY", frozen_summary)
    monkeypatch.setattr(authority, "OUT", out)
    monkeypatch.setattr(authority, "run_required", lambda _script: (True, 0))
    monkeypatch.setattr(authority, "validate_snapshot_manifest", lambda: [])
    return out


def test_contract_preserves_authorization_boundaries() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["governing_snapshot"]["snapshot_id"] == authority.SNAPSHOT_ID
    assert contract["governing_snapshot"]["certified_product_count"] == 50
    controls = contract["required_controls"]
    assert controls["open_ended_repository_scan_prohibited"] is True
    assert controls["frozen_manifest_only"] is True
    assert controls["ebay_authoritative_price_prohibited"] is True
    assert controls["current_snapshot_as_history_prohibited"] is True
    authorization = contract["authorization"]
    assert authorization["historical_source_adjudication_authorized"] is True
    assert authorization["raw_historical_price_authority_certified"] is False
    assert authorization["historical_observation_ledger_build_authorized"] is False
    assert authorization["historical_coverage_assessment_authorized"] is False
    assert authorization["lifecycle_panel_build_authorized"] is False
    assert authorization["model_tournament_authorized"] is False
    assert authorization["purchase_recommendations_authorized"] is False


def test_script_has_no_open_ended_csv_discovery() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'rglob("*.csv")' not in text
    assert "glob(" not in text
    assert "datetime.now" not in text
    assert authority.SNAPSHOT_ID in text
    assert authority.BUNDLE_SHA in text
    assert "historical_observation_ledger_build_authorized\": False" in text
    assert "purchase_recommendations_authorized\": False" in text
    assert "source_timestamp" in text
    assert "SINGLE_TIMESTAMP_CURRENT_SNAPSHOT_NOT_HISTORY" in text


def test_manifest_bound_registry_can_pass_with_multi_date_frozen_source(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "sources" / "tcgcsv_history.csv"
    write_csv(source, [
        {"canonical_product_id": "collector-1", "observation_date": "2024-01-01", "market_price": "100.00"},
        {"canonical_product_id": "collector-1", "observation_date": "2024-02-01", "market_price": "110.00"},
    ])
    out = configure(monkeypatch, tmp_path, source, "AUTHORITATIVE_PRICE_CANDIDATE")

    assert authority.main() == 0
    summary = json.loads((out / "collector_manifest_bound_historical_source_authority_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "PASS_COLLECTOR_MANIFEST_BOUND_HISTORICAL_SOURCE_AUTHORITY"
    assert summary["source_adjudication_completed"] is True
    assert summary["authoritative_historical_price_source_available"] is True
    assert summary["authoritative_price_candidate_count"] == 1
    assert summary["raw_historical_price_authority_certified"] is False
    assert summary["historical_observation_ledger_build_authorized"] is False


def test_single_timestamp_tcgcsv_is_current_only_and_blocks_authority(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "sources" / "tcgcsv_price_observations.csv"
    write_csv(source, [
        {"tcgplayer_product_id": "1", "source_timestamp": "2026-07-28T10:32:34+00:00", "market_price": "100.00"},
        {"tcgplayer_product_id": "2", "source_timestamp": "2026-07-28T10:32:34+00:00", "market_price": "200.00"},
    ])
    out = configure(monkeypatch, tmp_path, source, "AUTHORITATIVE_PRICE_CANDIDATE")

    assert authority.main() == 6
    summary = json.loads((out / "collector_manifest_bound_historical_source_authority_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "BLOCKED_NO_AUTHORITATIVE_HISTORICAL_PRICE_SOURCE"
    assert summary["source_adjudication_completed"] is True
    assert summary["authoritative_historical_price_source_available"] is False
    assert summary["current_production_only_source_count"] == 1
    exclusions = list(csv.DictReader((out / "collector_manifest_bound_historical_source_exclusions.csv").open(encoding="utf-8")))
    assert exclusions[0]["source_role"] == "CURRENT_PRODUCTION_ONLY"
    assert exclusions[0]["observation_date_field"] == "source_timestamp"
    assert exclusions[0]["distinct_observation_timestamp_count"] == "1"
    assert "SINGLE_TIMESTAMP_CURRENT_SNAPSHOT_NOT_HISTORY" in exclusions[0]["adjudication_reasons"]
    assert summary["historical_observation_ledger_build_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False


def test_review_required_source_is_never_admitted(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "sources" / "unknown.csv"
    write_csv(source, [{
        "canonical_product_id": "collector-1",
        "observation_date": "2024-01-01",
        "market_price": "100.00",
    }])
    out = configure(monkeypatch, tmp_path, source, "REVIEW_REQUIRED")

    assert authority.main() == 6
    summary = json.loads((out / "collector_manifest_bound_historical_source_authority_summary.json").read_text(encoding="utf-8"))
    assert summary["admitted_source_count"] == 0
    assert summary["source_adjudication_completed"] is True
    assert summary["status"] == "BLOCKED_NO_AUTHORITATIVE_HISTORICAL_PRICE_SOURCE"
    assert summary["historical_observation_ledger_build_authorized"] is False
