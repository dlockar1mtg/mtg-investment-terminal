from __future__ import annotations

from scripts.normalize_collector_evidence import (
    confidence_class,
    derive_release_date,
    group_confidence,
    normalize_score,
    price_band,
    release_era,
)


POLICY = {
    "confidence_classes": {
        "HIGH": {"minimum": 80.0},
        "MODERATE": {"minimum": 60.0},
        "LOW": {"minimum": 40.0},
        "INSUFFICIENT": {"minimum": 0.0},
    },
    "comparable_classes": {
        "release_era": {
            "CURRENT": 2025,
            "RECENT": 2022,
            "EARLY_COLLECTOR": 2019,
        },
        "price_bands": [
            {
                "class": "UNDER_150",
                "maximum": 149.99,
            },
            {
                "class": "150_TO_249",
                "maximum": 249.99,
            },
            {
                "class": "250_TO_399",
                "maximum": 399.99,
            },
            {
                "class": "400_TO_599",
                "maximum": 599.99,
            },
            {
                "class": "600_PLUS",
                "maximum": None,
            },
        ],
    },
}


def test_zero_to_one_score_is_percent_scaled() -> None:
    assert normalize_score("0.75") == 75.0


def test_zero_to_100_score_is_retained() -> None:
    assert normalize_score("75") == 75.0


def test_out_of_range_score_is_missing() -> None:
    assert normalize_score("101") is None
    assert normalize_score("-1") is None


def test_group_confidence_reflects_coverage() -> None:
    count, score = group_confidence(
        [80.0, 60.0, None]
    )

    assert count == 2
    assert 0 < score < 100


def test_confidence_class_is_governed() -> None:
    assert confidence_class(
        85.0,
        POLICY,
    ) == "HIGH"

    assert confidence_class(
        65.0,
        POLICY,
    ) == "MODERATE"

    assert confidence_class(
        45.0,
        POLICY,
    ) == "LOW"


def test_price_band_is_deterministic() -> None:
    assert price_band(
        100.0,
        POLICY,
    ) == "UNDER_150"

    assert price_band(
        300.0,
        POLICY,
    ) == "250_TO_399"

    assert price_band(
        800.0,
        POLICY,
    ) == "600_PLUS"


def test_release_era_is_deterministic() -> None:
    assert release_era(
        2026,
        POLICY,
    ) == "CURRENT"

    assert release_era(
        2023,
        POLICY,
    ) == "RECENT"

    assert release_era(
        2020,
        POLICY,
    ) == "EARLY_COLLECTOR"


def test_missing_values_remain_missing() -> None:
    assert normalize_score("") is None
    assert normalize_score("unknown") is None

def test_release_date_can_be_derived_from_months() -> None:
    release_date, method = derive_release_date(
        explicit_release_date="",
        latest_observation_date="2026-07-31",
        months_since_release=74,
    )

    assert release_date == "2020-05-31"
    assert method.startswith("DERIVED_")


def test_explicit_release_date_has_priority() -> None:
    release_date, method = derive_release_date(
        explicit_release_date="2020-04-24",
        latest_observation_date="2026-07-31",
        months_since_release=74,
    )

    assert release_date == "2020-04-24"
    assert method == "DIRECT_OR_SOURCE_RELEASE_DATE"


def test_zero_months_is_valid() -> None:
    release_date, method = derive_release_date(
        explicit_release_date="",
        latest_observation_date="2026-07-31",
        months_since_release=0,
    )

    assert release_date == "2026-07-31"
    assert method.startswith("DERIVED_")