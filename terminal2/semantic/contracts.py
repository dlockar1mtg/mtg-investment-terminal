from __future__ import annotations

from dataclasses import dataclass

from terminal2.warehouse_core import DatasetDefinition


@dataclass(frozen=True)
class SemanticDatasetContract:
    name: str
    description: str
    primary_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    snapshot: bool = True
    version: str = "1"

    def definition(self) -> DatasetDefinition:
        return DatasetDefinition(
            name=self.name,
            category="semantic",
            module="terminal2.semantic",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version=self.version,
        )


SEMANTIC_DATASET_CONTRACTS = {
    "semantic_dim_product": SemanticDatasetContract(
        name="semantic_dim_product",
        description="Conformed Power BI product dimension with stable ProductKey.",
        primary_key=("ProductKey",),
        required_columns=(
            "ProductKey",
            "investment_product_id",
            "box_name",
            "set_name",
            "product_type",
        ),
    ),
    "semantic_dim_date": SemanticDatasetContract(
        name="semantic_dim_date",
        description="Conformed calendar dimension used by historical and snapshot facts.",
        primary_key=("DateKey",),
        required_columns=(
            "DateKey",
            "Date",
            "Year",
            "Quarter",
            "MonthNumber",
            "MonthName",
        ),
    ),
    "semantic_fact_product_snapshot": SemanticDatasetContract(
        name="semantic_fact_product_snapshot",
        description="One current semantic snapshot row per approved investment product.",
        primary_key=("ProductKey",),
        required_columns=(
            "ProductKey",
            "investment_product_id",
            "SnapshotDateKey",
            "current_price",
            "investment_score",
            "risk_adjusted_score",
            "conviction_score",
        ),
    ),
    "semantic_fact_price_history": SemanticDatasetContract(
        name="semantic_fact_price_history",
        description="Power BI-ready historical price fact keyed by product, date, and source.",
        primary_key=("ProductKey", "DateKey", "price_source"),
        required_columns=(
            "ProductKey",
            "DateKey",
            "price_source",
            "market_price",
        ),
    ),
    "semantic_fact_forecast": SemanticDatasetContract(
        name="semantic_fact_forecast",
        description="Multi-horizon product forecast fact for dashboard scenarios.",
        primary_key=("ProductKey", "horizon_months"),
        required_columns=(
            "ProductKey",
            "horizon_months",
            "base_forecast_price",
            "bear_forecast_price",
            "bull_forecast_price",
            "expected_return",
            "probability_of_loss",
        ),
    ),
    "semantic_fact_portfolio": SemanticDatasetContract(
        name="semantic_fact_portfolio",
        description="Actual portfolio position fact; may be empty until holdings are entered.",
        primary_key=("ProductKey",),
        required_columns=(
            "ProductKey",
            "quantity",
            "current_price",
            "current_value",
            "portfolio_weight",
        ),
    ),
    "semantic_executive_kpis": SemanticDatasetContract(
        name="semantic_executive_kpis",
        description="Long-form executive KPI contract and current KPI values.",
        primary_key=("SnapshotDateKey", "KPIName"),
        required_columns=(
            "SnapshotDateKey",
            "KPIName",
            "KPIValue",
            "DisplayFormat",
            "KPIGroup",
        ),
    ),
    "semantic_refresh_status": SemanticDatasetContract(
        name="semantic_refresh_status",
        description="Dataset publication and refresh status for operational monitoring.",
        primary_key=("DatasetName",),
        required_columns=(
            "DatasetName",
            "Category",
            "PublishedAtUTC",
            "RowCount",
            "Status",
            "IsCurrent",
        ),
        snapshot=False,
    ),
    "semantic_relationship_map": SemanticDatasetContract(
        name="semantic_relationship_map",
        description="Recommended Power BI relationships and filter directions.",
        primary_key=("RelationshipName",),
        required_columns=(
            "RelationshipName",
            "FromTable",
            "FromColumn",
            "ToTable",
            "ToColumn",
            "Cardinality",
            "CrossFilterDirection",
        ),
        snapshot=False,
    ),
    "semantic_measure_catalog": SemanticDatasetContract(
        name="semantic_measure_catalog",
        description="Recommended Power BI DAX measure catalog and business definitions.",
        primary_key=("MeasureName",),
        required_columns=(
            "MeasureName",
            "HomeTable",
            "DAXExpression",
            "DisplayFormat",
            "MeasureGroup",
            "BusinessDefinition",
        ),
        snapshot=False,
    ),
    "semantic_field_dictionary": SemanticDatasetContract(
        name="semantic_field_dictionary",
        description="Generated semantic table and field documentation for Power BI authors.",
        primary_key=("DatasetName", "FieldName"),
        required_columns=(
            "DatasetName",
            "FieldName",
            "DataType",
            "IsKey",
            "Nullable",
            "BusinessDescription",
        ),
        snapshot=False,
    ),
}


def get_semantic_contract(name: str) -> SemanticDatasetContract:
    try:
        return SEMANTIC_DATASET_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown semantic dataset contract: {name}") from exc
