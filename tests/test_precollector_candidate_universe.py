from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_candidate_universe.py"
SPEC = importlib.util.spec_from_file_location("precollector_universe", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_contract_is_scope_bound_and_downstream_disabled():
    contract = json.loads((ROOT / "config/mtg/standards/precollector_candidate_universe_inventory_contract_v1.json").read_text(encoding="utf-8"))
    assert contract["scope_authority"] == "config/mtg/governance/precollector_booster_product_scope_owner_decision_v1.json"
    controls = contract["certification_controls"]
    assert controls["forecast_generation_authorized"] is False
    assert controls["ranking_execution_authorized"] is False
    assert controls["purchase_recommendation_authorized"] is False
    assert controls["automatic_purchase_execution_authorized"] is False


def test_scope_classification_examples():
    included = MODULE.classify_product("Modern Masters Booster Box", False)
    assert included["initial_inclusion_status"] == "INCLUDED_CANDIDATE"

    collector = MODULE.classify_product("Example Collector Booster Box", True)
    assert collector["classification_reason"] == "COLLECTOR_BOOSTER_PRODUCT"

    draft = MODULE.classify_product("Example Draft Booster Box", False)
    assert draft["classification_reason"] == "DRAFT_BOOSTER_PRODUCT"

    play = MODULE.classify_product("Example Play Booster Box", False)
    assert play["classification_reason"] == "PLAY_BOOSTER_PRODUCT"

    coexistence = MODULE.classify_product("Example Set Booster Box", True)
    assert coexistence["classification_reason"] == "RELEASE_HAS_COLLECTOR_OPTION"

    foreign = MODULE.classify_product("Japanese Example Booster Box", False)
    assert foreign["classification_reason"] == "FOREIGN_LANGUAGE_PRODUCT"

    loose = MODULE.classify_product("Example Booster Pack", False)
    assert loose["classification_reason"] == "NOT_COMPLETE_BOOSTER_BOX"


def test_inventory_validator_rejects_included_scope_violation():
    row = {
        "canonical_product_id": "tcgplayer:1",
        "product_name": "Bad Draft Booster Box",
        "release_or_group_id": "10",
        "booster_format": "DRAFT_BOOSTER",
        "language": "ENGLISH",
        "full_booster_box_indicator": True,
        "factory_sealed_product_class_indicator": True,
        "damaged_or_opened_indicator": False,
        "collector_product_indicator": False,
        "draft_product_indicator": True,
        "play_product_indicator": False,
        "collector_option_indicator": False,
        "initial_inclusion_status": "INCLUDED_CANDIDATE",
        "classification_reason": "MEETS_INITIAL_SCOPE",
        "source_reference": "fixture.csv",
    }
    frame = pd.DataFrame([row])
    try:
        MODULE._validate_inventory(frame)
    except RuntimeError as exc:
        assert "SCOPE_VIOLATION" in str(exc)
    else:
        raise AssertionError("scope violation should fail closed")


def test_required_standard_horizons_remain_unchanged():
    standard = (ROOT / "docs/standards/mtg/MTG_FORECASTING_STANDARD.md").read_text(encoding="utf-8")
    assert "Required horizons are one, three, and five years." in standard
    assert "Forecast generation and purchase authorization remain separate." in standard
