from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts import audit_collector_v1_historical_feature_availability as audit

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_historical_feature_availability"


def test_historical_feature_availability_audit() -> None:
    assert audit.main([]) == 0
    summary = json.loads((OUT / "collector_v1_historical_feature_availability_audit_summary.json").read_text(encoding="utf-8"))
    ledger = pd.read_csv(OUT / "collector_v1_historical_feature_availability_ledger.csv", dtype=str).fillna("")

    assert summary["status"] == "PASS_COLLECTOR_V1_HISTORICAL_FEATURE_AVAILABILITY_AUDIT"
    assert summary["feature_availability_audit_certified"] is True
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False
    assert summary["critical_failures"] == []
    assert len(ledger) > 0
    assert {
        "feature_name", "feature_family", "source_path", "source_sha256",
        "date_field", "identity_field", "availability_state", "replay_eligible",
        "exclusion_reason", "provenance_notes",
    }.issubset(ledger.columns)
    assert not ledger["availability_state"].eq("CURRENT_ONLY").where(ledger["replay_eligible"].str.lower().eq("true"), False).any()


def test_unknown_dates_are_not_replay_eligible() -> None:
    assert audit.main([]) == 0
    ledger = pd.read_csv(OUT / "collector_v1_historical_feature_availability_ledger.csv", dtype=str).fillna("")
    unknown = ledger[ledger["availability_state"].isin(["DATE_UNVERIFIED", "UNAVAILABLE", "CURRENT_ONLY"])]
    assert unknown["replay_eligible"].str.lower().eq("false").all()
