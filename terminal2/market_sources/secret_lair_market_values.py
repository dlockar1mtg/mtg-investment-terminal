from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SecretLairMarketValue:
    canonical_product_id: str
    canonical_product_name: str
    market_value_usd: float
    currency: str
    observation_count: int
    seller_count: int
    confidence_score: float
    confidence_state: str
    sample_state: str
    source: str
    valuation_method: str


class SecretLairMarketValueStore:
    """Read-only model-facing interface for admitted Secret Lair values."""

    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)

    def load(self) -> list[SecretLairMarketValue]:
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        values = [self._parse(row) for row in rows]
        self._validate(values)
        return values

    def by_product_id(self) -> dict[str, SecretLairMarketValue]:
        return {value.canonical_product_id: value for value in self.load()}

    @staticmethod
    def _parse(row: dict[str, str]) -> SecretLairMarketValue:
        return SecretLairMarketValue(
            canonical_product_id=row["canonical_product_id"],
            canonical_product_name=row["canonical_product_name"],
            market_value_usd=float(row["market_value_usd"]),
            currency=row["currency"],
            observation_count=int(row["observation_count"]),
            seller_count=int(row["seller_count"]),
            confidence_score=float(row["confidence_score"]),
            confidence_state=row["confidence_state"],
            sample_state=row["sample_state"],
            source=row["source"],
            valuation_method=row["valuation_method"],
        )

    @staticmethod
    def _validate(values: Iterable[SecretLairMarketValue]) -> None:
        items = list(values)
        ids = [item.canonical_product_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate canonical product IDs in model-facing values")
        for item in items:
            if item.market_value_usd <= 0:
                raise ValueError(f"Non-positive market value for {item.canonical_product_id}")
            if item.currency != "USD":
                raise ValueError(f"Unsupported currency for {item.canonical_product_id}: {item.currency}")
            if item.observation_count <= 0 or item.seller_count <= 0:
                raise ValueError(f"Invalid evidence counts for {item.canonical_product_id}")
