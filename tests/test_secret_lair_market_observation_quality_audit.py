from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_secret_lair_market_observations",
    ROOT / "scripts/audit_secret_lair_market_observations.py",
)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def row(**overrides):
    base = {
        "observation_count": "5",
        "seller_count": "5",
        "market_value_median": "60",
        "market_value_low": "50",
        "market_value_high": "70",
        "price_dispersion_cv": "0.15",
        "outlier_count": "0",
        "accepted_observation_count": "5",
        "sample_state": "MODERATE_EVIDENCE",
        "confidence_state": "MEDIUM",
    }
    base.update(overrides)
    return base


def test_pass_decision():
    flags, decision, _ = AUDIT.classify_row(row())
    assert flags == []
    assert decision == "PASS"


def test_no_evidence_excluded():
    flags, decision, _ = AUDIT.classify_row(row(observation_count="0", seller_count="0", market_value_median=""))
    assert flags == ["NO_ACCEPTED_EVIDENCE"]
    assert decision == "EXCLUDE_FROM_MODEL"


def test_single_observation_reviewed():
    flags, decision, _ = AUDIT.classify_row(row(observation_count="1", seller_count="1", sample_state="SINGLE_OBSERVATION"))
    assert "SINGLE_OBSERVATION" in flags
    assert "WEAK_SELLER_DIVERSITY" in flags
    assert decision == "REVIEW_REQUIRED"


def test_very_low_confidence_excluded():
    flags, decision, _ = AUDIT.classify_row(row(confidence_state="VERY_LOW"))
    assert "VERY_LOW_CONFIDENCE" in flags
    assert decision == "EXCLUDE_FROM_MODEL"


def test_high_dispersion_and_value_reviewed():
    flags, decision, _ = AUDIT.classify_row(row(
        market_value_median="500",
        market_value_low="100",
        market_value_high="500",
        price_dispersion_cv="0.70",
    ))
    assert {"HIGH_DISPERSION", "HIGH_MEDIAN_VALUE", "WIDE_PRICE_RANGE"}.issubset(flags)
    assert decision == "REVIEW_REQUIRED"


def test_outlier_heavy_reviewed():
    flags, decision, _ = AUDIT.classify_row(row(outlier_count="4", accepted_observation_count="8"))
    assert "OUTLIER_HEAVY" in flags
    assert decision == "REVIEW_REQUIRED"
