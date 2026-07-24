from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FullSecretLairEvaluation:
    investment_product_id: str
    product_name: str
    evaluation_tier: str
    evaluated_market_value_usd: float
    model_confidence_score: float
    model_weight: float
    forecast_low_usd: float
    forecast_base_usd: float
    forecast_high_usd: float
    guarded_recommendation: str


class FullSecretLairEvaluationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[FullSecretLairEvaluation]:
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        values = [FullSecretLairEvaluation(
            investment_product_id=row["investment_product_id"],
            product_name=row["canonical_product_name"],
            evaluation_tier=row["evaluation_tier"],
            evaluated_market_value_usd=float(row["evaluated_market_value_usd"]),
            model_confidence_score=float(row["model_confidence_score"]),
            model_weight=float(row["model_weight"]),
            forecast_low_usd=float(row["forecast_low_usd"]),
            forecast_base_usd=float(row["forecast_base_usd"]),
            forecast_high_usd=float(row["forecast_high_usd"]),
            guarded_recommendation=row["guarded_recommendation"],
        ) for row in rows]
        ids = [item.investment_product_id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate Secret Lair evaluation IDs")
        if any(item.evaluated_market_value_usd <= 0 for item in values):
            raise ValueError("All evaluated values must be positive")
        return values

    def by_product_id(self) -> dict[str, FullSecretLairEvaluation]:
        return {item.investment_product_id: item for item in self.load()}

    def by_tier(self, tier: str) -> list[FullSecretLairEvaluation]:
        return [item for item in self.load() if item.evaluation_tier == tier]
