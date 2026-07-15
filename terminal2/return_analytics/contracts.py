from __future__ import annotations

from dataclasses import dataclass

from terminal2.warehouse_core import DatasetDefinition


@dataclass(frozen=True)
class ReturnAnalyticsContract:
    name: str
    description: str
    primary_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    snapshot: bool = True

    def definition(self) -> DatasetDefinition:
        return DatasetDefinition(
            name=self.name,
            category="intelligence",
            module="terminal2.return_analytics",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version="1",
        )


BASE = (
    "investment_product_id",
    "asset_class",
    "product_name",
)

RETURN_ANALYTICS_CONTRACTS = {
    "universal_return_summary": ReturnAnalyticsContract(
        "universal_return_summary",
        "Product-level return, volatility, and drawdown summary across asset classes.",
        ("investment_product_id",),
        BASE + (
            "observation_months",
            "history_span_months",
            "first_price",
            "latest_price",
            "total_return",
            "cagr",
            "annualized_volatility",
            "maximum_drawdown",
            "analytics_status",
        ),
    ),
    "universal_rolling_returns": ReturnAnalyticsContract(
        "universal_rolling_returns",
        "Monthly prices and trailing return windows across asset classes.",
        ("price_month", "investment_product_id"),
        BASE + (
            "price_month",
            "market_price",
            "monthly_return",
            "rolling_3m_return",
            "rolling_6m_return",
            "rolling_12m_return",
            "rolling_24m_return",
        ),
        False,
    ),
    "universal_drawdown_series": ReturnAnalyticsContract(
        "universal_drawdown_series",
        "Monthly peak, drawdown, and underwater duration across asset classes.",
        ("price_month", "investment_product_id"),
        (
            "price_month",
            "investment_product_id",
            "asset_class",
            "market_price",
            "running_peak_price",
            "drawdown",
            "underwater_months",
            "recovery_state",
        ),
        False,
    ),
    "universal_risk_adjusted_returns": ReturnAnalyticsContract(
        "universal_risk_adjusted_returns",
        "Risk-adjusted return metrics across asset classes.",
        ("investment_product_id",),
        BASE + (
            "annualized_return",
            "annualized_volatility",
            "downside_deviation",
            "sharpe_like_ratio",
            "sortino_like_ratio",
            "return_to_drawdown_ratio",
        ),
    ),
    "universal_momentum_analytics": ReturnAnalyticsContract(
        "universal_momentum_analytics",
        "Current momentum, persistence, and trend classification.",
        ("investment_product_id",),
        BASE + (
            "return_3m",
            "return_6m",
            "return_12m",
            "positive_month_ratio",
            "momentum_persistence",
            "momentum_state",
        ),
    ),
    "universal_return_rankings": ReturnAnalyticsContract(
        "universal_return_rankings",
        "Unified and within-asset-class performance rankings.",
        ("investment_product_id",),
        BASE + (
            "return_rank",
            "risk_adjusted_rank",
            "drawdown_rank",
            "momentum_rank",
            "asset_class_rank",
            "composite_return_score",
            "composite_rank",
        ),
    ),
    "universal_return_coverage": ReturnAnalyticsContract(
        "universal_return_coverage",
        "Metric availability and history sufficiency by product.",
        ("investment_product_id",),
        BASE + (
            "observation_months",
            "history_span_months",
            "cagr_available",
            "volatility_available",
            "rolling_12m_available",
            "rolling_24m_available",
            "coverage_tier",
        ),
    ),
    "return_asset_class_summary": ReturnAnalyticsContract(
        "return_asset_class_summary",
        "Return analytics coverage and performance by asset class.",
        ("asset_class",),
        (
            "asset_class",
            "product_count",
            "analytics_ready_count",
            "rolling_12m_ready_count",
            "rolling_24m_ready_count",
            "positive_cagr_count",
            "median_cagr",
            "median_volatility",
            "median_maximum_drawdown",
        ),
    ),
    "universal_return_analytics_summary": ReturnAnalyticsContract(
        "universal_return_analytics_summary",
        "Executive status of the universal return analytics layer.",
        ("snapshot_date",),
        (
            "snapshot_date",
            "product_count",
            "asset_class_count",
            "analytics_ready_count",
            "rolling_12m_ready_count",
            "rolling_24m_ready_count",
            "positive_cagr_count",
            "negative_cagr_count",
            "median_cagr",
            "median_volatility",
            "median_maximum_drawdown",
            "analytics_status",
        ),
    ),
}


def get_return_analytics_contract(name: str) -> ReturnAnalyticsContract:
    try:
        return RETURN_ANALYTICS_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown return analytics contract: {name}") from exc
