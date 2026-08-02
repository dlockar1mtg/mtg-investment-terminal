from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "recover_collector_v1_historical_price_authority.py"
CONTRACT = ROOT / "config" / "mtg" / "standards" / "collector_historical_price_recovery_contract_v1.json"
OUTPUT = ROOT / "data" / "governance" / "permanence" / "certification" / "collector_v1_historical_price_recovery"
SUMMARY = OUTPUT / "collector_historical_price_recovery_summary.json"
LEDGER = OUTPUT / "collector_historical_price_replay_ledger_candidate.csv"
COVERAGE = OUTPUT / "collector_historical_checkpoint_coverage.csv"
INVENTORY = OUTPUT / "collector_historical_price_recovery_source_inventory.csv"
EXCLUSIONS = OUTPUT / "collector_historical_price_recovery_exclusions.csv"


def run_recovery() -> None:
    completed = subprocess.run([sys.executable, str(SCRIPT), "--strict"], cwd=ROOT, check=False)
    assert completed.returncode == 0


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


def test_recovery_outputs_and_authorization_boundaries() -> None:
    run_recovery()
    for path in (SUMMARY, LEDGER, COVERAGE, INVENTORY, EXCLUSIONS):
        assert path.exists()
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS_COLLECTOR_V1_HISTORICAL_PRICE_RECOVERY_AND_COVERAGE"
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False
    assert summary["required_checkpoints_days"] == [0, 30, 60, 90, 120, 180, 270, 365]
    if summary["lifecycle_panel_build_authorized"]:
        assert summary["raw_historical_price_authority_certified"] is True
        assert summary["products_with_all_required_exact_checkpoints"] > 0


def test_replay_ledger_has_no_prohibited_paths_or_missing_lineage() -> None:
    run_recovery()
    prohibited = ("secret_lair", "pre_collector", "ebay", "staging", "validation", "backup", "attempt", "repair", "current", "latest", "snapshot", "forecast", "recommendation", "portfolio", "model_input")
    with LEDGER.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        lower = row["source_path"].replace("\\", "/").lower()
        assert not any(term in lower for term in prohibited)
        assert len(row["source_sha256"]) == 64
        assert row["canonical_product_id"]
        assert row["observation_date"]
        assert float(row["market_price"]) > 0
        assert row["provider"]


def test_coverage_reports_every_required_checkpoint() -> None:
    run_recovery()
    with COVERAGE.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    for day in (0, 30, 60, 90, 120, 180, 270, 365):
        assert f"checkpoint_{day}d_exact_supported" in rows[0]
