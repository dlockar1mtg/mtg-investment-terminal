from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_final_premodel_user_exclusion_resolution_contract_v1.json"
EXCLUSIONS = ROOT / "data/governance/mtg/standards/collector_user_investment_exclusions_v1.csv"
SCRIPT = ROOT / "scripts/certify_collector_v1_final_premodel_user_exclusion_resolution.py"


def test_contract_is_parseable_and_preserves_comparable_minimum() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["contract_name"] == "Collector Final Pre-Model User Exclusion Resolution"
    assert payload["required_product_count"] == 50
    assert payload["required_user_exclusions"] == 1
    assert payload["required_certified_comparable_groups"] == 23
    assert payload["required_forecast_authorized_products"] == 48
    assert payload["required_deferred_products"] == 2
    assert payload["minimum_comparables_per_certified_group"] == 3
    assert payload["required_controls"]["three_comparable_minimum_not_weakened"] is True


def test_exclusion_registry_contains_exact_governed_product() -> None:
    with EXCLUSIONS.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    row = rows[0]
    assert row["canonical_product_id"] == "MTG-CANON-TCGPLAYER-515906"
    assert row["tcgplayer_product_id"] == "515906"
    assert row["required_forecast_route"] == "DEFERRED_INSUFFICIENT_EVIDENCE"
    assert row["purchase_analysis_allowed"].lower() == "false"
    assert row["purchase_recommendation_authorized"].lower() == "false"
    assert row["permanent_until_changed"].lower() == "true"


def test_script_uses_exact_expected_base_failure() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert "BASE_FAILURE_SET_NOT_EXACTLY_EXPECTED" in text
    assert contract["expected_base_failure"] == "INSUFFICIENT_COMPARABLES:MTG-CANON-TCGPLAYER-515906:2"


def test_script_preserves_registry_but_blocks_investment_outputs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"governed_registry_retained": True' in text
    assert '"current_price_authority_retained": True' in text
    assert '"historical_ledger_retained": True' in text
    assert '"model_tournament_allowed": False' in text
    assert '"ranking_allowed": False' in text
    assert '"allocation_allowed": False' in text
    assert '"purchase_analysis_allowed": False' in text
    assert '"purchase_recommendation_authorized": False' in text


def test_script_assigns_governed_user_exclusion_route() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"routing_status": "GOVERNED_USER_EXCLUSION"' in text
    assert '"investable_universe_status": "USER_EXCLUDED_NON_INVESTABLE"' in text
    assert "only two governed comparables exist" in text


def test_script_does_not_weaken_comparable_pool_rule() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "minimum_comparables_per_certified_group" in text
    assert "maximum_comparables_per_certified_group" in text
    assert '"three_comparable_minimum_unchanged": True' in text


def test_script_outputs_all_final_certification_artifacts() -> None:
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
        "collector_user_investment_exclusion_certification.csv",
        "collector_final_premodel_user_exclusion_resolution_summary.json",
    ]
    for name in required:
        assert name in text


def test_script_keeps_production_and_purchase_authority_closed() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"production_forecasting_authorized": False' in text
    assert '"uip_delivery_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text


def test_expected_final_status() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["expected_status"] == "PASS_COLLECTOR_FINAL_PREMODEL_USER_EXCLUSION_RESOLUTION"
