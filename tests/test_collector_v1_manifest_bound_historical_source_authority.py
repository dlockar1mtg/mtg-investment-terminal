from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import scripts.certify_collector_v1_manifest_bound_historical_source_authority as authority


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def configure(monkeypatch, tmp_path: Path, frozen_rows, snapshot_files):
    source_manifest = tmp_path / "snapshot.json"
    source_manifest.write_text(json.dumps({
        "snapshot_id": authority.SNAPSHOT_ID,
        "operating_date": authority.OPERATING_DATE,
        "operating_timezone": authority.TIMEZONE,
        "source_bundle_sha256": authority.BUNDLE_SHA,
        "purchase_recommendations_authorized": False,
        "files": snapshot_files,
    }), encoding="utf-8")
    frozen = tmp_path / "frozen.csv"
    write_csv(frozen, frozen_rows)
    out = tmp_path / "out"
    monkeypatch.setattr(authority, "ROOT", tmp_path)
    monkeypatch.setattr(authority, "SNAPSHOT_MANIFEST", source_manifest)
    monkeypatch.setattr(authority, "FROZEN_MANIFEST", frozen)
    monkeypatch.setattr(authority, "OUT", out)
    monkeypatch.setattr(authority, "run_required", lambda _script: (True, 0))
    return out


def test_unregistered_july_source_is_excluded(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "data" / "ebay_2026-07-28.csv"
    write_csv(source, [{"price": "100"}])
    out = configure(monkeypatch, tmp_path, [{
        "source_file": "data/ebay_2026-07-28.csv",
        "source_role": "CORROBORATING_LISTING_ONLY",
    }], [])
    assert authority.main() == 6
    summary = json.loads((out / "collector_manifest_bound_historical_source_authority_summary.json").read_text())
    exclusions = list(csv.DictReader((out / "collector_manifest_bound_historical_source_exclusions.csv").open()))
    assert summary["status"] == "BLOCKED_NO_CERTIFIED_AUGUST1_HISTORICAL_PRICE_SOURCE"
    assert summary["admitted_source_count"] == 0
    assert exclusions[0]["adjudication_reasons"] == "NOT_REGISTERED_IN_CERTIFIED_AUGUST1_MANIFEST"


def test_registered_august1_source_requires_exact_hash(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "data" / "history.csv"
    write_csv(source, [{"market_price": "100"}])
    rel = "data/history.csv"
    out = configure(monkeypatch, tmp_path, [{
        "source_file": rel,
        "source_role": "AUTHORITATIVE_PRICE_CANDIDATE",
    }], [{
        "role": "historical_price_source",
        "path": rel,
        "sha256": digest(source),
        "operating_date": "2026-08-01",
    }])
    assert authority.main() == 0
    summary = json.loads((out / "collector_manifest_bound_historical_source_authority_summary.json").read_text())
    assert summary["status"] == "PASS_COLLECTOR_MANIFEST_BOUND_HISTORICAL_SOURCE_AUTHORITY"
    assert summary["admitted_source_count"] == 1
    assert summary["historical_observation_ledger_build_authorized"] is False


def test_registered_non_august1_source_is_blocked(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "data" / "history.csv"
    write_csv(source, [{"market_price": "100"}])
    rel = "data/history.csv"
    out = configure(monkeypatch, tmp_path, [{
        "source_file": rel,
        "source_role": "AUTHORITATIVE_PRICE_CANDIDATE",
    }], [{
        "role": "historical_price_source",
        "path": rel,
        "sha256": digest(source),
        "operating_date": "2026-07-28",
    }])
    assert authority.main() == 6
    exclusions = list(csv.DictReader((out / "collector_manifest_bound_historical_source_exclusions.csv").open()))
    assert "SOURCE_OPERATING_DATE_NOT_CERTIFIED_2026_08_01" in exclusions[0]["adjudication_reasons"]


def test_downstream_authorizations_always_false() -> None:
    text = Path(authority.__file__).read_text(encoding="utf-8")
    for key in (
        "raw_historical_price_authority_certified",
        "historical_observation_ledger_build_authorized",
        "historical_coverage_assessment_authorized",
        "lifecycle_panel_build_authorized",
        "model_tournament_authorized",
        "production_forecasting_authorized",
        "uip_delivery_authorized",
        "purchase_recommendations_authorized",
    ):
        assert f'"{key}": False' in text
