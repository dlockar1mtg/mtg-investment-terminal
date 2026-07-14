from __future__ import annotations

from dataclasses import dataclass

from terminal2.warehouse_core import DatasetDefinition


@dataclass(frozen=True)
class SecretLairBackfillContract:
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
            module="terminal2.secret_lair.backfill",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version=self.version,
        )


SECRET_LAIR_BACKFILL_CONTRACTS = {
    "secret_lair_source_catalog": SecretLairBackfillContract(
        name="secret_lair_source_catalog",
        description="Normalized external Secret Lair catalog records before matching.",
        primary_key=("source_name", "source_record_id"),
        required_columns=(
            "source_name",
            "source_record_id",
            "drop_name",
            "variant_name",
            "finish",
        ),
    ),
    "secret_lair_match_results": SecretLairBackfillContract(
        name="secret_lair_match_results",
        description="Source-to-registry matching decisions and confidence evidence.",
        primary_key=("source_name", "source_record_id"),
        required_columns=(
            "source_name",
            "source_record_id",
            "secret_lair_id",
            "match_status",
            "match_method",
            "match_confidence",
        ),
    ),
    "secret_lair_unmatched_review": SecretLairBackfillContract(
        name="secret_lair_unmatched_review",
        description="Ambiguous or incomplete source rows requiring human review.",
        primary_key=("source_name", "source_record_id"),
        required_columns=(
            "source_name",
            "source_record_id",
            "review_reason",
            "best_candidate_id",
            "best_candidate_score",
        ),
        snapshot=False,
    ),
    "secret_lair_backfill_registry": SecretLairBackfillContract(
        name="secret_lair_backfill_registry",
        description="Proposed complete registry after safe source-catalog backfill.",
        primary_key=("secret_lair_id",),
        required_columns=(
            "secret_lair_id",
            "drop_name",
            "variant_name",
            "finish",
            "source_name",
            "source_record_id",
        ),
    ),
    "secret_lair_backfill_prices": SecretLairBackfillContract(
        name="secret_lair_backfill_prices",
        description="Proposed complete price history after matched source-price backfill.",
        primary_key=("observation_date", "secret_lair_id", "source_name"),
        required_columns=(
            "observation_date",
            "secret_lair_id",
            "source_name",
            "market_price",
        ),
    ),
    "secret_lair_backfill_coverage": SecretLairBackfillContract(
        name="secret_lair_backfill_coverage",
        description="Backfill coverage by source, match status, and pricing availability.",
        primary_key=("source_name",),
        required_columns=(
            "source_name",
            "catalog_rows",
            "auto_matched_rows",
            "new_asset_rows",
            "review_rows",
            "priced_rows",
        ),
    ),
    "secret_lair_backfill_summary": SecretLairBackfillContract(
        name="secret_lair_backfill_summary",
        description="Executive one-row summary of Secret Lair backfill readiness.",
        primary_key=("snapshot_date",),
        required_columns=(
            "snapshot_date",
            "catalog_rows",
            "matched_rows",
            "new_asset_rows",
            "review_rows",
            "price_rows",
            "apply_ready",
        ),
    ),
}


def get_secret_lair_backfill_contract(
    name: str,
) -> SecretLairBackfillContract:
    try:
        return SECRET_LAIR_BACKFILL_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown Secret Lair backfill contract: {name}"
        ) from exc
