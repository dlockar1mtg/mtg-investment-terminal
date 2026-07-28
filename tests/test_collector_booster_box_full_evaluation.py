from __future__ import annotations

import csv
from pathlib import Path

from terminal2.market_sources.collector_box_evaluation import build_evaluation


def _write_ledger(path: Path) -> None:
    fieldnames = [
        "canonical_product_id",
        "canonical_product_name",
        "canonical_set_name",
        "admission_tier",
        "valuation_basis",
        "confidence",
        "retained_observations",
        "market_value_usd",
    ]
    rows = []
    for index in range(49):
        if index < 36:
            tier, basis, confidence, value = "FULL_MODEL", "OBSERVED_GOVERNED", "HIGH", "500"
        elif index < 47:
            tier, basis, confidence, value = "PROVISIONAL_MODEL", "OBSERVED_LIMITED", "MEDIUM", "400"
        else:
            tier, basis, confidence, value = "STRUCTURAL_ONLY", "NO_ACCEPTED_OBSERVATION", "STRUCTURAL", ""
        rows.append(
            {
                "canonical_product_id": f"P{index}",
                "canonical_product_name": f"Product {index}",
                "canonical_set_name": f"Set {index}",
                "admission_tier": tier,
                "valuation_basis": basis,
                "confidence": confidence,
                "retained_observations": "5" if value else "0",
                "market_value_usd": value,
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_full_evaluation_certifies(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.csv"
    _write_ledger(ledger)
    manifest = build_evaluation(ledger, tmp_path / "out")
    assert manifest["status"] == "CERTIFIED"
    assert manifest["products"] == 49
    # Synthetic IDs do not join to production Monte Carlo models.
    assert manifest["native_range_products"] == 0
    assert manifest["observed_value_only_products"] == 47
    assert manifest["suppressed_products"] == 2
    assert manifest["certified_horizon_products"] == 0
    assert manifest["recommendation_eligible_products"] == 0


def test_structural_rows_are_suppressed(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.csv"
    _write_ledger(ledger)
    manifest = build_evaluation(ledger, tmp_path / "out")
    with Path(manifest["outputs"]["forecasts"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    structural = [row for row in rows if row["admission_tier"] == "STRUCTURAL_ONLY"]
    assert len(structural) == 2
    assert all(row["forecast_eligible"] == "NO" for row in structural)
    assert all(row["1y_base_usd"] == "" for row in structural)


def test_no_directional_trade_actions(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.csv"
    _write_ledger(ledger)
    manifest = build_evaluation(ledger, tmp_path / "out")
    with Path(manifest["outputs"]["recommendations"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert all(row["action"] not in {"BUY", "SELL"} for row in rows)
