from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data" / "validation" / "phase_10" / "universal_export" / "latest"
REQUIRED_FILES = {
    "asset_master.csv": 1141,
    "forecasts.csv": 1141,
    "recommendations.csv": 1141,
    "risk_metrics.csv": 1141,
    "portfolio_summary.csv": 3,
    "platform_status.csv": 1,
    "diagnostics.csv": 0,
}
FORBIDDEN_PRIVATE_FIELDS = {
    "acquisition_date",
    "acquisition_cost_total",
    "total_cost_basis_usd",
    "unit_cost_usd",
    "quantity",
    "holding_id",
    "source_holding_id",
    "notes",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def main() -> int:
    summary_path = PACKAGE / "package_summary.json"
    manifest_path = PACKAGE / "export_manifest.json"
    if not summary_path.exists() or not manifest_path.exists():
        raise FileNotFoundError("Run scripts/build_phase_10_10_universal_export.py first")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    all_headers: set[str] = set()
    asset_ids: set[str] = set()

    for filename, expected_rows in REQUIRED_FILES.items():
        path = PACKAGE / filename
        checks[f"{filename}_exists"] = path.exists()
        if not path.exists():
            continue
        headers, rows = read_csv(path)
        all_headers.update(headers)
        checks[f"{filename}_rows"] = len(rows) == expected_rows
        expected_sha = manifest.get("files", {}).get(filename)
        checks[f"{filename}_sha"] = expected_sha == sha256(path)
        if filename == "asset_master.csv":
            asset_ids = {row["asset_id"] for row in rows}
            checks["asset_ids_unique"] = len(asset_ids) == 1141
        elif filename in {"forecasts.csv", "recommendations.csv", "risk_metrics.csv"}:
            checks[f"{filename}_ids_match_assets"] = {row["asset_id"] for row in rows} == asset_ids

    checks["summary_status_pass"] = summary.get("validation_status") == "PASS"
    checks["manifest_status_pass"] = manifest.get("validation_status") == "PASS"
    checks["summary_product_count"] = summary.get("product_count") == 1141
    checks["private_position_fields_excluded"] = not (FORBIDDEN_PRIVATE_FIELDS & all_headers)
    checks["private_position_details_false"] = summary.get("private_position_details_included") is False
    checks["portfolio_summary_only_true"] = summary.get("portfolio_summary_only") is True
    checks["quota_calls_zero"] = summary.get("quota_calls") == 0
    checks["package_summary_sha"] = manifest.get("package_summary_sha256") == sha256(summary_path)

    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    report = {
        "status": status,
        "phase": "10.10",
        "package_id": summary.get("package_id"),
        "checks": checks,
        "quota_calls": 0,
    }
    print(f"PHASE 10.10 UNIVERSAL EXPORT VALIDATION: {status}")
    print(json.dumps(report, indent=2))
    return 0 if status == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
