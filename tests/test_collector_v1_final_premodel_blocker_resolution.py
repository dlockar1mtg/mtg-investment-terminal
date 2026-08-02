from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_final_premodel_blocker_resolution_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_final_premodel_blocker_resolution.py"


def test_contract_exists_and_is_parseable() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["contract_name"] == "Collector Final Pre-Model Blocker Resolution"
    assert payload["contract_version"] == "1.0.1"
    assert payload["required_product_count"] == 50
    assert payload["required_ledger_rows"] == 1215
    assert payload["required_anomaly_rows"] == 12
    assert payload["required_comparable_route_products"] == 24
    assert payload["expected_status"] == "PASS_COLLECTOR_FINAL_PREMODEL_DATA_AND_ROUTING_CERTIFICATION"


def test_contract_preserves_fail_closed_purchase_separation() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    controls = payload["required_controls"]
    assert controls["forecast_generation_separate_from_purchase_authorization"] is True
    assert controls["current_only_features_blocked_from_backtest"] is True
    assert controls["comparable_selection_time_safe"] is True
    assert controls["insufficient_evidence_may_receive_governed_deferral"] is True


def test_contract_supports_mtg_standard_routes() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    routes = set(payload["allowed_final_routes"])
    assert "DIRECT_HISTORY_CALIBRATED" in routes
    assert "DIRECT_HISTORY_LIMITED" in routes
    assert "COMPARABLE_PRODUCT_ADJUSTED" in routes
    assert "DEFERRED_MISSING_PRICE" in routes
    assert "DEFERRED_INSUFFICIENT_EVIDENCE" in routes


def test_script_exists_and_uses_certified_upstream_authorities() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "collector_v1_wizards_release_date_authority" in text
    assert "collector_v1_august1_historical_observation_ledger" in text
    assert "collector_v1_premodel_reasonableness_audit" in text
    assert "collector_v1_august1_snapshot_bound_current_foundation" in text


def test_script_builds_all_required_final_outputs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    required = [
        "collector_final_artifact_manifest.csv",
        "collector_final_feature_availability_registry.csv",
        "collector_final_current_price_authority.csv",
        "collector_final_anomaly_adjudication.csv",
        "collector_comparable_pool_certification.csv",
        "collector_final_method_routing.csv",
        "collector_structural_risk_resolution.csv",
        "collector_final_premodel_traceability.csv",
        "collector_final_premodel_data_and_routing_summary.json",
    ]
    for name in required:
        assert name in text


def test_script_blocks_current_only_features_from_backtests() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"august1_current_price", "feature_class": "CURRENT_ONLY", "backtest_allowed": False' in text
    assert '"ebay_listing_count", "feature_class": "CURRENT_ONLY", "backtest_allowed": False' in text
    assert '"current_eligibility_status", "feature_class": "PROHIBITED_FOR_BACKTEST", "backtest_allowed": False' in text


def test_script_resolves_anomalies_without_deleting_source_rows() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "RESOLVED_BY_GOVERNED_POLICY" in text
    assert "RETAIN_WITH_ROBUST_SENSITIVITY" in CONTRACT.read_text(encoding="utf-8")
    assert "EXCLUDE_TRANSITION_RETURN_FROM_PRIMARY_FIT" in CONTRACT.read_text(encoding="utf-8")
    assert "PRESALE_SEGMENT_ONLY" in CONTRACT.read_text(encoding="utf-8")


def test_script_requires_time_safe_comparables() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "candidate_release_date<=forecast_cutoff" in text
    assert "candidate_history_available_before_cutoff" in text
    assert "minimum_comparables_per_product" in text


def test_script_distinguishes_direct_history_from_total_forecast_eligibility() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "direct_history_method_allowed" in text
    assert "comparable_method_allowed" in text
    assert "forecast_output_allowed" in text


def test_script_keeps_production_and_purchase_gates_closed() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"production_forecasting_authorized": False' in text
    assert '"uip_delivery_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text
    assert '"purchase_recommendation_authorized": False' in text


def test_script_produces_mtg_standard_traceability() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for requirement_id in [
        "MTG-STD-001",
        "MTG-STD-002",
        "MTG-STD-003",
        "MTG-STD-004",
        "MTG-STD-008",
        "MTG-STD-009",
        "MTG-STD-010",
        "COL-STD-003",
        "COL-STD-004",
        "COL-STD-005",
    ]:
        assert requirement_id in text
