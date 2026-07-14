from __future__ import annotations

from dataclasses import dataclass

from terminal2.warehouse_core import DatasetDefinition


@dataclass(frozen=True)
class SecretLairPricingContract:
    name: str
    description: str
    primary_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    snapshot: bool = True
    version: str = "1"

    def definition(self) -> DatasetDefinition:
        return DatasetDefinition(
            name=self.name,
            category="secret_lair",
            module="terminal2.secret_lair.pricing",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version=self.version,
        )


SECRET_LAIR_PRICING_CONTRACTS = {
    "secret_lair_price_observations": SecretLairPricingContract(
        name="secret_lair_price_observations",
        description="Canonical curated Secret Lair market-price observations.",
        primary_key=(
            "observation_date",
            "secret_lair_id",
            "source_name",
        ),
        required_columns=(
            "observation_date",
            "secret_lair_id",
            "source_name",
            "market_price",
            "currency",
        ),
    ),
    "secret_lair_current_prices": SecretLairPricingContract(
        name="secret_lair_current_prices",
        description="Latest valid price and MSRP premium for each Secret Lair asset.",
        primary_key=("secret_lair_id",),
        required_columns=(
            "secret_lair_id",
            "observation_date",
            "market_price",
            "msrp_usd",
            "premium_to_msrp",
            "price_age_days",
        ),
    ),
    "secret_lair_monthly_prices": SecretLairPricingContract(
        name="secret_lair_monthly_prices",
        description="Latest Secret Lair price by asset, source, and calendar month.",
        primary_key=(
            "year_month",
            "secret_lair_id",
            "source_name",
        ),
        required_columns=(
            "year_month",
            "observation_date",
            "secret_lair_id",
            "source_name",
            "market_price",
        ),
    ),
    "secret_lair_returns": SecretLairPricingContract(
        name="secret_lair_returns",
        description="Secret Lair appreciation, CAGR, drawdown, and horizon returns.",
        primary_key=("secret_lair_id",),
        required_columns=(
            "secret_lair_id",
            "current_price",
            "inception_return",
            "annualized_return",
            "drawdown_from_peak",
        ),
    ),
    "secret_lair_price_coverage": SecretLairPricingContract(
        name="secret_lair_price_coverage",
        description="Historical pricing coverage and freshness by Secret Lair asset.",
        primary_key=("secret_lair_id",),
        required_columns=(
            "secret_lair_id",
            "observation_count",
            "source_count",
            "first_observation_date",
            "latest_observation_date",
            "coverage_status",
        ),
    ),
    "secret_lair_price_quality": SecretLairPricingContract(
        name="secret_lair_price_quality",
        description="Row-level Secret Lair price-data quality findings.",
        primary_key=("validation_id",),
        required_columns=(
            "validation_id",
            "secret_lair_id",
            "severity",
            "rule_name",
            "message",
        ),
        snapshot=False,
    ),
    "secret_lair_market_summary": SecretLairPricingContract(
        name="secret_lair_market_summary",
        description="Executive Secret Lair pricing and coverage summary.",
        primary_key=("snapshot_date",),
        required_columns=(
            "snapshot_date",
            "priced_asset_count",
            "observation_count",
            "source_count",
            "average_market_price",
            "average_premium_to_msrp",
        ),
    ),
}


def get_secret_lair_pricing_contract(
    name: str,
) -> SecretLairPricingContract:
    try:
        return SECRET_LAIR_PRICING_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown Secret Lair pricing contract: {name}"
        ) from exc
