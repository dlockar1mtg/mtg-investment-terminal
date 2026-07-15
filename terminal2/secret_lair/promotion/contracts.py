from __future__ import annotations
from dataclasses import dataclass
from terminal2.warehouse_core import DatasetDefinition

@dataclass(frozen=True)
class PromotionContract:
    name: str
    description: str
    primary_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    snapshot: bool = True

    def definition(self) -> DatasetDefinition:
        return DatasetDefinition(
            name=self.name,
            category="secret_lair",
            module="terminal2.secret_lair.promotion",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version="1",
        )

PROMOTION_CONTRACTS = {
    "secret_lair_promotion_candidates": PromotionContract(
        "secret_lair_promotion_candidates",
        "Products eligible for guarded production promotion.",
        ("secret_lair_id",),
        ("secret_lair_id","drop_name","variant_name","finish","source_confidence","promotion_eligibility","promotion_reason"),
    ),
    "secret_lair_promotion_rejections": PromotionContract(
        "secret_lair_promotion_rejections",
        "Products excluded from promotion and their blocking reasons.",
        ("secret_lair_id","rejection_code"),
        ("secret_lair_id","product_name","rejection_code","rejection_reason","source_confidence"),
    ),
    "secret_lair_promotion_prices": PromotionContract(
        "secret_lair_promotion_prices",
        "Price observations eligible for production promotion.",
        ("observation_date","secret_lair_id","source_name"),
        ("observation_date","secret_lair_id","source_name","market_price","price_eligibility","price_reason"),
        False,
    ),
    "secret_lair_promotion_review_remaining": PromotionContract(
        "secret_lair_promotion_review_remaining",
        "Master database review records retained after promotion.",
        ("review_id",),
        ("review_id","review_type","severity","product_name","message"),
    ),
    "secret_lair_promotion_log": PromotionContract(
        "secret_lair_promotion_log",
        "Permanent audit log of preview and applied promotion runs.",
        ("promotion_run_id",),
        ("promotion_run_id","promotion_timestamp_utc","mode","minimum_confidence","candidate_count","promoted_registry_rows","promoted_price_rows","rejected_count","review_remaining_count","status"),
        False,
    ),
    "secret_lair_promotion_summary": PromotionContract(
        "secret_lair_promotion_summary",
        "Executive production promotion status and readiness summary.",
        ("snapshot_date",),
        ("snapshot_date","master_product_count","eligible_product_count","rejected_product_count","review_remaining_count","eligible_price_count","production_registry_count","production_price_count","apply_ready","last_apply_status"),
    ),
    "secret_lair_registry_health": PromotionContract(
        "secret_lair_registry_health",
        "Post-promotion registry integrity and downstream readiness metrics.",
        ("snapshot_date",),
        ("snapshot_date","registry_product_count","unique_registry_id_count","duplicate_registry_id_count","valid_finish_count","invalid_finish_count","priced_product_count","orphan_price_count","current_price_coverage","integrity_status"),
    ),
}

def get_promotion_contract(name: str) -> PromotionContract:
    try:
        return PROMOTION_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown promotion contract: {name}") from exc
