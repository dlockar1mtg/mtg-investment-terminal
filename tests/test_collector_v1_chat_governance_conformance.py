from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit_collector_v1_chat_governance_conformance.py"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_chat_governance_conformance"
SUMMARY = OUT / "collector_chat_governance_conformance_summary.json"
RECOVERY = ROOT / "scripts/recover_collector_v1_historical_price_authority.py"


def test_invalid_recovery_is_revoked_and_fail_closed() -> None:
    result = subprocess.run([sys.executable, str(RECOVERY), "--strict"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    summary = json.loads((ROOT / "data/governance/permanence/certification/collector_v1_historical_price_recovery/collector_historical_price_recovery_summary.json").read_text(encoding="utf-8"))
    assert summary["previous_result_revoked"] is True
    assert summary["governing_snapshot_id"] == "collector-20260801T211201Z-7688afbd"
    assert summary["governing_operating_date"] == "2026-08-01"
    assert summary["governing_certified_product_count"] == 50
    assert summary["raw_historical_price_authority_certified"] is False
    assert summary["historical_coverage_assessment_completed"] is False
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False


def test_governance_audit_produces_fail_closed_certification() -> None:
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["governing_snapshot_id"] == "collector-20260801T211201Z-7688afbd"
    assert summary["governing_operating_date"] == "2026-08-01"
    assert summary["governing_product_count"] == 50
    assert summary["historical_price_authority_certified"] is False
    assert summary["historical_coverage_assessment_completed"] is False
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False
