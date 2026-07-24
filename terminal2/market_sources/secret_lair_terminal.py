from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SecretLairTerminalValue:
    investment_product_id: str
    product_name: str
    current_price: float
    confidence_score: float
    forecast_eligible: bool
    recommendation_eligible: bool


class SecretLairTerminalValueStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[SecretLairTerminalValue]:
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        values = [SecretLairTerminalValue(
            investment_product_id=row["investment_product_id"],
            product_name=row["product_name"],
            current_price=float(row["current_price"]),
            confidence_score=float(row["confidence_score"]),
            forecast_eligible=row["forecast_input_status"] == "ELIGIBLE",
            recommendation_eligible=row["recommendation_input_status"] == "ELIGIBLE",
        ) for row in rows]
        ids = [value.investment_product_id for value in values]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate Secret Lair investment_product_id values")
        if any(value.current_price <= 0 for value in values):
            raise ValueError("Secret Lair terminal values must be positive")
        return values

    def by_product_id(self) -> dict[str, SecretLairTerminalValue]:
        return {value.investment_product_id: value for value in self.load()}
