from __future__ import annotations

from pathlib import Path

FILES = {
    "scripts/manage_secret_lair_holdings.py": r'''from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

HOLDINGS_COLUMNS = (
    "investment_product_id",
    "quantity",
    "acquisition_cost_total",
    "acquisition_date",
    "notes",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, object]], columns: tuple[str, ...] | list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def create_template(path: Path) -> Path:
    if not path.exists():
        _write_csv(path, [], HOLDINGS_COLUMNS)
    return path


def build_lookup(valuation_universe: Path, output_path: Path) -> Path:
    rows = _read_csv(valuation_universe)
    lookup = [{
        "investment_product_id": row["investment_product_id"],
        "product_name": row["product_name"],
        "current_price": row["current_price"],
        "confidence_score": row["confidence_score"],
        "confidence_state": row["confidence_state"],
        "forecast_input_status": row["forecast_input_status"],
        "recommendation_input_status": row["recommendation_input_status"],
    } for row in rows]
    _write_csv(output_path, lookup, list(lookup[0]) if lookup else [])
    return output_path


def search_lookup(lookup_path: Path, query: str, limit: int = 25) -> list[dict[str, str]]:
    query_norm = query.strip().lower()
    rows = _read_csv(lookup_path)
    matches = [row for row in rows if query_norm in row.get("product_name", "").lower() or query_norm in row.get("investment_product_id", "").lower()]
    return matches[:limit]


def normalize_import(source: Path, lookup_path: Path, output_path: Path, diagnostics_path: Path) -> dict[str, object]:
    source_rows = _read_csv(source)
    lookup = {row["investment_product_id"].strip(): row for row in _read_csv(lookup_path)}
    required = {"investment_product_id", "quantity", "acquisition_cost_total"}
    if source_rows:
        missing = required - set(source_rows[0])
        if missing:
            raise ValueError(f"Owned inventory source missing columns: {sorted(missing)}")

    consolidated: dict[str, dict[str, object]] = {}
    diagnostics: list[dict[str, object]] = []
    for line_number, row in enumerate(source_rows, start=2):
        product_id = row.get("investment_product_id", "").strip()
        quantity = _float(row.get("quantity"), -1)
        cost = _float(row.get("acquisition_cost_total"), -1)
        issues: list[str] = []
        if not product_id:
            issues.append("BLANK_PRODUCT_ID")
        elif product_id not in lookup:
            issues.append("UNKNOWN_OR_SUPPRESSED_PRODUCT_ID")
        if quantity <= 0:
            issues.append("INVALID_QUANTITY")
        if cost < 0:
            issues.append("INVALID_COST_BASIS")
        if issues:
            diagnostics.append({
                "source_line": line_number,
                "investment_product_id": product_id,
                "diagnostic_status": "REVIEW_REQUIRED",
                "diagnostic_codes": "|".join(issues),
            })
            continue
        bucket = consolidated.setdefault(product_id, {
            "investment_product_id": product_id,
            "quantity": 0.0,
            "acquisition_cost_total": 0.0,
            "acquisition_date": row.get("acquisition_date", ""),
            "notes": set(),
        })
        bucket["quantity"] = _float(bucket["quantity"]) + quantity
        bucket["acquisition_cost_total"] = _float(bucket["acquisition_cost_total"]) + cost
        date = row.get("acquisition_date", "").strip()
        if date and (not bucket["acquisition_date"] or date < str(bucket["acquisition_date"])):
            bucket["acquisition_date"] = date
        note = row.get("notes", "").strip()
        if note:
            bucket["notes"].add(note)

    normalized = []
    for product_id in sorted(consolidated):
        row = consolidated[product_id]
        normalized.append({
            "investment_product_id": product_id,
            "quantity": round(_float(row["quantity"]), 6),
            "acquisition_cost_total": round(_float(row["acquisition_cost_total"]), 2),
            "acquisition_date": row["acquisition_date"],
            "notes": " | ".join(sorted(row["notes"])),
        })
    _write_csv(output_path, normalized, HOLDINGS_COLUMNS)
    _write_csv(diagnostics_path, diagnostics, ["source_line", "investment_product_id", "diagnostic_status", "diagnostic_codes"])
    result = {
        "status": "CERTIFIED" if not diagnostics else "REVIEW_REQUIRED",
        "source_rows": len(source_rows),
        "normalized_rows": len(normalized),
        "diagnostic_rows": len(diagnostics),
        "duplicate_rows_consolidated": max(0, len(source_rows) - len(normalized) - len(diagnostics)),
        "total_quantity": round(sum(_float(row["quantity"]) for row in normalized), 6),
        "total_cost_basis": round(sum(_float(row["acquisition_cost_total"]) for row in normalized), 2),
        "output": str(output_path.resolve()),
        "diagnostics": str(diagnostics_path.resolve()),
    }
    print("SECRET LAIR HOLDINGS IMPORT: COMPLETE")
    print(json.dumps(result, indent=2))
    return result


def certify_holdings(holdings_path: Path, valuation_universe: Path, output_root: Path) -> dict[str, object]:
    holdings = _read_csv(holdings_path)
    values = {row["investment_product_id"]: row for row in _read_csv(valuation_universe)}
    ids = [row.get("investment_product_id", "").strip() for row in holdings]
    checks = {
        "required_columns_present": not holdings or set(HOLDINGS_COLUMNS).issubset(holdings[0]),
        "product_ids_unique": len(ids) == len(set(ids)),
        "all_product_ids_known": all(product_id in values for product_id in ids),
        "all_quantities_positive": all(_float(row.get("quantity")) > 0 for row in holdings),
        "all_cost_basis_nonnegative": all(_float(row.get("acquisition_cost_total"), -1) >= 0 for row in holdings),
        "quota_calls_zero": True,
    }
    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    result = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "holdings_rows": len(holdings),
        "total_quantity": round(sum(_float(row.get("quantity")) for row in holdings), 6),
        "total_cost_basis": round(sum(_float(row.get("acquisition_cost_total")) for row in holdings), 2),
        "checks": checks,
        "quota_calls": 0,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "secret_lair_holdings_certification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = ["# Secret Lair Holdings Certification", "", f"**Status:** {status}", "", f"- Holdings rows: {len(holdings)}", f"- Total quantity: {result['total_quantity']}", f"- Total cost basis: ${result['total_cost_basis']:,.2f}", "- API quota calls: 0", "", "## Checks", ""]
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
    (output_root / "SECRET_LAIR_HOLDINGS_CERTIFICATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("SECRET LAIR HOLDINGS CERTIFICATION: COMPLETE")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    template = subparsers.add_parser("template")
    template.add_argument("--output", type=Path, required=True)

    lookup = subparsers.add_parser("lookup")
    lookup.add_argument("--valuation-universe", type=Path, required=True)
    lookup.add_argument("--output", type=Path, required=True)

    search = subparsers.add_parser("search")
    search.add_argument("--lookup", type=Path, required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=25)

    imp = subparsers.add_parser("import")
    imp.add_argument("--source", type=Path, required=True)
    imp.add_argument("--lookup", type=Path, required=True)
    imp.add_argument("--output", type=Path, required=True)
    imp.add_argument("--diagnostics", type=Path, required=True)

    cert = subparsers.add_parser("certify")
    cert.add_argument("--holdings", type=Path, required=True)
    cert.add_argument("--valuation-universe", type=Path, required=True)
    cert.add_argument("--output-root", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "template":
        print(create_template(args.output))
    elif args.command == "lookup":
        print(build_lookup(args.valuation_universe, args.output))
    elif args.command == "search":
        print(json.dumps(search_lookup(args.lookup, args.query, args.limit), indent=2))
    elif args.command == "import":
        normalize_import(args.source, args.lookup, args.output, args.diagnostics)
    elif args.command == "certify":
        certify_holdings(args.holdings, args.valuation_universe, args.output_root)


if __name__ == "__main__":
    main()
''',
    "scripts/refresh_secret_lair_portfolio.py": r'''from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.build_secret_lair_terminal_integration import build
from scripts.manage_secret_lair_holdings import certify_holdings


def refresh(model_values: Path, admission_manifest: Path, holdings: Path, output_root: Path) -> dict[str, object]:
    integration_root = output_root / "terminal_integration"
    holdings_cert_root = output_root / "holdings_certification"
    valuation_universe = integration_root / "secret_lair_terminal_valuation_universe.csv"

    first = build(model_values, admission_manifest, integration_root)
    holdings_cert = certify_holdings(holdings, valuation_universe, holdings_cert_root)
    if holdings_cert["status"] != "CERTIFIED":
        result = {"status": "FAILED", "holdings_certification": holdings_cert, "initial_integration": first}
        print("SECRET LAIR PORTFOLIO REFRESH: FAILED")
        print(json.dumps(result, indent=2))
        return result

    final = build(model_values, admission_manifest, integration_root, holdings)
    status = "CERTIFIED" if final["status"] == "CERTIFIED" and holdings_cert["status"] == "CERTIFIED" else "FAILED"
    result = {
        "status": status,
        "holdings_certification": holdings_cert,
        "terminal_integration": final,
        "published_outputs": final["outputs"],
        "quota_calls": 0,
    }
    (output_root / "secret_lair_portfolio_refresh_manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("SECRET LAIR PORTFOLIO REFRESH: COMPLETE")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-values", type=Path, required=True)
    parser.add_argument("--admission-manifest", type=Path, required=True)
    parser.add_argument("--holdings", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    refresh(args.model_values, args.admission_manifest, args.holdings, args.output_root)


if __name__ == "__main__":
    main()
''',
    "tests/test_secret_lair_holdings_workflow.py": r'''from __future__ import annotations

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
    print("SECRET LAIR HOLDINGS WORKFLOW BUNDLE: APPLIED")


if __name__ == "__main__":
    main()
