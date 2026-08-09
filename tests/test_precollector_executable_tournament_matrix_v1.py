import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_executable_tournament_matrix_v1.json"
)


def load():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_matrix_partition():
    counts = load()[
        "expected_matrix_counts"
    ]

    assert counts["direct_oos_executable"] == 468

    assert (
        counts[
            "blocked_point_in_time_feature_evidence"
        ]
        == 624
    )

    assert counts[
        "unsupported_long_horizon"
    ] == 728

    assert counts["total"] == 1820


def test_direct_horizons():
    assert load()[
        "direct_oos_horizons_days"
    ] == [
        90,
        180,
        365,
    ]


def test_three_and_five_year_are_not_direct_backtests():
    governance = load()[
        "long_horizon_governance"
    ]

    assert (
        governance[
            "three_year_direct_backtest_supported"
        ]
        is False
    )

    assert (
        governance[
            "five_year_direct_backtest_supported"
        ]
        is False
    )


def test_current_market_features_cannot_leak_backwards():
    governance = load()[
        "point_in_time_governance"
    ]

    assert (
        governance[
            "current_liquidity_allowed_in_historical_folds"
        ]
        is False
    )

    assert (
        governance[
            "current_source_disagreement_allowed_in_historical_folds"
        ]
        is False
    )

    assert (
        governance[
            "future_information_leakage_allowed"
        ]
        is False
    )


def test_downstream_execution_still_blocked():
    auth = load()[
        "authorization"
    ]

    assert (
        auth[
            "direct_oos_model_fitting"
        ]
        is False
    )

    assert (
        auth[
            "monte_carlo_execution"
        ]
        is False
    )

    assert (
        auth[
            "production_model_selection"
        ]
        is False
    )

    assert (
        auth[
            "forecast_execution"
        ]
        is False
    )

    assert (
        auth[
            "ranking_execution"
        ]
        is False
    )

    assert (
        auth[
            "purchase_analysis"
        ]
        is False
    )