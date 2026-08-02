from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_lorwyn_target_specific_comparable_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_lorwyn_target_specific_comparables.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_contract_requires_governed_target_specific_selection() -> None:
    contract = load_contract()
    assert contract["requested_product_name"] == "Lorwyn Eclipsed - Collector Booster Display"
    assert contract["identity_resolution_mode"] == "EXACT_NORMALIZED_NAME_SINGLE_AUTHORITY_ROW"
    assert contract["minimum_comparables"] == 5
    assert contract["maximum_comparables"] == 7
    assert contract["minimum_similarity_score"] == 55.0
    assert contract["minimum_dimension_coverage"] == 0.8
    assert contract["minimum_history_observations"] == 6


def test_contract_has_no_manual_product_identity_assertions() -> None:
    payload = load_contract()
    text = json.dumps(payload)
    assert '"canonical_product_id"' not in text
    assert '"tcgplayer_product_id"' not in text
    assert '"investment_product_id"' not in text


def test_contract_preserves_downstream_blocks() -> None:
    rules = load_contract()["rules"]
    assert rules["certified_authority_is_only_identity_source"] is True
    assert rules["manual_identity_assertions_prohibited"] is True
    assert rules["target_cannot_compare_to_itself"] is True
    assert rules["peer_release_must_precede_target_release"] is True
    assert rules["peer_must_have_minimum_history"] is True
    assert rules["missing_values_are_not_zero_filled"] is True
    assert rules["weak_peers_must_not_be_forced"] is True
    assert rules["existing_comparable_authority_must_not_be_modified"] is True
    assert rules["current_ebay_prices_prohibited_as_historical_returns"] is True
    assert rules["generic_return_pool_prohibited"] is True
    assert rules["projection_authorized"] is False
    assert rules["production_forecast_authorized"] is False
    assert rules["ranking_authorized"] is False
    assert rules["purchase_recommendations_authorized"] is False


def test_script_uses_exact_certified_authorities() -> None:
    contract = load_contract()
    for relative in contract["authorities"].values():
        assert (ROOT / relative).is_file(), relative


def test_script_has_required_outputs_and_failures() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    required = [
        "collector_lorwyn_comparable_candidate_audit.csv",
        "collector_lorwyn_certified_comparable_group.csv",
        "collector_lorwyn_comparable_exclusion_ledger.csv",
        "collector_lorwyn_comparable_score_components.csv",
        "collector_lorwyn_comparable_certification_summary.json",
        "INSUFFICIENT_CERTIFIED_COMPARABLES",
        "SELF_COMPARISON_SELECTED",
        "DUPLICATE_COMPARABLE_SELECTED",
        "EXISTING_COMPARABLE_AUTHORITY_MODIFIED",
        "PEER_RELEASE_BEFORE_TARGET;EVIDENCE_CUTOFF_2026-08-01",
        "ELEVATED_UNCERTAINTY_NO_DIRECT_TARGET_HISTORY",
    ]
    for token in required:
        assert token in text


def test_script_contains_no_hardcoded_product_identity() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any(value.startswith("MTG-CANON-TCGPLAYER-") for value in strings)


def test_weights_sum_to_one() -> None:
    weights = load_contract()["weights"]
    assert abs(sum(float(value) for value in weights.values()) - 1.0) < 1e-9
