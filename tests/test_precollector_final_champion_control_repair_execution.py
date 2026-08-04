from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_precollector_final_champion_control_repair_execution.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_final_champion_control_repair_execution_contract_v1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("repair_execution", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_files_exist():
    assert SCRIPT.is_file()
    assert CONTRACT.is_file()


def test_contract_binds_certified_packages():
    import json

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["required_repair_architecture_package"]["sha256"] == "95a5921959089d46afb527c082f0610c012c7457106c8dda9b91c830eb9b9d40"
    assert contract["required_final_challenge_package"]["sha256"] == "7cc9c8ec5adb4d57bf81156c00b36537ae65077dcceabe295cc1b1f8f2296ca3"


def test_contract_preserves_evidence():
    import json

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    prohibited = contract["prohibited_behavior"]
    assert prohibited["change_candidates"] is True
    assert prohibited["change_folds"] is True
    assert prohibited["recompute_predictions"] is True
    assert prohibited["recompute_errors"] is True
    assert prohibited["tune_models"] is True


def test_missing_bias_metric_is_not_fabricated():
    import json

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    limitation = contract["evidence_limitation"]
    assert limitation["missing_metric"] == "MEAN_SIGNED_PERCENTAGE_ERROR"
    assert limitation["hard_rejection_from_unavailable_metric_authorized"] is False
    assert limitation["required_disposition"] == "NOT_EVALUABLE_FROM_PRESERVED_SCORECARD"


def test_allowed_decisions_are_governed():
    import json

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert set(contract["allowed_repaired_decisions"]) == {
        "RETAIN_ROUND_ONE_INCUMBENT",
        "PROMOTE_FROZEN_ROUND_TWO_CHALLENGER",
        "RETAIN_GOVERNED_BASELINE",
        "GOVERNED_NO_PRODUCTION_CHAMPION",
    }


def test_output_authorizations_remain_false():
    import json

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["final_winner_certification_authorized"] is False
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_analysis_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False


def test_helpers_are_deterministic():
    module = load_module()
    assert module.clean(None) == ""
    assert module.clean(" x ") == "x"
    assert module.number("1.25") == 1.25
    assert module.number("bad") == 0.0


def test_next_stage_is_winner_uncertainty_certification():
    import json

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["next_stage_if_certified"] == "PRECOLLECTOR_WINNER_AND_UNCERTAINTY_CERTIFICATION"
