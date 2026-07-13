from __future__ import annotations

from dataclasses import dataclass

from terminal2.warehouse_core import DatasetDefinition


@dataclass(frozen=True)
class PortfolioDatasetContract:
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
            module="terminal2.portfolio",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version=self.version,
        )


PORTFOLIO_DATASET_CONTRACTS = {
    "portfolio_positions": PortfolioDatasetContract(
        name="portfolio_positions",
        category="portfolio",
        description="Current owned positions enriched with market and investment intelligence.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "quantity",
            "current_price",
            "current_value",
            "portfolio_weight",
        ),
    ),
    "portfolio_allocation": PortfolioDatasetContract(
        name="portfolio_allocation",
        category="portfolio",
        description="Current portfolio allocation by sealed-product asset group.",
        primary_key=("asset_group",),
        required_columns=(
            "asset_group",
            "position_count",
            "current_value",
            "portfolio_weight",
        ),
    ),
    "portfolio_risk_exposure": PortfolioDatasetContract(
        name="portfolio_risk_exposure",
        category="portfolio",
        description="Portfolio concentration, downside, volatility, and confidence exposures.",
        primary_key=("risk_metric",),
        required_columns=(
            "risk_metric",
            "metric_value",
            "risk_level",
        ),
    ),
    "portfolio_recommendations": PortfolioDatasetContract(
        name="portfolio_recommendations",
        category="portfolio",
        description="Position-level hold, add, trim, avoid, and candidate recommendations.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "recommendation",
            "recommendation_score",
            "target_weight",
            "recommended_dollar_amount",
        ),
    ),
    "portfolio_candidate_allocation": PortfolioDatasetContract(
        name="portfolio_candidate_allocation",
        category="portfolio",
        description="Model portfolio allocation across the strongest eligible products.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "allocation_rank",
            "target_weight",
            "recommended_dollar_amount",
            "conviction_score",
        ),
    ),
    "portfolio_scenarios": PortfolioDatasetContract(
        name="portfolio_scenarios",
        category="portfolio",
        description="Portfolio value under downside, base, upside, and five-year model scenarios.",
        primary_key=("scenario_name",),
        required_columns=(
            "scenario_name",
            "scenario_value",
            "change_amount",
            "change_pct",
        ),
    ),
    "portfolio_summary": PortfolioDatasetContract(
        name="portfolio_summary",
        category="executive",
        description="One-row executive summary of current portfolio health and model allocation.",
        primary_key=("snapshot_date",),
        required_columns=(
            "snapshot_date",
            "position_count",
            "current_value",
            "portfolio_health_score",
            "concentration_score",
            "model_portfolio_capital",
        ),
    ),
}


def get_portfolio_contract(name: str) -> PortfolioDatasetContract:
    try:
        return PORTFOLIO_DATASET_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown portfolio dataset contract: {name}") from exc
