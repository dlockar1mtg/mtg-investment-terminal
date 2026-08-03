from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_94_product_evidence_comparable_review_contract_v1.json"
BUILDER = ROOT / "scripts/build_precollector_94_product_evidence_comparable_review.py"
GATE = ROOT / "scripts/run_precollector_94_product_evidence_comparable_review_gate.ps1"


def test_contract_preserves_final_universe_and_blocks_downstream_authority():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["expected_final_universe_count"] == 94
    assert contract["expected_direct_supply_authorized_count"] == 67
    assert contract["maximum_comparables_per_product"] == 5
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False
    assert contract["automatic_purchase_execution_authorized"] is False


def test_builder_uses_all_94_and_does_not_shrink_to_direct_supply_rows():
    text = BUILDER.read_text(encoding="utf-8")
    assert 'final_universe = supply[supply["model_input_status"].eq("MODEL_INPUT_CANDIDATE")]' in text
    assert "FINAL_UNIVERSE_COUNT_DRIFT" in text
    assert "DIRECT_EVIDENCE" in text
    assert "DIRECT_HISTORY_LIMITED" in text
    assert "COMPARABLE_PRODUCT_ADJUSTED" in text
    assert "PENDING_OWNER_DECISION" in text


def test_builder_requires_governed_identity_price_history_and_supply_evidence():
    text = BUILDER.read_text(encoding="utf-8")
    assert "precollector_supply_adjusted_model_eligibility_v1.csv" in text
    assert "precollector_model_input_eligibility_v1.csv" in text
    assert "precollector_current_price_authority_v1.csv" in text
    assert "precollector_current_price_blocked_v1.csv" in text
    assert "DUPLICATE_CURRENT_PRICE_IDENTITY" in text
    assert "FINAL_UNIVERSE_MISSING_POSITIVE_CURRENT_PRICE" in text


def test_comparable_matrix_is_ranked_and_owner_reviewable():
    text = BUILDER.read_text(encoding="utf-8")
    assert "comparable_distance_score" in text
    assert "comparable_rank" in text
    assert "owner_comparable_decision" in text
    assert "owner_practicality_decision" in text
    assert "confidence_penalty_required" in text


def test_gate_runs_targeted_and_full_regression_and_exports_review_package():
    text = GATE.read_text(encoding="utf-8")
    assert "test_precollector_94_product_evidence_comparable_review.py" in text
    assert "build_precollector_94_product_evidence_comparable_review.py" in text
    assert "Full repository regression suite" in text
    assert "MTG_PreCollector_94_Product_Evidence_Comparable_Review_v1.zip" in text
    assert "CERTIFIED_PASS_PRECOLLECTOR_94_PRODUCT_EVIDENCE_COMPARABLE_REVIEW_GATE" in text
