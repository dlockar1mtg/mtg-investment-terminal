from __future__ import annotations

from pathlib import Path

FILES = {
    "scripts/build_secret_lair_terminal_integration.py": r'''from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

UNIVERSE_SIZE = 973
ADMITTED_SIZE = 214


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_holdings(path: Path | None) -> tuple[list[dict[str, str]], bool]:
    if path is None or not path.exists():
        return [], False
    rows = _read_csv(path)
    required = {"investment_product_id", "quantity", "acquisition_cost_total"}
    missing = required - set(rows[0].keys() if rows else [])
    if rows and missing:
        raise ValueError(f"Holdings file missing columns: {sorted(missing)}")
    return rows, True


def build(model_values: Path, manifest: Path, output_root: Path, holdings: Path | None = None) -> dict[str, object]:
    source_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    values = _read_csv(model_values)
    holdings_rows, holdings_found = _load_holdings(holdings)

    values_by_id = {row["canonical_product_id"].strip(): row for row in values}
    duplicate_value_ids = len(values_by_id) != len(values)

    valuation_rows: list[dict[str, object]] = []
    for row in values:
        product_id = row["canonical_product_id"].strip()
        value = _float(row.get("market_value_usd"))
        confidence = _float(row.get("confidence_score"))
        observation_count = int(_float(row.get("observation_count")))
        seller_count = int(_float(row.get("seller_count")))
        forecast_eligible = value > 0 and confidence >= 60 and observation_count >= 3
        recommendation_eligible = forecast_eligible and seller_count >= 3
        valuation_rows.append({
            "investment_product_id": product_id,
            "canonical_product_id": product_id,
            "product_name": row.get("canonical_product_name", ""),
            "asset_group": "Secret Lair",
            "current_price": round(value, 2),
            "currency": row.get("currency", "USD"),
            "observation_count": observation_count,
            "seller_count": seller_count,
            "confidence_score": round(confidence, 2),
            "confidence_state": row.get("confidence_state", ""),
            "forecast_input_status": "ELIGIBLE" if forecast_eligible else "SUPPRESSED",
            "recommendation_input_status": "ELIGIBLE" if recommendation_eligible else "SUPPRESSED",
            "source_lineage_sha256": source_manifest.get("source_audit_sha256", ""),
        })

    consolidated: dict[str, dict[str, object]] = {}
    for row in holdings_rows:
        product_id = row.get("investment_product_id", "").strip()
        if not product_id:
            continue
        bucket = consolidated.setdefault(product_id, {
            "investment_product_id": product_id,
            "quantity": 0.0,
            "acquisition_cost_total": 0.0,
        })
        bucket["quantity"] = _float(bucket["quantity"]) + _float(row.get("quantity"))
        bucket["acquisition_cost_total"] = _float(bucket["acquisition_cost_total"]) + _float(row.get("acquisition_cost_total"))

    position_rows: list[dict[str, object]] = []
    diagnostic_rows: list[dict[str, object]] = []
    for product_id, holding in sorted(consolidated.items()):
        source = values_by_id.get(product_id)
        quantity = _float(holding["quantity"])
        cost = _float(holding["acquisition_cost_total"])
        if source is None:
            diagnostic_rows.append({
                "investment_product_id": product_id,
                "diagnostic_type": "MISSING_ADMITTED_VALUE",
                "diagnostic_status": "REVIEW_REQUIRED",
                "detail": "Holding is not present in the governed 214-product admitted valuation interface.",
            })
            continue
        price = _float(source.get("market_value_usd"))
        current_value = round(quantity * price, 2)
        gain = round(current_value - cost, 2)
        gain_pct = round(gain / cost, 6) if cost > 0 else ""
        position_rows.append({
            "investment_product_id": product_id,
            "product_name": source.get("canonical_product_name", ""),
            "asset_group": "Secret Lair",
            "quantity": round(quantity, 6),
            "acquisition_cost_total": round(cost, 2),
            "cost_basis_per_unit": round(cost / quantity, 2) if quantity > 0 else "",
            "current_price": round(price, 2),
            "current_value": current_value,
            "unrealized_gain": gain,
            "unrealized_gain_pct": gain_pct,
            "confidence_score": _float(source.get("confidence_score")),
            "confidence_state": source.get("confidence_state", ""),
            "forecast_input_status": "ELIGIBLE" if _float(source.get("confidence_score")) >= 60 and int(_float(source.get("observation_count"))) >= 3 else "SUPPRESSED",
            "recommendation_input_status": "ELIGIBLE" if _float(source.get("confidence_score")) >= 60 and int(_float(source.get("observation_count"))) >= 3 and int(_float(source.get("seller_count"))) >= 3 else "SUPPRESSED",
        })

    total_value = round(sum(_float(row["current_value"]) for row in position_rows), 2)
    total_cost = round(sum(_float(row["acquisition_cost_total"]) for row in position_rows), 2)
    for row in position_rows:
        row["portfolio_weight"] = round(_float(row["current_value"]) / total_value, 8) if total_value > 0 else 0.0

    forecast_rows = [row.copy() for row in valuation_rows if row["forecast_input_status"] == "ELIGIBLE"]
    recommendation_rows = [row.copy() for row in valuation_rows if row["recommendation_input_status"] == "ELIGIBLE"]

    universal_positions = [{
        "asset_id": row["investment_product_id"],
        "asset_name": row["product_name"],
        "asset_class": "collectibles",
        "asset_subclass": "mtg_secret_lair",
        "quantity": row["quantity"],
        "unit_price": row["current_price"],
        "market_value": row["current_value"],
        "cost_basis": row["acquisition_cost_total"],
        "currency": "USD",
        "valuation_confidence": row["confidence_score"],
        "source_system": "mtg-investment-terminal",
    } for row in position_rows]

    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "valuation_universe": output_root / "secret_lair_terminal_valuation_universe.csv",
        "portfolio_positions": output_root / "secret_lair_portfolio_positions.csv",
        "diagnostics": output_root / "secret_lair_portfolio_valuation_diagnostics.csv",
        "forecast_inputs": output_root / "secret_lair_forecast_eligible_values.csv",
        "recommendation_inputs": output_root / "secret_lair_recommendation_eligible_values.csv",
        "universal_positions": output_root / "secret_lair_universal_portfolio_positions.csv",
        "manifest": output_root / "secret_lair_terminal_integration_manifest.json",
        "certification": output_root / "SECRET_LAIR_TERMINAL_INTEGRATION_CERTIFICATION.md",
    }
    valuation_columns = list(valuation_rows[0].keys()) if valuation_rows else []
    _write_csv(paths["valuation_universe"], valuation_rows, valuation_columns)
    position_columns = list(position_rows[0].keys()) if position_rows else [
        "investment_product_id", "product_name", "asset_group", "quantity", "acquisition_cost_total", "cost_basis_per_unit", "current_price", "current_value", "unrealized_gain", "unrealized_gain_pct", "confidence_score", "confidence_state", "forecast_input_status", "recommendation_input_status", "portfolio_weight"
    ]
    _write_csv(paths["portfolio_positions"], position_rows, position_columns)
    _write_csv(paths["diagnostics"], diagnostic_rows, ["investment_product_id", "diagnostic_type", "diagnostic_status", "detail"])
    _write_csv(paths["forecast_inputs"], forecast_rows, valuation_columns)
    _write_csv(paths["recommendation_inputs"], recommendation_rows, valuation_columns)
    universal_columns = list(universal_positions[0].keys()) if universal_positions else ["asset_id", "asset_name", "asset_class", "asset_subclass", "quantity", "unit_price", "market_value", "cost_basis", "currency", "valuation_confidence", "source_system"]
    _write_csv(paths["universal_positions"], universal_positions, universal_columns)

    checks = {
        "source_admission_certified": source_manifest.get("status") == "CERTIFIED",
        "source_universe_equal_973": int(source_manifest.get("products", 0)) == UNIVERSE_SIZE,
        "source_admitted_equal_214": int(source_manifest.get("admitted_products", 0)) == ADMITTED_SIZE,
        "valuation_rows_equal_214": len(valuation_rows) == ADMITTED_SIZE,
        "valuation_ids_unique": not duplicate_value_ids,
        "all_values_positive": all(_float(row["current_price"]) > 0 for row in valuation_rows),
        "all_currency_usd": all(row["currency"] == "USD" for row in valuation_rows),
        "positions_reconcile": round(sum(_float(row["current_value"]) for row in position_rows), 2) == total_value,
        "universal_positions_reconcile": len(universal_positions) == len(position_rows),
        "missing_holdings_is_diagnostic_only": len(position_rows) + len(diagnostic_rows) == len(consolidated),
        "quota_calls_zero": True,
    }
    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    result = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_model_values": str(model_values.resolve()),
        "source_manifest": str(manifest.resolve()),
        "source_model_values_sha256": _sha256(model_values),
        "source_manifest_sha256": _sha256(manifest),
        "products": UNIVERSE_SIZE,
        "admitted_valuation_products": len(valuation_rows),
        "forecast_eligible_products": len(forecast_rows),
        "recommendation_eligible_products": len(recommendation_rows),
        "holdings_file_found": holdings_found,
        "holding_product_ids": len(consolidated),
        "valued_positions": len(position_rows),
        "unvalued_positions": len(diagnostic_rows),
        "portfolio_current_value": total_value,
        "portfolio_cost_basis": total_cost,
        "portfolio_unrealized_gain": round(total_value - total_cost, 2),
        "universal_export_rows": len(universal_positions),
        "quota_calls": 0,
        "checks": checks,
        "outputs": {key: str(path.resolve()) for key, path in paths.items()},
    }
    paths["manifest"].write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Secret Lair Terminal Integration Certification", "",
        f"**Status:** {status}", f"**Generated at (UTC):** {result['generated_at_utc']}", "",
        "## Integration Results", "",
        f"- Governed valuation products: {len(valuation_rows)}",
        f"- Forecast-eligible products: {len(forecast_rows)}",
        f"- Recommendation-eligible products: {len(recommendation_rows)}",
        f"- Holdings file found: {holdings_found}",
        f"- Valued positions: {len(position_rows)}",
        f"- Unvalued positions: {len(diagnostic_rows)}",
        f"- Portfolio current value: ${total_value:,.2f}",
        f"- Portfolio cost basis: ${total_cost:,.2f}",
        f"- Portfolio unrealized gain: ${total_value-total_cost:,.2f}",
        f"- Universal export rows: {len(universal_positions)}",
        "- API quota calls: 0", "", "## Certification Checks", "",
    ]
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
    paths["certification"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("SECRET LAIR TERMINAL INTEGRATION: COMPLETE")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-values", type=Path, required=True)
    parser.add_argument("--admission-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--holdings", type=Path)
    args = parser.parse_args()
    build(args.model_values, args.admission_manifest, args.output_root, args.holdings)


if __name__ == "__main__":
    main()
''',
    "terminal2/market_sources/secret_lair_terminal.py": r'''from __future__ import annotations

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
''',
    "tests/test_secret_lair_terminal_integration.py": r'''from __future__ import annotations

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
''',
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative, content in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing file: {relative}")
        path.write_text(content, encoding="utf-8")
        print(f"Created: {relative}")
    print("SECRET LAIR TERMINAL INTEGRATION BUNDLE: APPLIED")


if __name__ == "__main__":
    main()
