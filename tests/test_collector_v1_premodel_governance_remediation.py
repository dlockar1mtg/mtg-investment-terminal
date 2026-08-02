from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_premodel_governance_remediation_contract_v1.json"
SCRIPT = ROOT / "scripts/build_collector_v1_premodel_governance_remediation.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_is_bounded_and_parseable() -> None:
    payload = load_contract()
    assert payload["contract_name"] == "Collector Pre-Model Governance Remediation"
    assert payload["required_product_count"] == 50
    assert payload["required_ledger_rows"] == 1215
    assert payload["required_risk_count"] == 12
    assert len(payload["required_artifacts"]) == 7


def test_lifecycle_bands_are_explicit() -> None:
    bands = load_contract()["lifecycle_bands"]
    assert bands["PRESALE"] == [-99999, -1]
    assert bands["RELEASE_MONTH"] == [0, 30]
    assert bands["EARLY_POST_RELEASE"] == [31, 90]
    assert bands["DEVELOPING"] == [91, 365]
    assert bands["ESTABLISHED"] == [366, 99999]


def test_downstream_authorizations_remain_false() -> None:
    authorization = load_contract()["authorization"]
    assert authorization["dynamic_artifact_manifest_authorized"] is True
    assert authorization["lifecycle_candidate_build_authorized"] is True
    assert authorization["feature_availability_registry_authorized"] is True
    assert authorization["final_product_modeling_authorization"] is False
    assert authorization["model_tournament_authorized"] is False
    assert authorization["production_forecasting_authorized"] is False
    assert authorization["uip_delivery_authorized"] is False
    assert authorization["purchase_recommendations_authorized"] is False


def test_script_contains_required_governance_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    required = [
        "PASS_COLLECTOR_PREMODEL_GOVERNANCE_REMEDIATION_PACKAGE_BUILT",
        "TECHNICALLY_VALID_PENDING_STATUS_PROMOTION",
        "PROHIBITED_FOR_BACKTEST",
        "PENDING_COMPARABLE_POOL_CERTIFICATION",
        "PENDING_EVIDENCE_REVIEW",
        '"model_tournament_authorized": False',
        '"purchase_recommendations_authorized": False',
    ]
    assert all(token in text for token in required)


def test_current_only_features_are_not_backtest_allowed() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"feature_name": "ebay_listing_count", "feature_class": "PROHIBITED_FOR_BACKTEST", "backtest_allowed": False' in text
    assert '"feature_name": "august1_current_price", "feature_class": "CURRENT_ONLY", "backtest_allowed": False' in text
    assert '"feature_name": "current_eligibility_status", "feature_class": "PROHIBITED_FOR_BACKTEST", "backtest_allowed": False' in text


def test_lifecycle_output_remains_candidate_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"panel_status": "CANDIDATE_NOT_YET_AUTHORIZED"' in text
    assert '"final_modeling_authorized": False' in text
