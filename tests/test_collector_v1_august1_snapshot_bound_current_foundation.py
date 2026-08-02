from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts import build_collector_v1_august1_snapshot_bound_current_foundation as build
from scripts import certify_collector_v1_august1_snapshot_bound_current_foundation as certify

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_bound_current_foundation"
DIRECT_ROUTES = {"DIRECT_HISTORY_CALIBRATED", "DIRECT_HISTORY_LIMITED"}
COMPARABLE_ROUTES = {
    "COMPARABLE_PRODUCT_ADJUSTED",
    "EARLY_OPPORTUNITY_COHORT_FALLBACK",
    "FUNDAMENTAL_COMPARABLE_HYBRID",
}


def test_august1_snapshot_bound_current_foundation() -> None:
    assert build.main([]) == 0
    summary = json.loads(
        (OUT / "collector_v1_august1_snapshot_bound_current_foundation_summary.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == "PASS_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION"
    assert summary["foundation_rows"] == 50
    assert summary["accepted_listing_rows"] == 562
    assert summary["products_with_direct_history"] == 49
    assert summary["products_without_direct_history"] == 1
    assert summary["purchase_recommendations_authorized"] is False

    frame = pd.read_csv(
        OUT / "collector_v1_august1_snapshot_bound_current_foundation.csv", dtype=str
    ).fillna("")
    assert len(frame) == 50
    assert frame["tcgplayer_product_id"].is_unique
    assert frame["source_snapshot_id"].eq("collector-20260801T211201Z-7688afbd").all()
    assert frame["source_observation_at_utc"].str.strip().ne("").all()
    assert frame["purchase_recommendation_authorized"].str.lower().eq("false").all()

    history_count = pd.to_numeric(frame["history_observation_count"], errors="raise")
    direct = frame["forecast_route"].isin(DIRECT_ROUTES)
    comparable = frame["forecast_route"].isin(COMPARABLE_ROUTES)
    zero_history = history_count.eq(0)

    assert history_count[direct].gt(0).all()
    assert comparable[zero_history].all()
    assert frame.loc[zero_history, "direct_history_required"].str.lower().eq("false").all()
    assert frame.loc[zero_history, "comparable_only_forecast_required"].str.lower().eq("true").all()
    assert frame.loc[zero_history, "confidence_penalty_required"].str.lower().eq("true").all()
    assert frame.loc[zero_history, "wider_uncertainty_required"].str.lower().eq("true").all()

    star_trek = frame.loc[frame["tcgplayer_product_id"].eq("706142")]
    assert len(star_trek) == 1
    row = star_trek.iloc[0]
    assert row["forecast_route"] == "COMPARABLE_PRODUCT_ADJUSTED"
    assert row["history_observation_count"] == "0"
    assert row["history_requirement_status"] == "COMPARABLE_ROUTE_NO_DIRECT_HISTORY_REQUIRED"

    assert certify.main([]) == 0
    certification = json.loads(
        (OUT / "collector_v1_august1_snapshot_bound_current_foundation_certification.json").read_text(encoding="utf-8")
    )
    assert certification["status"] == "PASS_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION_CERTIFIED"
    assert certification["current_foundation_certified"] is True
    assert certification["forecast_ranking_rebuild_authorized"] is True
    assert certification["products_with_direct_history"] == 49
    assert certification["products_without_direct_history"] == 1
    assert certification["purchase_recommendations_authorized"] is False
