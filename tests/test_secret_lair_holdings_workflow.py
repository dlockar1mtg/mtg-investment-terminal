from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.manage_secret_lair_holdings import build_lookup, certify_holdings, create_template, normalize_import, search_lookup
from scripts.refresh_secret_lair_portfolio import refresh


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def _valuation_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    values = tmp_path / "model.csv"
    rows = []
    for index in range(214):
        rows.append({
            "canonical_product_id": f"SL-{index:04d}", "canonical_product_name": f"Product {index}",
            "market_value_usd": 20 + index, "currency": "USD", "observation_count": 4,
            "seller_count": 4, "confidence_score": 70, "confidence_state": "MEDIUM",
            "model_input_status": "ACTIVE",
        })
    _write(values, rows)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"status":"CERTIFIED","products":973,"admitted_products":214,"source_audit_sha256":"abc"}), encoding="utf-8")
    terminal_universe = tmp_path / "terminal.csv"
    terminal_rows = [{
        "investment_product_id": row["canonical_product_id"], "product_name": row["canonical_product_name"],
        "current_price": row["market_value_usd"], "confidence_score": 70, "confidence_state": "MEDIUM",
        "forecast_input_status": "ELIGIBLE", "recommendation_input_status": "ELIGIBLE",
    } for row in rows]
    _write(terminal_universe, terminal_rows)
    return values, manifest, terminal_universe


def test_template_and_lookup(tmp_path: Path):
    _, _, terminal = _valuation_fixture(tmp_path)
    template = create_template(tmp_path / "holdings.csv")
    assert template.exists()
    lookup = build_lookup(terminal, tmp_path / "lookup.csv")
    assert len(search_lookup(lookup, "Product 1")) > 0


def test_import_consolidates_duplicates(tmp_path: Path):
    _, _, terminal = _valuation_fixture(tmp_path)
    lookup = build_lookup(terminal, tmp_path / "lookup.csv")
    source = tmp_path / "source.csv"
    _write(source, [
        {"investment_product_id":"SL-0001","quantity":1,"acquisition_cost_total":20,"acquisition_date":"2025-01-01","notes":"a"},
        {"investment_product_id":"SL-0001","quantity":2,"acquisition_cost_total":40,"acquisition_date":"2025-02-01","notes":"b"},
    ])
    result = normalize_import(source, lookup, tmp_path / "normalized.csv", tmp_path / "diag.csv")
    assert result["status"] == "CERTIFIED"
    assert result["normalized_rows"] == 1
    assert result["total_quantity"] == 3


def test_import_flags_unknown_and_invalid(tmp_path: Path):
    _, _, terminal = _valuation_fixture(tmp_path)
    lookup = build_lookup(terminal, tmp_path / "lookup.csv")
    source = tmp_path / "source.csv"
    _write(source, [{"investment_product_id":"UNKNOWN","quantity":0,"acquisition_cost_total":-1,"acquisition_date":"","notes":""}])
    result = normalize_import(source, lookup, tmp_path / "normalized.csv", tmp_path / "diag.csv")
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["diagnostic_rows"] == 1


def test_holdings_certification(tmp_path: Path):
    _, _, terminal = _valuation_fixture(tmp_path)
    holdings = tmp_path / "holdings.csv"
    _write(holdings, [{"investment_product_id":"SL-0001","quantity":2,"acquisition_cost_total":30,"acquisition_date":"2025-01-01","notes":""}])
    result = certify_holdings(holdings, terminal, tmp_path / "cert")
    assert result["status"] == "CERTIFIED"


def test_refresh_values_and_publishes(tmp_path: Path):
    values, manifest, _ = _valuation_fixture(tmp_path)
    holdings = tmp_path / "holdings.csv"
    _write(holdings, [{"investment_product_id":"SL-0001","quantity":2,"acquisition_cost_total":30,"acquisition_date":"2025-01-01","notes":""}])
    result = refresh(values, manifest, holdings, tmp_path / "out")
    assert result["status"] == "CERTIFIED"
    assert result["terminal_integration"]["valued_positions"] == 1
    assert result["terminal_integration"]["universal_export_rows"] == 1
