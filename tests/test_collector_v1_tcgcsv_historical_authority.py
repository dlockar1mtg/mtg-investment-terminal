from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_collector_v1_tcgcsv_historical_authority.py"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_tcgcsv_historical_authority"
SUMMARY = OUT / "collector_tcgcsv_historical_authority_summary.json"
ROWS = OUT / "collector_tcgcsv_candidate_row_audit.csv"


def run_verification() -> dict:
    result = subprocess.run([sys.executable, str(SCRIPT), "--strict"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def test_tcgcsv_candidate_semantics_are_measured_without_premature_authority() -> None:
    summary = run_verification()
    assert summary["status"] == "PASS_COLLECTOR_V1_TCGCSV_HISTORICAL_AUTHORITY_VERIFICATION"
    assert summary["candidate_hash_verified"] is True
    assert summary["candidate_row_count"] > 0
    assert summary["tcgcsv_provider_semantics_certified"] in {True, False}
    assert summary["raw_historical_price_authority_certified"] is False
    assert summary["historical_coverage_assessment_authorized"] is False
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False


def test_single_day_candidate_cannot_support_first_year_replay() -> None:
    summary = run_verification()
    if summary["distinct_observation_date_count"] <= 1:
        assert summary["coverage_90d_supported"] is False
        assert summary["coverage_180d_supported"] is False
        assert summary["coverage_365d_supported"] is False
        assert summary["first_year_replay_supported"] is False


def test_candidate_rows_remain_blocked_from_replay() -> None:
    run_verification()
    frame = pd.read_csv(ROWS, dtype=str).fillna("")
    assert not frame.empty
    assert set(frame["historical_replay_eligible"].str.lower()) == {"false"}
    assert frame["historical_replay_exclusion_reason"].str.len().gt(0).all()
