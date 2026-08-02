from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_purchase_recommendation_certification_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_purchase_recommendations.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_contract_uses_complete_ranked_authority_and_primary_horizon() -> None:
    contract = load_contract()
    assert contract["required_ranked_products"] == 49
    assert contract["primary_horizon_days"] == 365
    for relative in contract["authorities"].values():
        assert (ROOT / relative).is_file(), relative


def test_entry_rules_are_explicit_and_downside_aware() -> None:
    rules = load_contract()["entry_rules"]
    assert rules["strong_candidate_max_rank"] == 10
    assert rules["strong_candidate_min_score"] == 65.0
    assert rules["strong_candidate_max_loss_probability"] == 0.05
    assert rules["strong_candidate_min_50pct_gain_probability"] == 0.45
    assert rules["candidate_max_rank"] == 15
    assert rules["candidate_min_score"] == 58.0
    assert rules["candidate_max_loss_probability"] == 0.08
    assert rules["p25_required_upside_strong"] == 0.10


def test_contract_preserves_conditional_and_execution_blocks() -> None:
    rules = load_contract()["rules"]
    assert rules["conditional_products_must_remain_purchase_ineligible"] is True
    assert rules["current_price_must_match_certified_authority"] is True
    assert rules["p25_entry_ceiling_must_be_used"] is True
    assert rules["budget_bands_are_context_not_hard_user_limits"] is True
    assert rules["one_box_analysis_only"] is True
    assert rules["forecast_values_must_not_be_modified"] is True
    assert rules["purchase_recommendations_authorized_only_for_certified_candidates"] is True


def test_script_has_required_fail_closed_controls_and_outputs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "FINAL_RANKING_NOT_PASS",
        "RANKING_NOT_AUTHORIZED",
        "CURRENT_PRICE_AUTHORITY_MISMATCH",
        "REQUIRED_PURCHASE_INPUT_MISSING",
        "CONDITIONAL_PRODUCT_AUTHORIZED",
        "BLOCKED_PURCHASE_ROWS_PRESENT",
        "FORECAST_VALUES_MODIFIED",
        "STRONG_PURCHASE_CANDIDATE",
        "PURCHASE_CANDIDATE",
        "WATCHLIST",
        "NOT_PURCHASE_ELIGIBLE",
        "collector_purchase_recommendation_authority.csv",
        "collector_authorized_purchase_candidates.csv",
        "collector_purchase_watchlist.csv",
        "collector_purchase_recommendation_summary.json",
    ]:
        assert token in text


def test_budget_bands_are_contextual_and_cover_all_prices() -> None:
    bands = load_contract()["budget_context_bands"]
    assert [band["label"] for band in bands] == ["UNDER_400", "400_TO_600", "600_TO_1000", "OVER_1000"]
    assert bands[-1]["maximum_price"] is None


def test_script_contains_no_hardcoded_product_identity() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any(value.startswith("MTG-CANON-TCGPLAYER-") for value in strings)


def test_automatic_purchase_execution_remains_false() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"automatic_purchase_execution_authorized": False' in text
