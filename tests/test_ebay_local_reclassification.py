from __future__ import annotations

from scripts.reclassify_ebay_matching_batch import coverage_state


def test_coverage_state_strong():
    assert coverage_state(5, 0) == "STRONG_MATCH_COVERAGE"


def test_coverage_state_limited():
    assert coverage_state(1, 4) == "LIMITED_MATCH_COVERAGE"


def test_coverage_state_ambiguous():
    assert coverage_state(0, 2) == "AMBIGUOUS_RESULTS"


def test_coverage_state_no_matches():
    assert coverage_state(0, 0) == "NO_MATCHES"
