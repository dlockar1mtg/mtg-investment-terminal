from __future__ import annotations

from dataclasses import dataclass

from terminal2.warehouse_core import DatasetDefinition


@dataclass(frozen=True)
class IntelligenceDatasetContract:
    name: str
    description: str
    primary_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    snapshot: bool = True
    version: str = "1"

    def definition(self) -> DatasetDefinition:
        return DatasetDefinition(
            name=self.name,
            category="intelligence",
            module="terminal2.intelligence",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version=self.version,
        )


INTELLIGENCE_DATASET_CONTRACTS = {
    "intelligence_risk_assessment": IntelligenceDatasetContract(
        name="intelligence_risk_assessment",
        description="Product-level decomposed investment risk assessment.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "overall_risk_score",
            "risk_rating",
            "volatility_risk",
            "liquidity_risk",
            "drawdown_risk",
            "data_risk",
            "forecast_risk",
        ),
    ),
    "intelligence_confidence_assessment": IntelligenceDatasetContract(
        name="intelligence_confidence_assessment",
        description="Evidence-strength assessment supporting each recommendation.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "overall_confidence_score",
            "confidence_rating",
            "history_depth_score",
            "observation_score",
            "forecast_confidence_score",
            "market_confidence_score",
            "model_coverage_score",
        ),
    ),
    "intelligence_recommendations": IntelligenceDatasetContract(
        name="intelligence_recommendations",
        description="Core investment recommendation, expected return, risk, and confidence.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "recommendation",
            "recommendation_score",
            "overall_confidence_score",
            "overall_risk_score",
            "forecast_expected_cagr",
            "conviction_score",
        ),
    ),
    "intelligence_recommendation_factors": IntelligenceDatasetContract(
        name="intelligence_recommendation_factors",
        description="Long-form positive, risk, and evidence factors by product.",
        primary_key=("investment_product_id", "factor_code"),
        required_columns=(
            "investment_product_id",
            "factor_code",
            "factor_group",
            "factor_label",
            "factor_value",
            "factor_score",
            "factor_direction",
        ),
        snapshot=False,
    ),
    "intelligence_recommendation_explanations": IntelligenceDatasetContract(
        name="intelligence_recommendation_explanations",
        description="Human-readable recommendation reasoning and risk summary.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "recommendation",
            "recommendation_summary",
            "positive_drivers",
            "risk_factors",
            "evidence_summary",
        ),
    ),
    "intelligence_model_coverage": IntelligenceDatasetContract(
        name="intelligence_model_coverage",
        description="Availability and completeness of source models used in Phase 1.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "historical_model_available",
            "market_model_available",
            "forecast_model_available",
            "pricing_available",
            "available_model_count",
            "model_coverage_score",
            "coverage_status",
        ),
    ),
    "intelligence_executive_buy_list": IntelligenceDatasetContract(
        name="intelligence_executive_buy_list",
        description="Executive ranked list of the strongest actionable opportunities.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "buy_list_rank",
            "recommendation",
            "recommendation_score",
            "overall_confidence_score",
            "overall_risk_score",
            "forecast_expected_cagr",
        ),
    ),
}


def get_intelligence_contract(
    name: str,
) -> IntelligenceDatasetContract:
    try:
        return INTELLIGENCE_DATASET_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown intelligence dataset contract: {name}"
        ) from exc
