from __future__ import annotations

import csv
from pathlib import Path

from terminal2.market_sources.collector_box_evaluation import (
    NATIVE_RANGE,
    OBSERVED_ONLY,
    build_evaluation,
)


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_native_range_replaces_tier_scenarios(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.csv"
    models = tmp_path / "models.csv"

    write_rows(
        ledger,
        [
            "canonical_product_id", "canonical_product_name", "canonical_set_name",
            "admission_tier", "valuation_basis", "confidence",
            "retained_observations", "market_value_usd",
        ],
        [{
            "canonical_product_id": "TCGCSV-22876-489207",
            "canonical_product_name": "Aftermath Collector Booster Display",
            "canonical_set_name": "Aftermath",
            "admission_tier": "FULL_MODEL",
            "valuation_basis": "OBSERVED_GOVERNED",
            "confidence": "HIGH",
            "retained_observations": "5",
            "market_value_usd": "825",
        }],
    )
    write_rows(
        models,
        ["investment_product_id", "current_price", "mc_p05", "mc_median", "mc_p95"],
        [{
            "investment_product_id": "TCGCSV-22876-489207",
            "current_price": "227.18",
            "mc_p05": "261.31",
            "mc_median": "340.58",
            "mc_p95": "444.19",
        }],
    )

    manifest = build_evaluation(ledger, tmp_path / "out", models)
    assert manifest["status"] == "CERTIFIED"

    with Path(manifest["outputs"]["forecasts"]).open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))

    assert row["current_market_value_usd"] == "227.18"
    assert row["forecast_method"] == NATIVE_RANGE
    assert row["native_forecast_base_usd"] == "340.58"
    assert row["1y_base_usd"] == ""
    assert row["3y_base_usd"] == ""
    assert row["5y_base_usd"] == ""


def test_observed_value_without_native_model_is_not_a_forecast(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.csv"
    write_rows(
        ledger,
        [
            "canonical_product_id", "canonical_product_name", "canonical_set_name",
            "admission_tier", "valuation_basis", "confidence",
            "retained_observations", "market_value_usd",
        ],
        [{
            "canonical_product_id": "P1",
            "canonical_product_name": "Observed Product",
            "canonical_set_name": "Set",
            "admission_tier": "FULL_MODEL",
            "valuation_basis": "OBSERVED_GOVERNED",
            "confidence": "HIGH",
            "retained_observations": "5",
            "market_value_usd": "500",
        }],
    )

    manifest = build_evaluation(ledger, tmp_path / "out", tmp_path / "missing.csv")
    with Path(manifest["outputs"]["forecasts"]).open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))

    assert row["forecast_method"] == OBSERVED_ONLY
    assert row["forecast_eligible"] == "NO"
    assert row["1y_base_usd"] == ""
