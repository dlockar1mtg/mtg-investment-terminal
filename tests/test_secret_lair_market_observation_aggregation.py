from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("aggregation", ROOT / "scripts/aggregate_secret_lair_market_observations.py")
assert SPEC and SPEC.loader
AGG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AGG)


def test_percentile_interpolates():
    assert AGG.percentile([10, 20, 30, 40], 0.25) == 17.5


def test_outlier_bounds_reject_high_extreme():
    low, high = AGG.outlier_bounds([10, 11, 12, 13, 100])
    assert low <= 10
    assert high < 100


def test_dedupe_keeps_highest_match_score():
    rows = [
        {"canonical_product_id": "A", "ebay_item_id": "1", "match_score": "0.8"},
        {"canonical_product_id": "A", "ebay_item_id": "1", "match_score": "0.9"},
    ]
    result = AGG.dedupe_rows(rows)
    assert len(result) == 1
    assert result[0]["match_score"] == "0.9"


def test_sample_state_thresholds():
    assert AGG.sample_state(0, 0) == "NO_ACCEPTED_EVIDENCE"
    assert AGG.sample_state(1, 1) == "SINGLE_OBSERVATION"
    assert AGG.sample_state(4, 2) == "LIMITED_EVIDENCE"
    assert AGG.sample_state(7, 3) == "MODERATE_EVIDENCE"
    assert AGG.sample_state(10, 4) == "STRONG_EVIDENCE"


def test_aggregate_product_retains_zero_evidence_product():
    product = {"canonical_product_id": "A", "canonical_product_name": "Example"}
    row = AGG.aggregate_product(product, [], "2026-07-24T00:00:00+00:00")
    assert row["canonical_product_id"] == "A"
    assert row["market_value_median"] == ""
    assert row["sample_state"] == "NO_ACCEPTED_EVIDENCE"
    assert row["confidence_score"] == 0.0
