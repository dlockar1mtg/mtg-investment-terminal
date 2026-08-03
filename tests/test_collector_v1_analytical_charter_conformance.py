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
GOVERNED_ROUTES = DIRECT_ROUTES | COMPARABLE_ROUTES


def load_foundation() -> tuple[pd.DataFrame, dict, dict]:
    assert build.main([]) == 0
    assert certify.main([]) == 0
    frame = pd.read_csv(
        OUT / "collector_v1_august1_snapshot_bound_current_foundation.csv", dtype=str
    ).fillna("")
    summary = json.loads(
        (OUT / "collector_v1_august1_snapshot_bound_current_foundation_summary.json").read_text(encoding="utf-8")
    )
    certification = json.loads(
        (OUT / "collector_v1_august1_snapshot_bound_current_foundation_certification.json").read_text(encoding="utf-8")
    )
    return frame, summary, certification


def test_every_governed_product_remains_in_analysis() -> None:
    frame, summary, certification = load_foundation()
    assert len(frame) == 50
    assert frame["tcgplayer_product_id"].nunique() == 50
    assert summary["foundation_rows"] == 50
    assert certification["checks"]["no_product_excluded_for_missing_direct_history"] is True


def test_missing_history_is_not_negative_evidence_or_zero_substitution() -> None:
    frame, _, certification = load_foundation()
    history = pd.to_numeric(frame["history_observation_count"], errors="raise")
    zero_history = history.eq(0)
    assert zero_history.sum() == 1
    assert frame.loc[zero_history, "forecast_route"].isin(COMPARABLE_ROUTES).all()
    assert frame.loc[zero_history, "history_requirement_status"].eq(
        "COMPARABLE_ROUTE_NO_DIRECT_HISTORY_REQUIRED"
    ).all()
    assert frame.loc[zero_history, "confidence_penalty_required"].str.lower().eq("true").all()
    assert frame.loc[zero_history, "wider_uncertainty_required"].str.lower().eq("true").all()
    assert certification["checks"]["zero_history_products_have_uncertainty_controls"] is True


def test_history_sufficiency_is_route_aware() -> None:
    frame, _, certification = load_foundation()
    history = pd.to_numeric(frame["history_observation_count"], errors="raise")
    routes = frame["forecast_route"]
    assert routes.isin(GOVERNED_ROUTES).all()
    assert history[routes.isin(DIRECT_ROUTES)].gt(0).all()
    assert history[routes.isin(COMPARABLE_ROUTES)].ge(0).all()
    assert certification["checks"]["direct_history_routes_have_history"] is True
    assert certification["checks"]["all_products_have_valid_history_disposition"] is True


def test_technical_certification_does_not_authorize_purchases() -> None:
    frame, summary, certification = load_foundation()
    assert frame["purchase_recommendation_authorized"].str.lower().eq("false").all()
    assert summary["purchase_recommendations_authorized"] is False
    assert certification["purchase_recommendations_authorized"] is False
    assert certification["production_forecasting_authorized"] is False
    assert certification["uip_delivery_authorized"] is False
