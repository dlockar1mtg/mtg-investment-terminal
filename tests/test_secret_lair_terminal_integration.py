from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.build_secret_lair_terminal_integration import build
from terminal2.market_sources.secret_lair_terminal import SecretLairTerminalValueStore


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def _fixtures(tmp_path: Path):
    values = tmp_path / "values.csv"
    rows = []
    for index in range(214):
        rows.append({
            "canonical_product_id": f"SL-{index:04d}",
            "canonical_product_name": f"Product {index}",
            "market_value_usd": 10 + index,
            "currency": "USD",
            "observation_count": 4 if index % 2 == 0 else 2,
            "seller_count": 4 if index % 3 == 0 else 2,
            "confidence_score": 70 if index % 2 == 0 else 55,
            "confidence_state": "MEDIUM",
        })
    _write(values, rows)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"status":"CERTIFIED","products":973,"admitted_products":214,"source_audit_sha256":"abc"}), encoding="utf-8")
    return values, manifest


def test_build_certifies_214_product_interface(tmp_path: Path):
    values, manifest = _fixtures(tmp_path)
    result = build(values, manifest, tmp_path / "out")
    assert result["status"] == "CERTIFIED"
    assert result["admitted_valuation_products"] == 214
    assert result["quota_calls"] == 0


def test_holdings_valuation_and_diagnostics(tmp_path: Path):
    values, manifest = _fixtures(tmp_path)
    holdings = tmp_path / "holdings.csv"
    _write(holdings, [
        {"investment_product_id":"SL-0000","quantity":2,"acquisition_cost_total":15},
        {"investment_product_id":"UNKNOWN","quantity":1,"acquisition_cost_total":5},
    ])
    result = build(values, manifest, tmp_path / "out", holdings)
    assert result["valued_positions"] == 1
    assert result["unvalued_positions"] == 1
    assert result["portfolio_current_value"] == 20.0


def test_store_loads_unique_positive_values(tmp_path: Path):
    values, manifest = _fixtures(tmp_path)
    build(values, manifest, tmp_path / "out")
    store = SecretLairTerminalValueStore(tmp_path / "out" / "secret_lair_terminal_valuation_universe.csv")
    loaded = store.load()
    assert len(loaded) == 214
    assert len(store.by_product_id()) == 214
    assert all(value.current_price > 0 for value in loaded)


def test_forecast_and_recommendation_gates(tmp_path: Path):
    values, manifest = _fixtures(tmp_path)
    result = build(values, manifest, tmp_path / "out")
    assert 0 < result["recommendation_eligible_products"] <= result["forecast_eligible_products"] < 214


def test_outputs_include_universal_export(tmp_path: Path):
    values, manifest = _fixtures(tmp_path)
    holdings = tmp_path / "holdings.csv"
    _write(holdings, [{"investment_product_id":"SL-0000","quantity":2,"acquisition_cost_total":15}])
    result = build(values, manifest, tmp_path / "out", holdings)
    export = Path(result["outputs"]["universal_positions"])
    rows = list(csv.DictReader(export.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["asset_subclass"] == "mtg_secret_lair"
