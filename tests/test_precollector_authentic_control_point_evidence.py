from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_authentic_control_point_evidence_contract_v1.json"
SCRIPT = ROOT / "scripts/build_precollector_authentic_control_point_evidence.py"


def test_contract_is_lane_bound_and_fail_closed() -> None:
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert data["governed_lane"] == "precollector_booster_boxes"
    assert data["controls"]["collector_targets_prohibited"] is True
    assert data["controls"]["automatic_control_point_certification"] is False
    assert data["controls"]["forecast_execution_authorized"] is False


def test_owner_review_package_is_hash_bound() -> None:
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    package = data["required_owner_review_package"]
    assert package["package_name"] == "MTG_PreCollector_Recovery_Owner_Review_v1.zip"
    assert len(package["sha256"]) == 64


def test_required_outputs_are_complete() -> None:
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    outputs = data["required_outputs"]
    assert len(outputs) == 6
    assert "precollector_authentic_control_point_recommendation.json" in outputs
    assert "precollector_authentic_control_point_evidence_summary.json" in outputs


def test_builder_contains_required_safety_markers() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FORECAST_CONTROL_POINT_VALIDATION" in text
    assert "authentic_control_point_certified\": False" in text
    assert "forecast_execution_authorized\": False" in text
    assert "COLLECTOR_V1_REFERENCE_MAY_BE_VALID_COMPARABLE_OR_INVALID_TARGET" in text


def test_next_stage_requires_owner_approval_or_rejection() -> None:
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert data["next_stage_if_certified"] == "OWNER_APPROVAL_OR_REJECTION_OF_AUTHENTIC_PRECOLLECTOR_CONTROL_POINT"
