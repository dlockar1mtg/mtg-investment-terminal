from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_collector_production_completion_v3.py"
SPEC = importlib.util.spec_from_file_location("collector_audit_v3", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_collector_row_uses_investment_product_type() -> None:
    row = {
        "investment_product_type": "Collector Booster Display",
        "box_name": "Example Collector Booster Display",
    }
    assert MODULE.is_collector_row(row)


def test_collector_row_excludes_case_configuration() -> None:
    row = {
        "investment_product_type": "Collector Booster Display",
        "box_name": "Example Collector Booster Display Case",
    }
    assert not MODULE.is_collector_row(row)


def test_product_id_supports_comparable_target_id() -> None:
    assert MODULE.product_id({"target_product_id": "TCGCSV-1-2"}) == "TCGCSV-1-2"


def test_selected_comparable_rows_are_not_unique_identity_dataset() -> None:
    rows = [
        {"target_product_id": "TARGET", "peer_product_id": "A"},
        {"target_product_id": "TARGET", "peer_product_id": "B"},
    ]
    counts = {}
    for row in rows:
        key = MODULE.product_id(row)
        counts[key] = counts.get(key, 0) + 1
    assert counts == {"TARGET": 2}


def test_hybrid_override_is_present_and_fail_closed() -> None:
    override = MODULE.load_hybrid_override()
    assert override["approved_method"] == "FUNDAMENTAL_COMPARABLE_HYBRID"
    assert override["primary_comparable_product_id"]
    assert override["projection_authorized"] is False
    assert override["purchase_recommendation_authorized"] is False


def test_active_controls_are_standard_or_owner_approved() -> None:
    traceability = MODULE.load_control_traceability()
    active = [
        control
        for control in traceability["controls"]
        if control["implementation_status"] == "ACTIVE"
    ]
    assert active
    assert all(
        control["authority_status"] in {"MTG_STANDARD", "OWNER_APPROVED"}
        for control in active
    )


def test_proposed_controls_are_empty() -> None:
    traceability = MODULE.load_control_traceability()
    assert traceability["proposed_controls"] == []
