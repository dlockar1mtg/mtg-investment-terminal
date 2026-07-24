from __future__ import annotations

import csv
from pathlib import Path

from terminal2.market_sources.secret_lair_market_values import SecretLairMarketValueStore


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def base_row(product_id: str = "A") -> dict[str, str]:
    return {
        "canonical_product_id": product_id,
        "canonical_product_name": product_id,
        "market_value_usd": "50.0",
        "currency": "USD",
        "observation_count": "3",
        "seller_count": "3",
        "confidence_score": "80",
        "confidence_state": "HIGH",
        "sample_state": "MODERATE_EVIDENCE",
        "price_dispersion_cv": "0.1",
        "market_value_low": "45",
        "market_value_high": "55",
        "source": "EBAY_CERTIFIED_SECRET_LAIR",
        "valuation_method": "MEDIAN_ACCEPTED_ACTIVE_LISTINGS_IQR_FILTERED",
        "model_input_status": "ACTIVE",
    }


def test_store_loads_model_values(tmp_path: Path):
    path = tmp_path / "values.csv"
    write_rows(path, [base_row()])
    values = SecretLairMarketValueStore(path).load()
    assert len(values) == 1
    assert values[0].market_value_usd == 50.0


def test_store_indexes_by_product_id(tmp_path: Path):
    path = tmp_path / "values.csv"
    write_rows(path, [base_row("A"), base_row("B")])
    values = SecretLairMarketValueStore(path).by_product_id()
    assert set(values) == {"A", "B"}


def test_store_rejects_duplicate_ids(tmp_path: Path):
    path = tmp_path / "values.csv"
    write_rows(path, [base_row("A"), base_row("A")])
    try:
        SecretLairMarketValueStore(path).load()
    except ValueError as error:
        assert "Duplicate canonical product IDs" in str(error)
    else:
        raise AssertionError("Expected duplicate IDs to fail")


def test_store_rejects_non_positive_values(tmp_path: Path):
    path = tmp_path / "values.csv"
    bad = base_row()
    bad["market_value_usd"] = "0"
    write_rows(path, [bad])
    try:
        SecretLairMarketValueStore(path).load()
    except ValueError as error:
        assert "Non-positive market value" in str(error)
    else:
        raise AssertionError("Expected non-positive value to fail")
