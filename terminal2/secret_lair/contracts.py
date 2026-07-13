from __future__ import annotations

from dataclasses import dataclass

from terminal2.warehouse_core import DatasetDefinition


@dataclass(frozen=True)
class SecretLairDatasetContract:
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
            module="terminal2.secret_lair",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version=self.version,
        )


SECRET_LAIR_DATASET_CONTRACTS = {
    "secret_lair_registry": SecretLairDatasetContract(
        name="secret_lair_registry",
        description="Canonical curated Secret Lair investment-asset registry.",
        primary_key=("secret_lair_id",),
        required_columns=(
            "secret_lair_id",
            "drop_name",
            "variant_name",
            "finish",
            "release_date",
            "msrp_usd",
            "franchise",
            "status",
        ),
    ),
    "secret_lair_variants": SecretLairDatasetContract(
        name="secret_lair_variants",
        description="One row per Secret Lair drop variant and finish.",
        primary_key=("secret_lair_id",),
        required_columns=(
            "secret_lair_id",
            "drop_name",
            "variant_name",
            "finish",
            "product_family",
            "msrp_usd",
        ),
    ),
    "secret_lair_release_calendar": SecretLairDatasetContract(
        name="secret_lair_release_calendar",
        description="Release, sale-window, year, quarter, and event metadata.",
        primary_key=("secret_lair_id",),
        required_columns=(
            "secret_lair_id",
            "release_date",
            "release_year",
            "release_quarter",
            "release_month",
            "event_type",
        ),
    ),
    "secret_lair_ip_catalog": SecretLairDatasetContract(
        name="secret_lair_ip_catalog",
        description="Distinct Secret Lair franchise and IP classifications.",
        primary_key=("ip_key",),
        required_columns=(
            "ip_key",
            "franchise",
            "ip_category",
            "universes_beyond",
            "asset_count",
        ),
    ),
    "secret_lair_artist_catalog": SecretLairDatasetContract(
        name="secret_lair_artist_catalog",
        description="Distinct artist-to-Secret-Lair asset catalog.",
        primary_key=("artist_key", "secret_lair_id"),
        required_columns=(
            "artist_key",
            "artist_name",
            "secret_lair_id",
            "drop_name",
        ),
    ),
    "secret_lair_data_quality": SecretLairDatasetContract(
        name="secret_lair_data_quality",
        description="Row-level Secret Lair registry validation findings.",
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
    "secret_lair_summary": SecretLairDatasetContract(
        name="secret_lair_summary",
        description="Executive Secret Lair registry coverage summary.",
        primary_key=("snapshot_date",),
        required_columns=(
            "snapshot_date",
            "asset_count",
            "drop_count",
            "foil_asset_count",
            "nonfoil_asset_count",
            "franchise_count",
            "artist_count",
        ),
    ),
}


def get_secret_lair_contract(name: str) -> SecretLairDatasetContract:
    try:
        return SECRET_LAIR_DATASET_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown Secret Lair dataset contract: {name}"
        ) from exc
