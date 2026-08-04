from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_horizon_tournament_execution_from_certified_bundle_contract_v1.json"
RUNNER = ROOT / "scripts/run_precollector_horizon_tournaments_from_certified_bundle.py"


def contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_binds_expected_certified_counts() -> None:
    data = contract()
    assert data["expected_active_product_count"] == 79
    assert data["expected_horizon_count"] == 5
    assert data["expected_route_count"] == 3
    assert data["expected_product_horizon_rows"] == 395
    assert data["expected_winner_rows"] == 15


def test_contract_requires_all_seven_certified_roles() -> None:
    assert len(contract()["required_artifact_roles"]) == 7
    assert "CANONICAL_HISTORICAL_PRICE" in contract()["required_artifact_roles"]
    assert "APPROVED_COMPARABLE_LEDGER" in contract()["required_artifact_roles"]


def test_contract_advances_to_round_two_only() -> None:
    data = contract()
    assert data["next_stage_if_certified"] == "PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE"
    assert data["round_two_refinement_required"] is True
    assert data["final_winner_certification_authorized"] is False


def test_contract_preserves_all_downstream_blocks() -> None:
    data = contract()
    for key in [
        "forecast_generation_authorized", "ranking_execution_authorized",
        "purchase_analysis_authorized", "purchase_recommendation_authorized",
        "automatic_purchase_execution_authorized", "uip_delivery_authorized",
    ]:
        assert data[key] is False


def test_runner_has_no_recursive_or_network_execution() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "requests" not in text
    assert "urlopen" not in text
    assert "rmtree" not in text
    assert "invoke_upstream_builders" not in text


def test_runner_reads_certified_zip_members() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "zipfile.ZipFile" in text
    assert "member_sha256" in text
    assert "load_certified_inputs" in text


def test_runner_executes_independent_horizon_route_competitions() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "models_by_group" in text
    assert "COMPETITIVE_WINNER" in text
    assert "CONSERVATIVE_FALLBACK_INSUFFICIENT_EVIDENCE" in text
    assert "winner_registry_rows" in text


def test_runner_preserves_round_two_and_authority_blocks() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert '"round_two_refinement_required": True' in text
    assert '"final_winner_certification_authorized": False' in text
    assert '"forecast_generation_authorized": False' in text
    assert 'print("RECURSIVE_UPSTREAM_REBUILD_PERFORMED=FALSE")' in text
    assert 'print("LIVE_NETWORK_COLLECTION_PERFORMED=FALSE")' in text


def test_runner_module_loads() -> None:
    spec = importlib.util.spec_from_file_location("precollector_certified_bundle_round_one", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
