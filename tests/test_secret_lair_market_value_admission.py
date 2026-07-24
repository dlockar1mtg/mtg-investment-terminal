from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_secret_lair_market_value_admission",
    ROOT / "scripts/build_secret_lair_market_value_admission.py",
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def row(product_id: str, decision: str, median: str = "50.0", flags: str = "") -> dict[str, str]:
    return {
        "canonical_product_id": product_id,
        "canonical_product_name": product_id,
        "quality_decision": decision,
        "quality_flags": flags,
        "market_value_median": median,
        "observation_count": "3",
        "seller_count": "3",
        "confidence_score": "80",
        "confidence_state": "HIGH",
        "sample_state": "MODERATE_EVIDENCE",
        "price_dispersion_cv": "0.1",
        "market_value_low": "45",
        "market_value_high": "55",
    }


def test_pass_rows_are_admitted():
    ledger, admitted = MOD.build_admission_rows([row("A", "PASS")])
    assert ledger[0]["admission_decision"] == "ADMITTED"
    assert ledger[0]["market_value_usd"] == "50.0"
    assert admitted[0]["canonical_product_id"] == "A"


def test_review_rows_are_suppressed():
    ledger, admitted = MOD.build_admission_rows([row("A", "REVIEW_REQUIRED", flags="LOW_CONFIDENCE")])
    assert ledger[0]["admission_decision"] == "SUPPRESSED"
    assert ledger[0]["market_value_usd"] == ""
    assert ledger[0]["suppression_reason"] == "QUALITY_REVIEW_REQUIRED:LOW_CONFIDENCE"
    assert admitted == []


def test_excluded_rows_are_suppressed():
    ledger, admitted = MOD.build_admission_rows([row("A", "EXCLUDE_FROM_MODEL", flags="NO_ACCEPTED_EVIDENCE")])
    assert ledger[0]["suppression_reason"] == "QUALITY_EXCLUDED:NO_ACCEPTED_EVIDENCE"
    assert admitted == []


def test_invalid_decision_rejected():
    try:
        MOD.build_admission_rows([row("A", "UNKNOWN")])
    except ValueError as error:
        assert "Invalid quality decision" in str(error)
    else:
        raise AssertionError("Expected invalid decision to fail")
