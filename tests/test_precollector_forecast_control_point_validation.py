from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_forecast_control_point_validation_contract_v1.json"
SCRIPT = ROOT / "scripts/validate_precollector_forecast_control_point.py"
APPROVAL = ROOT / "config/mtg/governance/precollector_forecast_control_point_owner_approval_v1.json"


def test_contract_and_script_exist():
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()


def test_owner_approval_exists_and_matches_restart_stage():
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    assert approval["approved_restart_stage"] == "FORECAST_CONTROL_POINT_VALIDATION"


def test_contract_blocks_downstream_execution():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    controls = contract["validation_controls"]
    assert controls["forecast_execution_authorized_by_this_stage"] is False
    assert controls["ranking_execution_authorized_by_this_stage"] is False
    assert controls["purchase_analysis_authorized_by_this_stage"] is False


def test_contract_forbids_collector_target_authority():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["validation_controls"]["collector_foundation_allowed_as_target"] is False
    assert contract["validation_controls"]["collector_products_allowed_as_comparables"] is True


def test_script_contains_fail_closed_controls():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "COLLECTOR_TARGET_AUTHORITY_BINDING" in text
    assert "NO_EXPLICIT_PRECOLLECTOR_TARGET_AUTHORITY_BINDING" in text
    assert "control_point_validated" in text
