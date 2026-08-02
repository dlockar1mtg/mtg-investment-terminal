from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_collector_v1_frozen_history_source_manifest.py"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_frozen_history_source_manifest"
SUMMARY = OUT / "collector_frozen_history_source_manifest_summary.json"
MANIFEST = OUT / "collector_frozen_history_source_manifest.csv"
ADJUDICATION = OUT / "collector_history_source_adjudication.csv"


def run_builder() -> None:
    completed = subprocess.run([sys.executable, str(SCRIPT), "--strict"], cwd=ROOT, check=False)
    assert completed.returncode == 0


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_frozen_manifest_builds_and_remains_fail_closed() -> None:
    run_builder()
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS_COLLECTOR_V1_FROZEN_HISTORY_SOURCE_MANIFEST"
    assert summary["frozen_manifest_build_certified"] is True
    assert summary["open_ended_repository_scan_authorized_for_replay"] is False
    assert summary["raw_historical_price_authority_certified"] is False
    assert summary["historical_coverage_assessment_authorized"] is False
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False
    assert summary["critical_failures"] == []


def test_manifest_excludes_wrong_product_classes_and_copies() -> None:
    run_builder()
    manifest = rows(MANIFEST)
    assert manifest
    for row in manifest:
        path = row["source_file"].lower()
        assert "secret_lair" not in path
        assert "pre_collector" not in path
        assert "backup" not in path
        assert "attempt" not in path
        assert "repair_input" not in path
        assert "reclassified" not in path
        assert row["source_sha256"]
        assert len(row["source_sha256"]) == 64


def test_ebay_never_receives_authoritative_price_role() -> None:
    run_builder()
    for row in rows(ADJUDICATION):
        if "ebay" in row["source_file"].lower():
            assert row["source_role"] != "AUTHORITATIVE_PRICE_CANDIDATE"


def test_derived_and_operational_outputs_are_not_manifest_candidates() -> None:
    run_builder()
    for row in rows(ADJUDICATION):
        path = row["source_file"].lower()
        if any(term in path for term in ("recommendation", "forecast", "ranking", "full_model", "portfolio", "owned_inventory", "manual_review", "product_coverage")):
            assert row["frozen_manifest_candidate"] == "False"


def test_every_adjudicated_source_has_explicit_role_and_reason() -> None:
    run_builder()
    adjudicated = rows(ADJUDICATION)
    assert adjudicated
    for row in adjudicated:
        assert row["source_role"]
        assert row["adjudication_reason"]
        assert row["historical_authority_certified"] == "False"
