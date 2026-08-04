from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_owner_approved_comparable_ledger_validation.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_owner_approved_comparable_ledger_validation_contract_v1.json"
APPROVAL = ROOT / "config/mtg/governance/precollector_owner_comparable_selection_approval_v1.json"

spec = importlib.util.spec_from_file_location("precollector_comparable_ledger", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_contract_locks_governed_counts() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["expected_active_product_count"] == 79
    assert payload["expected_excluded_product_count"] == 15
    assert payload["expected_required_comparable_target_count"] == 23
    assert payload["expected_fully_comparable_adjusted_target_count"] == 3


def test_owner_approval_is_bound_to_certified_package() -> None:
    payload = json.loads(APPROVAL.read_text(encoding="utf-8"))
    assert payload["owner_approval_status"] == "APPROVED"
    assert payload["certified_input_package"]["sha256"] == "de1971a2bbfea240757587a9e7871e686c19bf309d6722d1f3420185e610449a"
    assert payload["active_product_count"] == 79
    assert payload["required_comparable_target_count"] == 23


def test_designation_is_deterministic() -> None:
    assert module.designation(1, 2) == "PRIMARY"
    assert module.designation(2, 2) == "PRIMARY"
    assert module.designation(3, 2) == "SECONDARY"
    assert module.designation(5, 2) == "SECONDARY"


def test_distance_weight_declines_with_distance() -> None:
    weights = {"1": 1.0, "2": 0.75, "3": 0.5, "4": 0.35, "5": 0.25}
    near = module.weight_for(1, 1.0, weights, 0.15)
    far = module.weight_for(1, 8.0, weights, 0.15)
    assert near > far > 0


def test_direct_history_limited_cap_is_validation_only() -> None:
    caps = {
        "PRIMARY": 0.45,
        "SECONDARY": 0.25,
        "DISTANT_CORE": 0.12,
        "LOWER_RANKED_LORWYN_NEMESIS": 0.10,
        "DIRECT_HISTORY_LIMITED_VALIDATION_ONLY": 0.08,
    }
    policy, cap = module.cap_policy("Magic 2012 - Booster Box", "CORE", "DIRECT_HISTORY_LIMITED", 1, caps)
    assert policy == "DIRECT_HISTORY_LIMITED_VALIDATION_ONLY"
    assert cap == 0.08


def test_distant_core_cap_applies() -> None:
    caps = {
        "PRIMARY": 0.45,
        "SECONDARY": 0.25,
        "DISTANT_CORE": 0.12,
        "LOWER_RANKED_LORWYN_NEMESIS": 0.10,
        "DIRECT_HISTORY_LIMITED_VALIDATION_ONLY": 0.08,
    }
    policy, cap = module.cap_policy("Core Set 2020 - Booster Box", "CORE", "COMPARABLE_PRODUCT_ADJUSTED", 3, caps)
    assert policy == "DISTANT_CORE"
    assert cap == 0.12


def test_lorwyn_and_nemesis_lower_rank_cap_applies() -> None:
    caps = {
        "PRIMARY": 0.45,
        "SECONDARY": 0.25,
        "DISTANT_CORE": 0.12,
        "LOWER_RANKED_LORWYN_NEMESIS": 0.10,
        "DIRECT_HISTORY_LIMITED_VALIDATION_ONLY": 0.08,
    }
    for target in ["Lorwyn - Booster Box", "Nemesis - Booster Box"]:
        policy, cap = module.cap_policy(target, "STANDARD_EXPANSION", "COMPARABLE_PRODUCT_ADJUSTED", 3, caps)
        assert policy == "LOWER_RANKED_LORWYN_NEMESIS"
        assert cap == 0.10


def test_downstream_authority_remains_false() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["forecast_generation_authorized"] is False
    assert payload["ranking_execution_authorized"] is False
    assert payload["purchase_analysis_authorized"] is False
    assert payload["purchase_recommendation_authorized"] is False
    assert payload["automatic_purchase_execution_authorized"] is False
    assert payload["uip_delivery_authorized"] is False


def test_next_stage_is_model_tournament() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["next_stage_if_certified"] == "PRECOLLECTOR_COMPARABLE_MODEL_TOURNAMENT_AND_CALIBRATION"
