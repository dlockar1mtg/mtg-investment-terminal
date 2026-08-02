from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts import build_collector_v1_august1_snapshot_bound_current_foundation as build
from scripts import certify_collector_v1_august1_snapshot_bound_current_foundation as certify

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_bound_current_foundation"


def test_august1_snapshot_bound_current_foundation() -> None:
    assert build.main([]) == 0
    summary = json.loads((OUT / "collector_v1_august1_snapshot_bound_current_foundation_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "PASS_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION"
    assert summary["foundation_rows"] == 50
    assert summary["accepted_listing_rows"] == 562
    assert summary["canonical_history_rows"] == 215
    assert summary["purchase_recommendations_authorized"] is False

    frame = pd.read_csv(OUT / "collector_v1_august1_snapshot_bound_current_foundation.csv", dtype=str).fillna("")
    assert len(frame) == 50
    assert frame["tcgplayer_product_id"].is_unique
    assert frame["source_snapshot_id"].eq("collector-20260801T211201Z-7688afbd").all()
    assert frame["source_observation_at_utc"].str.strip().ne("").all()
    assert frame["purchase_recommendation_authorized"].str.lower().eq("false").all()

    assert certify.main([]) == 0
    certification = json.loads((OUT / "collector_v1_august1_snapshot_bound_current_foundation_certification.json").read_text(encoding="utf-8"))
    assert certification["status"] == "PASS_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION_CERTIFIED"
    assert certification["current_foundation_certified"] is True
    assert certification["forecast_ranking_rebuild_authorized"] is True
    assert certification["purchase_recommendations_authorized"] is False
