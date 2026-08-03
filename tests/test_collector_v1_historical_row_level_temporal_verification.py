from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts import verify_collector_v1_historical_rows as verify

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_historical_row_level_temporal_verification"


def test_historical_row_level_temporal_verification() -> None:
    assert verify.main([]) == 0
    summary = json.loads((OUT / "collector_v1_historical_row_level_temporal_verification_summary.json").read_text(encoding="utf-8"))
    rows = pd.read_csv(OUT / "collector_v1_historical_row_level_temporal_verification.csv", dtype=str).fillna("")

    assert summary["status"] == "PASS_COLLECTOR_V1_HISTORICAL_ROW_LEVEL_TEMPORAL_VERIFICATION"
    assert summary["candidate_source_count"] > 0
    assert summary["verified_source_count"] == summary["candidate_source_count"]
    assert summary["row_level_temporal_verification_certified"] is True
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False
    assert summary["critical_failures"] == []

    required = {
        "source_path", "source_sha256", "feature_family", "semantic_role",
        "row_count", "valid_date_row_count", "invalid_date_row_count",
        "minimum_observation_date", "maximum_observation_date",
        "distinct_product_count", "blank_identity_row_count",
        "duplicate_identity_date_row_count", "future_dated_row_count",
        "checkpoint_coverage_count", "row_level_replay_eligible", "exclusion_reason",
    }
    assert required.issubset(rows.columns)
    assert not rows[rows["semantic_role"].eq("DERIVED_OR_OPERATIONAL_OUTPUT")]["row_level_replay_eligible"].str.lower().eq("true").any()


def test_row_level_contract_remains_fail_closed() -> None:
    contract = json.loads((ROOT / "config/mtg/standards/collector_historical_row_level_temporal_verification_contract_v1.json").read_text(encoding="utf-8"))
    controls = contract["controls"]
    authorization = contract["authorization"]
    assert controls["future_information_prohibited"] is True
    assert controls["invalid_dates_not_replay_eligible"] is True
    assert controls["derived_or_operational_outputs_prohibited"] is True
    assert controls["current_only_sources_prohibited"] is True
    assert controls["row_level_temporal_verification_required"] is True
    assert authorization["row_level_verification_authorized"] is True
    assert authorization["lifecycle_panel_build_authorized"] is False
    assert authorization["model_tournament_authorized"] is False
    assert authorization["purchase_recommendations_authorized"] is False
