import json
from pathlib import Path

from scripts.validate_precollector_model_selection_rebinding_and_eligibility_gate import (
    EXPECTED_COUNT,
    EXPECTED_IDENTITY,
    validate_contract,
)


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_model_selection_rebinding_and_eligibility_gate_contract_v1.json"
)


def load_contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8-sig"))


def test_contract_exists():
    assert CONTRACT.is_file()


def test_canonical_universe_is_fixed():
    contract = load_contract()
    target = contract["canonical_target_authority"]

    assert EXPECTED_COUNT == 186
    assert target["canonical_product_count"] == 186
    assert target["canonical_universe_identity_sha256"] == EXPECTED_IDENTITY
    assert target["sole_binding_target_authority"] is True
    assert target["collector_target_authority_allowed"] is False


def test_no_arbitrary_chronological_exclusion():
    contract = load_contract()
    principles = contract["eligibility_principles"]

    assert principles["arbitrary_age_cutoffs_allowed"] is False
    assert principles["arbitrary_release_year_cutoffs_allowed"] is False
    assert principles["arbitrary_vintage_cutoffs_allowed"] is False


def test_exclusion_is_empirical_and_reviewed():
    contract = load_contract()
    principles = contract["eligibility_principles"]

    assert principles["canonical_products_begin_model_eligible"] is True
    assert principles["empirical_diagnostics_required"] is True
    assert principles["exclusion_for_model_improvement_alone_allowed"] is False
    assert principles["persistent_exclusion_requires_owner_review"] is True
    assert principles["excluded_training_product_remains_canonical"] is True


def test_historical_logic_preserved_but_bindings_rejected():
    contract = load_contract()
    history = contract["historical_model_selection"]

    assert history["artifact_count"] == 17
    assert history["implementation_logic_reusable"] is True
    assert history["historical_execution_bindings_reusable"] is False
    assert history["historical_snapshot_binding_authoritative"] is False
    assert history["historical_79_product_universe_authoritative"] is False
    assert history["historical_frozen_packages_authoritative"] is False


def test_model_execution_stays_disabled():
    contract = load_contract()
    auth = contract["authorization"]

    assert auth["model_execution"] is False
    assert auth["forecast_execution"] is False
    assert auth["monte_carlo_execution"] is False
    assert auth["ranking_execution"] is False
    assert auth["purchase_analysis"] is False
    assert auth["purchase_recommendations"] is False


def test_semantic_validator_passes():
    validate_contract(load_contract())