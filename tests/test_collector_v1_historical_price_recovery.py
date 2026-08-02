from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "recover_collector_v1_historical_price_authority.py"
CONTRACT = ROOT / "config" / "mtg" / "standards" / "collector_historical_price_recovery_contract_v1.json"
OUTPUT = ROOT / "data" / "governance" / "permanence" / "certification" / "collector_v1_historical_price_recovery"
SUMMARY = OUTPUT / "collector_historical_price_recovery_summary.json"


def run_revoked_recovery() -> dict:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--strict"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert SUMMARY.exists()
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def test_contract_preserves_governance_boundaries() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    controls = contract["required_controls"]
    assert controls["collector_only"] is True
    assert controls["point_in_time_only"] is True
    assert controls["current_snapshot_backfill_prohibited"] is True
    assert controls["secret_lair_prohibited"] is True
    assert controls["pre_collector_prohibited"] is True
    assert controls["ebay_listing_price_as_authority_prohibited"] is True
    assert controls["derived_value_as_observation_prohibited"] is True
    assert controls["open_ended_repository_scan_prohibited"] is True
    assert contract["required_checkpoints_days"] == [0, 30, 60, 90, 120, 180, 270, 365]


def test_revoked_recovery_cannot_certify_or_authorize() -> None:
    summary = run_revoked_recovery()
    assert summary["previous_result_revoked"] is True
    assert summary["status"] == "BLOCKED_PENDING_AUGUST_1_SNAPSHOT_CONFORMANCE"
    assert summary["governing_snapshot_id"] == "collector-20260801T211201Z-7688afbd"
    assert summary["governing_operating_date"] == "2026-08-01"
    assert summary["governing_timezone"] == "America/Chicago"
    assert summary["governing_source_bundle_sha256"] == "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
    assert summary["governing_certified_product_count"] == 50
    assert summary["raw_historical_price_authority_certified"] is False
    assert summary["historical_coverage_assessment_completed"] is False
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False


def test_revoked_recovery_is_deterministic() -> None:
    first = run_revoked_recovery()
    second = run_revoked_recovery()
    assert first == second
