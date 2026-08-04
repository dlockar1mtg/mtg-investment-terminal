from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_horizon_specific_tournament_execution_contract_v1.json"
WRAPPER = ROOT / "scripts/build_precollector_horizon_specific_tournament_execution_v1_1.py"
GATE = ROOT / "scripts/run_precollector_horizon_specific_tournament_execution_gate.ps1"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_execution_contract_routes_to_round_two_refinement() -> None:
    contract = load_contract()
    assert contract["next_stage_if_certified"] == "PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE"
    assert contract["round_two_policy"]["adaptive_refinement_required"] is True
    assert contract["round_two_policy"]["advance_top_contenders_per_horizon_route"] == 2


def test_round_two_preserves_round_one_splits_and_baseline_rechallenge() -> None:
    policy = load_contract()["round_two_policy"]
    assert policy["require_same_rolling_origin_splits_as_round_one"] is True
    assert policy["require_baseline_rechallenge"] is True
    assert policy["prohibit_final_champion_certification_before_round_two"] is True


def test_interface_wrapper_maps_canonical_architecture_output() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert "precollector_horizon_specific_tournament_architecture.csv" in text
    assert "precollector_horizon_tournament_architecture.csv" in text
    assert "PASS_PRECOLLECTOR_HORIZON_EXECUTION_ARCHITECTURE_INTERFACE_CORRECTION_V1_1" in text


def test_gate_uses_corrected_wrapper_and_round_two_stage() -> None:
    text = GATE.read_text(encoding="utf-8")
    assert "build_precollector_horizon_specific_tournament_execution_v1_1.py" in text
    assert "PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE" in text
    assert "ROUND_TWO_REFINEMENT_REQUIRED=TRUE" in text


def test_all_downstream_authority_remains_false() -> None:
    contract = load_contract()
    for key in [
        "forecast_generation_authorized", "ranking_execution_authorized",
        "purchase_analysis_authorized", "purchase_recommendation_authorized",
        "automatic_purchase_execution_authorized", "uip_delivery_authorized",
    ]:
        assert contract[key] is False
