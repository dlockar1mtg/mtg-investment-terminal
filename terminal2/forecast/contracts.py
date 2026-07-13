from __future__ import annotations

from dataclasses import dataclass

from terminal2.warehouse_core import DatasetDefinition


@dataclass(frozen=True)
class ForecastDatasetContract:
    name: str
    category: str
    description: str
    primary_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    snapshot: bool = True
    version: str = "1"

    def definition(self) -> DatasetDefinition:
        return DatasetDefinition(
            name=self.name,
            category=self.category,
            module="terminal2.forecast",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version=self.version,
        )


FORECAST_DATASET_CONTRACTS = {
    "forecast_product_summary": ForecastDatasetContract(
        name="forecast_product_summary",
        category="intelligence",
        description="Current product-level forecast, regime, risk, and conviction summary.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "forecast_regime",
            "trend_persistence_score",
            "forecast_confidence",
            "conviction_score",
            "conviction_tier",
        ),
    ),
    "forecast_horizons": ForecastDatasetContract(
        name="forecast_horizons",
        category="intelligence",
        description="Forecast price and return ranges by product and horizon.",
        primary_key=("investment_product_id", "horizon_months"),
        required_columns=(
            "investment_product_id",
            "horizon_months",
            "base_forecast_price",
            "bear_forecast_price",
            "bull_forecast_price",
            "expected_return",
            "probability_of_loss",
        ),
    ),
    "forecast_risk": ForecastDatasetContract(
        name="forecast_risk",
        category="intelligence",
        description="Product-level forecast downside, drawdown, uncertainty, and loss risk.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "forecast_volatility",
            "expected_max_drawdown",
            "probability_loss_12m",
            "uncertainty_score",
            "risk_tier",
        ),
    ),
    "forecast_regimes": ForecastDatasetContract(
        name="forecast_regimes",
        category="market",
        description="Product-level market regime and supporting regime indicators.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "forecast_regime",
            "regime_score",
            "momentum_score",
            "market_support_score",
        ),
    ),
    "forecast_rankings": ForecastDatasetContract(
        name="forecast_rankings",
        category="rankings",
        description="Risk-adjusted forecast and conviction ranking across eligible products.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "forecast_rank",
            "conviction_score",
            "risk_adjusted_expected_return",
            "forecast_confidence",
        ),
    ),
    "forecast_market_summary": ForecastDatasetContract(
        name="forecast_market_summary",
        category="executive",
        description="One-row executive summary of forecast regimes and conviction.",
        primary_key=("snapshot_date",),
        required_columns=(
            "snapshot_date",
            "product_count",
            "bullish_product_count",
            "neutral_product_count",
            "bearish_product_count",
            "average_conviction_score",
            "average_forecast_confidence",
        ),
    ),
}


def get_forecast_contract(name: str) -> ForecastDatasetContract:
    try:
        return FORECAST_DATASET_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown forecast dataset contract: {name}") from exc
