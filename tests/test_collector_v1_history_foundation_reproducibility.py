from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_collector_v1_history_foundation_reproducibility import main

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_history_foundation_reproducibility"


def test_reproducibility_audit_runs(monkeypatch):
    monkeypatch.setattr("sys.argv", ["audit_collector_v1_history_foundation_reproducibility.py", "--strict"])
    assert main() == 0


def test_reproducibility_summary_is_fail_closed():
    summary = json.loads((OUT / "collector_history_foundation_reproducibility_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "PASS_COLLECTOR_V1_HISTORY_FOUNDATION_REPRODUCIBILITY_AUDIT"
    assert summary["target_not_mutated"] is True
    assert summary["raw_historical_price_authority_certified"] is False
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False


def test_reproducibility_outputs_exist():
    assert (OUT / "collector_history_foundation_contributing_source_inventory.csv").is_file()
    assert (OUT / "collector_history_foundation_reconciliation_mismatches.csv").is_file()
