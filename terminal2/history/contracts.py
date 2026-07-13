from __future__ import annotations

from dataclasses import dataclass

from terminal2.warehouse_core import DatasetDefinition


@dataclass(frozen=True)
class HistoricalDatasetContract:
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
            module="terminal2.history",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version=self.version,
        )


HISTORICAL_DATASET_CONTRACTS = {
    "historical_prices": HistoricalDatasetContract(
        name="historical_prices",
        category="products",
        description="Canonical product-level historical sealed-price observations.",
        primary_key=(
            "observation_date",
            "investment_product_id",
            "price_source",
        ),
        required_columns=(
            "observation_date",
            "investment_product_id",
            "price_source",
            "market_price",
        ),
    ),
    "monthly_price_history": HistoricalDatasetContract(
        name="monthly_price_history",
        category="seasonality",
        description="Latest valid product price for each calendar month and source.",
        primary_key=(
            "year_month",
            "investment_product_id",
            "price_source",
        ),
        required_columns=(
            "year_month",
            "observation_date",
            "investment_product_id",
            "price_source",
            "market_price",
        ),
    ),
    "historical_returns": HistoricalDatasetContract(
        name="historical_returns",
        category="seasonality",
        description="Sequential monthly returns by product and price source.",
        primary_key=(
            "year_month",
            "investment_product_id",
            "price_source",
        ),
        required_columns=(
            "year_month",
            "investment_product_id",
            "price_source",
            "market_price",
            "monthly_return",
        ),
    ),
    "historical_price_features": HistoricalDatasetContract(
        name="historical_price_features",
        category="intelligence",
        description="Current historical trend, return, volatility, and drawdown features.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "latest_price",
            "observation_count",
            "first_observation_date",
            "latest_observation_date",
            "history_confidence",
        ),
    ),
    "historical_coverage": HistoricalDatasetContract(
        name="historical_coverage",
        category="metadata",
        description="Historical observation coverage and quality by product.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "observation_count",
            "first_observation_date",
            "latest_observation_date",
            "history_span_days",
            "source_count",
            "coverage_status",
        ),
    ),
    "historical_source_quality": HistoricalDatasetContract(
        name="historical_source_quality",
        category="metadata",
        description="Historical coverage and quality summary by price source.",
        primary_key=("price_source",),
        required_columns=(
            "price_source",
            "observation_count",
            "product_count",
            "first_observation_date",
            "latest_observation_date",
            "average_price_data_quality",
        ),
    ),
    "historical_summary": HistoricalDatasetContract(
        name="historical_summary",
        category="executive",
        description="One-row executive summary of historical price coverage.",
        primary_key=("snapshot_date",),
        required_columns=(
            "snapshot_date",
            "observation_count",
            "product_count",
            "source_count",
            "first_observation_date",
            "latest_observation_date",
        ),
    ),
}


def get_historical_contract(name: str) -> HistoricalDatasetContract:
    try:
        return HISTORICAL_DATASET_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown historical dataset contract: {name}") from exc


def required_historical_dataset_names() -> tuple[str, ...]:
    return tuple(sorted(HISTORICAL_DATASET_CONTRACTS))
