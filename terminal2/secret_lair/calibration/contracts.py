from __future__ import annotations
from dataclasses import dataclass
from terminal2.warehouse_core import DatasetDefinition

@dataclass(frozen=True)
class CalibrationContract:
    name: str
    description: str
    primary_key: tuple[str,...]
    required_columns: tuple[str,...]
    snapshot: bool=True
    def definition(self):
        return DatasetDefinition(
            name=self.name,
            category="secret_lair",
            module="terminal2.secret_lair.calibration",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version="1",
        )

BASE=("investment_product_id","asset_class","product_name")
CALIBRATION_CONTRACTS={
"secret_lair_calibrated_scores":CalibrationContract(
    "secret_lair_calibrated_scores",
    "Calibrated cross-sectional Secret Lair scores and evidence tiers.",
    ("investment_product_id",),
    BASE+("evidence_tier","calibrated_investment_score","calibrated_risk_adjusted_score","relative_opportunity_percentile","calibration_status"),
),
"secret_lair_calibrated_recommendations":CalibrationContract(
    "secret_lair_calibrated_recommendations",
    "Evidence-aware calibrated Secret Lair recommendations.",
    ("investment_product_id",),
    BASE+("recommendation","recommendation_score","evidence_tier","recommendation_basis","actionability"),
),
"secret_lair_factor_availability":CalibrationContract(
    "secret_lair_factor_availability",
    "Per-product factor availability and missing-input diagnostics.",
    ("investment_product_id","factor_code"),
    BASE+("factor_code","available","availability_reason","importance_weight"),
    False,
),
"secret_lair_score_distribution":CalibrationContract(
    "secret_lair_score_distribution",
    "Score distributions by evidence tier.",
    ("evidence_tier",),
    ("evidence_tier","product_count","priced_count","mean_score","median_score","minimum_score","maximum_score","mean_confidence"),
),
"secret_lair_calibration_summary":CalibrationContract(
    "secret_lair_calibration_summary",
    "Executive summary of calibrated Secret Lair intelligence.",
    ("snapshot_date",),
    ("snapshot_date","product_count","priced_count","historical_count","current_price_only_count","insufficient_count","provisional_watch_count","provisional_hold_count","actionable_buy_count","score_spread","calibration_status"),
),
}

def get_calibration_contract(name):
    try:return CALIBRATION_CONTRACTS[name]
    except KeyError as exc:raise KeyError(f"Unknown calibration contract: {name}") from exc
