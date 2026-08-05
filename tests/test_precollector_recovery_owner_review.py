from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_recovery_owner_review_contract_v1.json"
SCRIPT = ROOT / "scripts/review_precollector_recovery_state.py"


def test_contract_exists_and_binds_precollector_lane():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["governed_lane"] == "precollector_booster_boxes"
    assert payload["review_scope"]["read_only"] is True


def test_contract_binds_certified_audit_package():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    required = payload["required_recovery_audit_package"]
    assert required["package_name"] == "MTG_PreCollector_Recovery_State_Audit_v1.zip"
    assert required["sha256"] == "8d8ae7a32766d77ef32e67a8a96861ec553ab1fc7e2c2d903da3fe13a9bd2018"


def test_review_cannot_authorize_downstream_execution():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rules = payload["decision_rules"]
    assert rules["forecast_authorization_may_be_granted"] is False
    assert rules["ranking_authorization_may_be_granted"] is False
    assert rules["purchase_authorization_may_be_granted"] is False


def test_required_outputs_are_complete():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert len(payload["required_outputs"]) == 7
    assert "precollector_recovery_owner_review_summary.json" in payload["required_outputs"]


def test_review_script_is_read_only_and_present():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "PASS_PRECOLLECTOR_RECOVERY_OWNER_REVIEW" in text
    assert "AUTHENTIC_CONTROL_POINT_CERTIFIED=FALSE" in text
    assert "FORECAST_EXECUTION_AUTHORIZED=FALSE" in text
