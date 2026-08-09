import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_monte_carlo_purchase_ranking_v1.json"
)


def load():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_monte_carlo_uses_empirical_residuals():
    mc = load()["monte_carlo"]

    assert mc["paths_per_product_per_horizon"] == 10000
    assert mc["residual_observation_count"] == 516

    assert (
        mc["residual_sampling_method"]
        ==
        "EMPIRICAL_ANNUAL_BLOCK_BOOTSTRAP_WITH_REPLACEMENT"
    )

    assert (
        mc["gaussian_noise_substitution_allowed"]
        is False
    )


def test_long_horizon_is_not_direct_backtest():
    mc = load()["monte_carlo"]

    assert mc["three_year_direct_backtest"] is False
    assert mc["five_year_direct_backtest"] is False


def test_all_131_are_accounted_for():
    binding = load()["production_forecast_binding"]

    assert binding["direct_365_forecast_products"] == 95
    assert binding["governed_forecast_gap_products"] == 26

    assert (
        binding["canonical_without_current_price_authority"]
        == 10
    )

    assert (
        95
        + 26
        + 10
        == 131
    )


def test_purchase_score_is_not_predictive_model():
    ranking = load()["ranking"]

    assert (
        ranking["ranking_score_is_predictive_model"]
        is False
    )

    weights = ranking[
        "purchase_score_component_weights"
    ]

    assert abs(
        sum(weights.values())
        - 1.0
    ) < 1e-12


def test_no_synthetic_rank_for_gaps():
    ranking = load()["ranking"]

    assert (
        ranking[
            "unforecastable_products_may_receive_synthetic_rank"
        ]
        is False
    )


def test_case_controls():
    scope = load()["scope_controls"]

    assert scope["sealed_cases_are_targets"] is False
    assert scope["case_price_division_allowed"] is False

    assert (
        scope["synthetic_box_price_from_case_allowed"]
        is False
    )


def test_secret_lair_stays_blocked():
    contract = load()

    assert (
        contract[
            "scope_controls"
        ][
            "secret_lair_work_authorized"
        ]
        is False
    )

    assert (
        contract[
            "authorization_after_success"
        ][
            "secret_lair_work_authorized"
        ]
        is False
    )