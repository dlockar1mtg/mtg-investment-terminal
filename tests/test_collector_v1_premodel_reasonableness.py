from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_premodel_reasonableness_audit_contract_v1.json"
SCRIPT = ROOT / "scripts/audit_collector_v1_premodel_reasonableness.py"


def test_contract_exists_and_is_bounded() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["contract_name"] == "Collector Pre-Model Data Reasonableness and Leakage Audit"
    assert payload["required_product_count"] == 50
    assert payload["required_ledger_rows"] == 1215
    assert len(payload["required_evaluations"]) == 12


def test_thresholds_are_conservative() -> None:
    thresholds = json.loads(CONTRACT.read_text(encoding="utf-8"))["thresholds"]
    assert thresholds["extreme_absolute_monthly_return"] == 0.50
    assert thresholds["severe_absolute_monthly_return"] == 1.00
    assert thresholds["minimum_direct_history_observations"] >= 18
    assert thresholds["minimum_direct_history_span_days"] >= 365


def test_downstream_authorizations_remain_false() -> None:
    authorization = json.loads(CONTRACT.read_text(encoding="utf-8"))["authorization"]
    assert authorization["historical_coverage_assessment_authorized"] is True
    assert authorization["lifecycle_panel_build_authorized"] is False
    assert authorization["model_tournament_authorized"] is False
    assert authorization["production_forecasting_authorized"] is False
    assert authorization["uip_delivery_authorized"] is False
    assert authorization["purchase_recommendations_authorized"] is False


def test_script_covers_all_twelve_risk_areas() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    tokens = [
        "Governance audit freshness",
        "Uneven historical coverage",
        "Small samples",
        "Current versus historical anchor",
        "Selected-price method transitions",
        "Release and presale alignment",
        "Extreme movements and flatlines",
        "Current-universe survivorship bias",
        "Comparable-route validity",
        "Current-only feature leakage",
        "Cross-market source mismatch",
        "Current-price authority status",
    ]
    assert all(token in text for token in tokens)


def test_script_blocks_modeling_and_purchase_authorization() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"lifecycle_panel_build_authorized": False' in text
    assert '"model_tournament_authorized": False' in text
    assert '"production_forecasting_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text


def test_script_writes_required_audit_outputs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "collector_premodel_product_reasonableness.csv" in text
    assert "collector_premodel_anomalies.csv" in text
    assert "collector_premodel_structural_risks.csv" in text
    assert "collector_premodel_reasonableness_summary.json" in text


def test_current_only_supply_is_not_loaded_as_historical_ledger_feature() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "current-only features from historical folds" in text.lower()
    assert "supply__accepted_listing_count" not in text
