from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/trace_collector_v1_history_foundation_lineage.py"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_history_foundation_lineage"
SUMMARY = OUT / "collector_history_foundation_lineage_summary.json"
CANDIDATES = OUT / "collector_history_foundation_lineage_candidates.csv"
REFERENCES = OUT / "collector_history_foundation_code_references.csv"


def run_trace() -> None:
    result = subprocess.run([sys.executable, str(SCRIPT), "--strict"], cwd=ROOT, check=False)
    assert result.returncode == 0


def test_history_foundation_lineage_trace_is_fail_closed() -> None:
    run_trace()
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS_COLLECTOR_V1_HISTORY_FOUNDATION_LINEAGE_TRACE"
    assert summary["target_path"].endswith("universal_mtg_price_history.csv")
    assert summary["raw_historical_price_authority_certified"] is False
    assert summary["historical_coverage_assessment_authorized"] is False
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False


def test_lineage_candidates_have_required_observation_fields() -> None:
    run_trace()
    candidates = pd.read_csv(CANDIDATES, dtype=str).fillna("")
    assert set([
        "candidate_path",
        "source_sha256",
        "identity_field",
        "date_field",
        "price_field",
        "raw_observation_candidate",
    ]).issubset(candidates.columns)
    if len(candidates):
        assert candidates["source_sha256"].str.len().eq(64).all()
        assert candidates["identity_field"].ne("").all()
        assert candidates["date_field"].ne("").all()
        assert candidates["price_field"].ne("").all()


def test_code_references_are_recorded_without_granting_authority() -> None:
    run_trace()
    references = pd.read_csv(REFERENCES, dtype=str).fillna("")
    assert set(["reference_path", "matched_terms", "writer_signal"]).issubset(references.columns)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["lineage_state"] != "RAW_LINEAGE_CERTIFIED"
