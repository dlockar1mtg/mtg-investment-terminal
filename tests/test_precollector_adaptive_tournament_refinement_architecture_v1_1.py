from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "config/mtg/standards/precollector_adaptive_tournament_refinement_architecture_recovery_contract_v1_1.json"
BUILDER = ROOT / "scripts/build_precollector_adaptive_tournament_refinement_architecture_v1_1.py"


def recovery() -> dict:
    return json.loads(RECOVERY.read_text(encoding="utf-8"))


def test_recovery_does_not_lower_candidate_minimum() -> None:
    data = recovery()
    assert data["minimum_per_fallback_group"] == 12
    assert data["controls"]["do_not_lower_candidate_minimum"] is True


def test_recovery_seeds_governed_direct_models() -> None:
    data = recovery()["governed_recovery_models_by_route"]
    assert data["DIRECT_HISTORY_CALIBRATED"] == [
        "NAIVE_LAST_VALUE", "DRIFT", "ROBUST_LOG_LINEAR", "DAMPED_TREND", "EXPONENTIAL_SMOOTHING"
    ]
    assert data["DIRECT_HISTORY_LIMITED"] == [
        "NAIVE_LAST_VALUE", "DRIFT", "ROBUST_LOG_LINEAR", "SHRUNK_DIRECT_COMPARABLE_BLEND"
    ]


def test_recovery_preserves_fallback_and_folds() -> None:
    controls = recovery()["controls"]
    assert controls["preserve_round_one_fallback"] is True
    assert controls["preserve_round_one_fold_membership"] is True
    assert controls["do_not_force_winner"] is True


def test_recovery_preserves_downstream_blocks() -> None:
    controls = recovery()["controls"]
    for key in [
        "final_winner_certification_authorized",
        "forecast_generation_authorized",
        "ranking_execution_authorized",
        "purchase_analysis_authorized",
        "purchase_recommendation_authorized",
    ]:
        assert controls[key] is False


def test_builder_has_no_subprocess_or_network_execution() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "requests" not in text
    assert "urlopen" not in text
    assert "REFINEMENT_EXECUTION_PERFORMED=FALSE" in text


def test_builder_records_recovery_governance() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert "GOVERNED_ROUTE_EVIDENCE_RECOVERY_SEED" in text
    assert '"candidate_minimum_lowered": False' in text
    assert '"round_one_fold_membership_changed": False' in text


def test_builder_module_loads() -> None:
    spec = importlib.util.spec_from_file_location("precollector_round_two_architecture_v1_1", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
