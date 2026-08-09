from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_83_product_taxonomy_method_routing.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_83_product_taxonomy_method_routing_contract_v1.json"
DECISION = ROOT / "config/mtg/governance/precollector_owner_selected_production_lane_v2.json"

spec = importlib.util.spec_from_file_location("precollector_83_routing", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_contract_locks_83_selected_and_11_excluded() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["expected_selected_product_count"] == 83
    assert payload["expected_excluded_product_count"] == 11
    assert payload["source_review_product_count"] == 94


def test_owner_decision_excludes_reference_lane() -> None:
    payload = json.loads(DECISION.read_text(encoding="utf-8"))
    assert payload["owner_approval_status"] == "APPROVED"
    assert payload["selected_production_product_count"] == 83
    assert payload["excluded_product_count"] == 11
    assert payload["analytical_reference_lane_count"] == 0
    assert payload["excluded_product_policy"]["comparable_target_eligibility"] is False
    assert payload["excluded_product_policy"]["comparable_donor_eligibility"] is False


def test_family_classifier_preserves_specialty_classes() -> None:
    assert module.classify_family("Ultimate Masters - Booster Box") == "MASTERS"
    assert module.classify_family("Modern Masters 2017 - Booster Box") == "MASTERS"
    assert module.classify_family("Battlebond - Booster Box") == "SUPPLEMENTAL_DRAFT"
    assert module.classify_family("Conspiracy - Booster Box") == "SUPPLEMENTAL_DRAFT"
    assert module.classify_family("Unstable - Booster Box") == "NONSTANDARD_SPECIALTY"
    assert module.classify_family("Core Set 2020 - Booster Box") == "CORE"
    assert module.classify_family("Dominaria - Booster Box") == "STANDARD_EXPANSION"


def test_upstream_routes_map_to_governed_methods() -> None:
    assert module.method_from_route("DIRECT_EVIDENCE") == "DIRECT_HISTORY_CALIBRATED"
    assert module.method_from_route("DIRECT_HISTORY_LIMITED") == "DIRECT_HISTORY_LIMITED"
    assert module.method_from_route("COMPARABLE_PRODUCT_ADJUSTED") == "COMPARABLE_PRODUCT_ADJUSTED"


def test_lifecycle_is_deterministic() -> None:
    assert module.lifecycle(2.9) == "EARLY"
    assert module.lifecycle(3.0) == "DEVELOPING"
    assert module.lifecycle(7.0) == "MATURE"
    assert module.lifecycle(12.0) == "LEGACY"


def test_liquidity_class_is_fail_closed() -> None:
    assert module.liquidity_class(10, 5, "STRONG_MATCH_COVERAGE") == "DEEP"
    assert module.liquidity_class(5, 3, "STRONG_MATCH_COVERAGE") == "ADEQUATE"
    assert module.liquidity_class(1, 1, "LIMITED_MATCH_COVERAGE") == "THIN"
    assert module.liquidity_class(0, 0, "LIMITED_MATCH_COVERAGE") == "UNOBSERVED"
    assert module.liquidity_class(10, 5, "AMBIGUOUS_RESULTS") == "AMBIGUOUS"


def test_downstream_authorities_remain_false() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["forecast_generation_authorized"] is False
    assert payload["ranking_execution_authorized"] is False
    assert payload["purchase_analysis_authorized"] is False
    assert payload["purchase_recommendation_authorized"] is False
    assert payload["automatic_purchase_execution_authorized"] is False
    assert payload["uip_delivery_authorized"] is False


def test_next_stage_is_owner_comparable_approval() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["next_stage_if_certified"] == "PRECOLLECTOR_OWNER_COMPARABLE_SELECTION_APPROVAL"
