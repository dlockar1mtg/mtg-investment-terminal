from __future__ import annotations

from scripts.select_collector_comparables import (
    categorical_similarity,
    numeric_similarity,
    score_pair,
)


POLICY = {
    "minimum_similarity_score": 55.0,
    "minimum_dimension_coverage": 0.70,
    "weights": {
        "product_configuration": 0.10,
        "product_family": 0.15,
        "franchise_class": 0.10,
        "edition_class": 0.05,
        "release_era": 0.10,
        "lifecycle_stage": 0.10,
        "price_band": 0.10,
        "supply_profile": 0.10,
        "liquidity_class": 0.10,
        "demand_profile": 0.10,
    },
    "peer_quality_weights": {
        "CERTIFIED": 1.0,
        "CERTIFIED_LIMITED": 0.85,
    },
}


def evidence(
    *,
    configuration: str = "Collector Booster Display",
    era: str = "RECENT",
    lifecycle: str = "MID_LIFECYCLE",
    price_band: str = "250_TO_399",
    supply: str = "BALANCED",
    liquidity: str = "MODERATE",
    demand: str = "70",
    family: str = "STANDARD_MAGIC",
    franchise: str = "STANDARD_OR_CORE_MAGIC",
    edition: str = "STANDARD_ENGLISH",
) -> dict[str, str]:
    return {
        "product_name": (
            "Test Collector Booster Display"
        ),
        "product_configuration": configuration,
        "product_family_class": family,
        "franchise_class": franchise,
        "edition_class": edition,
        "release_era_class": era,
        "lifecycle_stage": lifecycle,
        "price_band_class": price_band,
        "supply_profile_class": supply,
        "liquidity_class": liquidity,
        "demand_score": demand,
    }


def test_matching_categories_score_one() -> None:
    score, observed = categorical_similarity(
        "RECENT",
        "RECENT",
    )

    assert score == 1.0
    assert observed is True


def test_different_categories_score_zero() -> None:
    score, observed = categorical_similarity(
        "RECENT",
        "CURRENT",
    )

    assert score == 0.0
    assert observed is True


def test_missing_category_is_unobserved() -> None:
    score, observed = categorical_similarity(
        "UNKNOWN",
        "CURRENT",
    )

    assert score == 0.0
    assert observed is False


def test_numeric_similarity_uses_distance() -> None:
    score, observed = numeric_similarity(
        80,
        70,
        100,
    )

    assert score == 0.9
    assert observed is True


def test_identical_products_score_high() -> None:
    result = score_pair(
        evidence(),
        evidence(),
        {
            "history_certification_status": (
                "CERTIFIED"
            )
        },
        POLICY,
    )

    assert result[
        "raw_similarity_score"
    ] == 100.0

    assert result[
        "adjusted_similarity_score"
    ] == 100.0

    assert result[
        "meets_similarity_threshold"
    ] is True


def test_limited_peer_receives_quality_discount() -> None:
    result = score_pair(
        evidence(),
        evidence(),
        {
            "history_certification_status": (
                "CERTIFIED_LIMITED"
            )
        },
        POLICY,
    )

    assert result[
        "adjusted_similarity_score"
    ] == 85.0


def test_weak_peer_fails_threshold() -> None:
    result = score_pair(
        evidence(
            era="CURRENT",
            lifecycle="EARLY_LIFECYCLE",
            price_band="600_PLUS",
            supply="CONSTRAINED",
            liquidity="HIGH",
            demand="90",
        ),
        evidence(
            era="EARLY_COLLECTOR",
            lifecycle="MATURE",
            price_band="UNDER_150",
            supply="ABUNDANT",
            liquidity="VERY_LOW",
            demand="10",
        ),
        {
            "history_certification_status": (
                "CERTIFIED"
            )
        },
        POLICY,
    )

    assert result[
        "meets_similarity_threshold"
    ] is False


def test_purchase_authorization_is_not_scored() -> None:
    result = score_pair(
        evidence(),
        evidence(),
        {
            "history_certification_status": (
                "CERTIFIED"
            )
        },
        POLICY,
    )

    assert (
        "purchase_recommendation_authorized"
        not in result
    )