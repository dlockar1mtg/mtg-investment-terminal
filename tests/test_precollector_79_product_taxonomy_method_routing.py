from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_79_product_taxonomy_method_routing_contract_v1.json"
DECISION = ROOT / "config/mtg/governance/precollector_owner_selected_production_lane_v3.json"

NEWLY_EXCLUDED = {
    "tcgplayer:27279",
    "tcgplayer:27278",
    "tcgplayer:27258",
    "tcgplayer:27269",
}


def test_contract_locks_79_selected_and_15_excluded() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["expected_selected_product_count"] == 79
    assert payload["expected_excluded_product_count"] == 15
    assert payload["source_review_product_count"] == 94


def test_owner_decision_reconciles_all_exclusions() -> None:
    payload = json.loads(DECISION.read_text(encoding="utf-8"))
    excluded = payload["excluded_products"]
    excluded_ids = {row["canonical_product_id"] for row in excluded}
    assert payload["owner_approval_status"] == "APPROVED"
    assert payload["selected_production_product_count"] == 79
    assert payload["excluded_product_count"] == 15
    assert len(excluded) == 15
    assert len(excluded_ids) == 15
    assert NEWLY_EXCLUDED.issubset(excluded_ids)


def test_all_excluded_products_are_blocked_downstream() -> None:
    payload = json.loads(DECISION.read_text(encoding="utf-8"))
    policy = payload["excluded_product_policy"]
    for key in (
        "active_analytical_lane",
        "forecast_method_routing",
        "comparable_target_eligibility",
        "comparable_donor_eligibility",
        "forecast_generation",
        "ranking_execution",
        "purchase_analysis",
        "purchase_recommendation",
        "uip_delivery",
    ):
        assert policy[key] is False


def test_downstream_authorities_remain_false() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["forecast_generation_authorized"] is False
    assert payload["ranking_execution_authorized"] is False
    assert payload["purchase_analysis_authorized"] is False
    assert payload["purchase_recommendation_authorized"] is False
    assert payload["automatic_purchase_execution_authorized"] is False
    assert payload["uip_delivery_authorized"] is False


def test_next_stage_remains_owner_comparable_approval() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["next_stage_if_certified"] == "PRECOLLECTOR_OWNER_COMPARABLE_SELECTION_APPROVAL"
