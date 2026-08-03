from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_adaptive_refinement_limited_evidence_resolution_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_adaptive_refinement_limited_evidence_resolution.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_exists_and_is_parseable() -> None:
    contract = load_contract()
    assert contract["contract_version"] == "1.0.0"
    assert contract["required_failure"] == "INSUFFICIENT_FINALISTS:REFINE-180-DIRECT_HISTORY_LIMITED"


def test_fallback_group_is_exact() -> None:
    contract = load_contract()
    assert contract["required_fallback_group_id"] == "REFINE-180-DIRECT_HISTORY_LIMITED"
    assert contract["required_fallback_horizon_days"] == 180
    assert contract["required_fallback_route"] == "DIRECT_HISTORY_LIMITED"


def test_resolution_does_not_lower_evidence_standards() -> None:
    governance = load_contract()["governance"]
    assert governance["do_not_lower_discovery_minimum"] is True
    assert governance["do_not_manufacture_finalists"] is True
    assert governance["retain_round1_champion_when_refinement_evidence_insufficient"] is True


def test_validation_controls_are_preserved() -> None:
    governance = load_contract()["governance"]
    assert governance["preserve_nested_validation"] is True
    assert governance["preserve_product_holdout"] is True
    assert governance["preserve_latest_time_holdout"] is True
    assert governance["preserve_multiple_testing_penalty"] is True


def test_current_only_features_remain_prohibited() -> None:
    governance = load_contract()["governance"]
    assert governance["current_only_features_prohibited"] is True


def test_production_and_purchase_gates_remain_closed() -> None:
    governance = load_contract()["governance"]
    assert governance["production_forecasting_authorized"] is False
    assert governance["purchase_recommendations_authorized"] is False


def test_round3_is_only_next_authorized_stage() -> None:
    governance = load_contract()["governance"]
    assert governance["round3_champion_challenge_authorized"] is True


def test_script_contains_exact_failure_validation() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "ROUND2_FAILURE_SET_NOT_EXACT" in text
    assert "FALLBACK_GROUP_ALREADY_DECIDED" in text
    assert "CURRENT_ONLY_FEATURE_LEAKAGE" in text


def test_script_records_no_manufactured_finalists() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"finalists_manufactured": False' in text
    assert '"discovery_minimum_lowered": False' in text


def test_expected_status_is_fail_closed_and_specific() -> None:
    contract = load_contract()
    assert contract["expected_status"] == "PASS_COLLECTOR_ADAPTIVE_REFINEMENT_LIMITED_EVIDENCE_RESOLUTION"
