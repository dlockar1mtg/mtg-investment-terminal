from __future__ import annotations

from dataclasses import dataclass

from terminal2.warehouse_core import DatasetDefinition


@dataclass(frozen=True)
class MarketDatasetContract:
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
            module="terminal2.market",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version=self.version,
        )


MARKET_DATASET_CONTRACTS = {
    "market_intelligence": MarketDatasetContract(
        name="market_intelligence",
        category="market",
        description="Current product-level sealed-market intelligence scores.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "market_intelligence_score",
            "market_intelligence_confidence",
        ),
    ),
    "market_signals": MarketDatasetContract(
        name="market_signals",
        category="market",
        description="Interpreted product-level market signals and reasons.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "market_signal",
            "signal_reason",
        ),
    ),
    "market_health": MarketDatasetContract(
        name="market_health",
        category="market",
        description="Historical sealed-market health measurements.",
        primary_key=("snapshot_date",),
        required_columns=("snapshot_date",),
    ),
    "source_health": MarketDatasetContract(
        name="source_health",
        category="market",
        description="Historical health and coverage by market data source.",
        primary_key=("snapshot_date", "source_name"),
        required_columns=(
            "snapshot_date",
            "source_name",
            "source_health_score",
            "status",
        ),
    ),
    "supply_metrics": MarketDatasetContract(
        name="supply_metrics",
        category="market",
        description="Observed sealed-product supply and inventory metrics.",
        primary_key=(
            "observation_date",
            "investment_product_id",
            "source_name",
        ),
        required_columns=(
            "observation_date",
            "investment_product_id",
            "source_name",
        ),
    ),
    "liquidity": MarketDatasetContract(
        name="liquidity",
        category="market",
        description="Observed sales and liquidity metrics.",
        primary_key=(
            "observation_date",
            "investment_product_id",
            "source_name",
        ),
        required_columns=(
            "observation_date",
            "investment_product_id",
            "source_name",
        ),
    ),
    "market_alerts": MarketDatasetContract(
        name="market_alerts",
        category="alerts",
        description="Current actionable market intelligence alerts.",
        primary_key=(
            "investment_product_id",
            "alert_type",
            "generated_at_utc",
        ),
        required_columns=(
            "investment_product_id",
            "alert_type",
            "severity",
            "generated_at_utc",
        ),
    ),
    "market_health_summary": MarketDatasetContract(
        name="market_health_summary",
        category="executive",
        description="Latest one-row executive market-health summary.",
        primary_key=("snapshot_date",),
        required_columns=("snapshot_date",),
    ),
    "current_market_intelligence": MarketDatasetContract(
        name="current_market_intelligence",
        category="intelligence",
        description="Current analytics-facing market intelligence dataset.",
        primary_key=("investment_product_id",),
        required_columns=(
            "investment_product_id",
            "market_intelligence_score",
        ),
        snapshot=False,
    ),
    "current_market_health": MarketDatasetContract(
        name="current_market_health",
        category="executive",
        description="Current analytics-facing market-health record.",
        primary_key=("snapshot_date",),
        required_columns=("snapshot_date",),
        snapshot=False,
    ),
}


def get_market_contract(name: str) -> MarketDatasetContract:
    try:
        return MARKET_DATASET_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown market dataset contract: {name}") from exc


def required_market_dataset_names() -> tuple[str, ...]:
    return tuple(sorted(MARKET_DATASET_CONTRACTS))
