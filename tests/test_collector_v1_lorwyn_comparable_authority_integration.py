from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_lorwyn_comparable_authority_integration_contract_v1.json"
SCRIPT = ROOT / "scripts/integrate_collector_v1_lorwyn_comparable_authority.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_contract_has_exact_authority_counts() -> None:
    contract = load_contract()
    assert contract["required_original_rows"] == 115
    assert contract["required_supplemental_rows"] == 6
    assert contract["required_integrated_rows"] == 121
    assert contract["required_original_targets"] == 23
    assert contract["required_integrated_targets"] == 24


def test_contract_uses_existing_certified_outputs_only() -> None:
    authorities = load_contract()["authorities"]
    for relative in authorities.values():
        assert (ROOT / relative).is_file(), relative


def test_contract_contains_no_manual_product_identity() -> None:
    payload = load_contract()
    text = json.dumps(payload)
    assert '"canonical_product_id"' not in text
    assert '"tcgplayer_product_id"' not in text
    assert '"investment_product_id"' not in text


def test_governance_controls_are_fail_closed() -> None:
    rules = load_contract()["rules"]
    for key in [
        "certified_authority_is_only_identity_source",
        "manual_identity_assertions_prohibited",
        "original_authority_must_remain_byte_identical",
        "supplemental_certification_must_pass",
        "target_and_member_names_must_match_authority",
        "target_and_member_release_dates_must_match_authority",
        "peer_release_must_precede_target_release",
        "supplemental_members_must_have_history",
        "duplicate_target_member_pairs_prohibited",
        "self_comparisons_prohibited",
        "silent_field_substitution_prohibited",
    ]:
        assert rules[key] is True
    assert rules["projection_authorized"] is False
    assert rules["production_forecast_authorized"] is False
    assert rules["ranking_authorized"] is False
    assert rules["purchase_recommendations_authorized"] is False


def test_script_preserves_original_schema_and_authority() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "ORIGINAL_FIELDS",
        "ORIGINAL_COMPARABLE_AUTHORITY_MODIFIED",
        "SUPPLEMENTAL_ROW_RECONCILIATION_FAILED",
        "DUPLICATE_SUPPLEMENTAL_TARGET_MEMBER_PAIR",
        "SUPPLEMENTAL_PAIR_COLLIDES_WITH_ORIGINAL_AUTHORITY",
        "DUPLICATE_INTEGRATED_TARGET_MEMBER_PAIR",
        "collector_integrated_comparable_pool_authority.csv",
        "collector_lorwyn_supplemental_comparable_integration_audit.csv",
        "collector_lorwyn_comparable_authority_integration_summary.json",
    ]:
        assert token in text


def test_script_contains_no_hardcoded_product_identity() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any(value.startswith("MTG-CANON-TCGPLAYER-") for value in strings)


def test_output_authority_path_is_deterministic() -> None:
    contract = load_contract()
    assert contract["output_authority"] == (
        "data/governance/permanence/certification/"
        "collector_v1_lorwyn_comparable_authority_integration/"
        "collector_integrated_comparable_pool_authority.csv"
    )
