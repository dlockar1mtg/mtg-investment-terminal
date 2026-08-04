from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_adaptive_tournament_refinement_execution_contract_v1.json"
RUNNER = ROOT / "scripts/run_precollector_adaptive_tournament_refinement_execution.py"


def contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_binds_certified_packages() -> None:
    data = contract()
    assert data["required_round_one_package"]["sha256"] == "0088ddd5f1a87c12eb720956c75605f821aafa6d2e495d2b4c291065080ec231"
    assert data["required_architecture_package"]["sha256"] == "42ca503d11a8a85ba5519739f273b4f7d9c6e3a8f83ca6df541d00d413ae06be"


def test_contract_preserves_architecture_counts() -> None:
    assert contract()["expected_counts"] == {
        "refinement_groups": 15,
        "competitive_groups": 9,
        "fallback_recovery_groups": 6,
        "parameter_candidates": 2011,
        "preserved_folds": 1992,
    }


def test_contract_requires_untouched_champion_partition() -> None:
    fold = contract()["fold_assignment"]
    assert fold["method"] == "DETERMINISTIC_HASH_PARTITION"
    assert fold["minimum_champion_folds_for_promotion"] >= 3
    assert fold["minimum_discovery_folds_for_selection"] >= 6


def test_contract_keeps_final_and_downstream_authority_false() -> None:
    data = contract()
    for key in [
        "final_winner_certification_authorized", "forecast_generation_authorized",
        "ranking_execution_authorized", "purchase_analysis_authorized",
        "purchase_recommendation_authorized", "automatic_purchase_execution_authorized",
        "uip_delivery_authorized",
    ]:
        assert data[key] is False


def test_contract_advances_only_to_final_champion_architecture() -> None:
    assert contract()["next_stage_if_certified"] == "PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_ARCHITECTURE"


def test_runner_has_no_recursive_or_network_execution() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "requests" not in text
    assert "urlopen" not in text
    assert "rmtree" not in text


def test_runner_hash_binds_both_packages() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "CERTIFIED_PACKAGE_HASH_DRIFT" in text
    assert "load_zip_binding" in text


def test_runner_preserves_folds_and_separates_roles() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert 'role = "CHAMPION"' in text
    assert '"preserved_fold_membership_changed": False' in text
    assert "DETERMINISTIC_HASH_PARTITION" in CONTRACT.read_text(encoding="utf-8")


def test_runner_applies_penalties_and_boundary_review() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "multiple_testing_penalty_scale" in text
    assert "complexity_penalty_per_parameter" in text
    assert "BOUNDARY_EXPANSION_REQUIRED" in text


def test_runner_does_not_force_winner() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "NO_PROMOTION_INSUFFICIENT_EVIDENCE" in text
    assert "ROUND_ONE_LEADER_RETAINED" in text
    assert '"final_winner_certification_authorized": False' in text


def test_runner_module_loads() -> None:
    spec = importlib.util.spec_from_file_location("precollector_round2_execution", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
