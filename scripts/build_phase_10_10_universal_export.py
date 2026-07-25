from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "data" / "validation" / "phase_10"
REGISTRY = VALIDATION / "unified_mtg_registry" / "unified_mtg_product_registry.csv"
INTELLIGENCE = VALIDATION / "unified_mtg_intelligence" / "unified_mtg_intelligence_interface.csv"
PORTFOLIO_SUMMARY = VALIDATION / "unified_mtg_portfolio" / "unified_mtg_portfolio_lane_summary.csv"
CLOSEOUT = VALIDATION / "unified_mtg_closeout" / "phase_10_9_unified_mtg_closeout_manifest.json"
OUTPUT_ROOT = VALIDATION / "universal_export"
LATEST = OUTPUT_ROOT / "latest"

INTERFACE_NAME = "mtg-universal-export-v1"
CONTRACT_VERSION = "1"
EXPECTED_PRODUCTS = 1141
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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_bool(value: str) -> bool:
    return str(value).strip().upper() in {"TRUE", "YES", "1", "Y"}


def first(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name, "").strip()
        if value:
            return value
    return ""


def main() -> int:
    required = [REGISTRY, INTELLIGENCE, PORTFOLIO_SUMMARY, CLOSEOUT]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing certified Phase 10.9 artifacts. Run Phase 10.9.1B through 10.9.4 first:\n"
            + "\n".join(missing)
        )

    registry = read_csv(REGISTRY)
    intelligence = read_csv(INTELLIGENCE)
    portfolio_summary = read_csv(PORTFOLIO_SUMMARY)
    closeout = json.loads(CLOSEOUT.read_text(encoding="utf-8"))

    if closeout.get("status") != "PRODUCTION_CLOSED":
        raise RuntimeError("Phase 10.9 closeout is not PRODUCTION_CLOSED")

    intelligence_by_id = {
        row["universal_mtg_product_id"].strip(): row for row in intelligence
    }

    generated_at = datetime.now(timezone.utc)
    package_id = generated_at.strftime("mtg-%Y%m%dT%H%M%SZ")
    package_dir = OUTPUT_ROOT / package_id
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    asset_rows: list[dict[str, Any]] = []
    forecast_rows: list[dict[str, Any]] = []
    recommendation_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []

    diagnostics: list[dict[str, str]] = []

    for asset in registry:
        asset_id = asset["universal_mtg_product_id"].strip()
        intel = intelligence_by_id.get(asset_id)
        if intel is None:
            diagnostics.append({"asset_id": asset_id, "diagnostic": "MISSING_INTELLIGENCE"})
            continue

        asset_rows.append(
            {
                "asset_id": asset_id,
                "asset_name": asset["canonical_product_name"].strip(),
                "asset_type": "MTG_SEALED_PRODUCT",
                "asset_subtype": asset["lane"].strip(),
                "platform": "MTG",
                "source_product_id": asset["source_product_id"].strip(),
                "product_class": asset["product_class"].strip(),
                "canonical_set_name": asset.get("canonical_set_name", "").strip(),
                "finish_group": asset.get("finish_group", "").strip(),
                "release_date": asset.get("release_date", "").strip(),
                "currency": "USD",
                "registry_status": asset.get("registry_status", "GOVERNED").strip() or "GOVERNED",
            }
        )

        forecast_eligible = as_bool(first(intel, "forecast_eligible"))
        recommendation_eligible = as_bool(first(intel, "recommendation_eligible"))

        forecast_rows.append(
            {
                "asset_id": asset_id,
                "platform": "MTG",
                "forecast_eligible": str(forecast_eligible).lower(),
                "forecast_status": first(intel, "forecast_status"),
                "forecast_method": first(intel, "forecast_method"),
                "current_value_usd": first(intel, "current_market_value_usd", "market_value_usd"),
                "forecast_low_usd": first(intel, "forecast_low_usd", "one_year_downside_usd", "1y_downside_usd"),
                "forecast_base_usd": first(intel, "forecast_base_usd", "one_year_base_usd", "1y_base_usd"),
                "forecast_high_usd": first(intel, "forecast_high_usd", "one_year_upside_usd", "1y_upside_usd"),
                "forecast_1y_low_usd": first(intel, "one_year_downside_usd", "1y_downside_usd"),
                "forecast_1y_base_usd": first(intel, "one_year_base_usd", "1y_base_usd"),
                "forecast_1y_high_usd": first(intel, "one_year_upside_usd", "1y_upside_usd"),
                "forecast_3y_low_usd": first(intel, "three_year_downside_usd", "3y_downside_usd"),
                "forecast_3y_base_usd": first(intel, "three_year_base_usd", "3y_base_usd"),
                "forecast_3y_high_usd": first(intel, "three_year_upside_usd", "3y_upside_usd"),
                "forecast_5y_low_usd": first(intel, "five_year_downside_usd", "5y_downside_usd"),
                "forecast_5y_base_usd": first(intel, "five_year_base_usd", "5y_base_usd"),
                "forecast_5y_high_usd": first(intel, "five_year_upside_usd", "5y_upside_usd"),
                "confidence": first(intel, "confidence", "model_confidence_score"),
                "currency": "USD",
            }
        )

        recommendation_rows.append(
            {
                "asset_id": asset_id,
                "platform": "MTG",
                "recommendation_eligible": str(recommendation_eligible).lower(),
                "action": first(intel, "recommendation_action", "guarded_recommendation", "action"),
                "recommendation_status": first(intel, "recommendation_status"),
                "confidence": first(intel, "confidence", "model_confidence_score"),
                "rationale": first(intel, "rationale", "suppression_reason"),
                "suppression_reason": first(intel, "suppression_reason"),
                "currency": "USD",
            }
        )

        risk_rows.append(
            {
                "asset_id": asset_id,
                "platform": "MTG",
                "admission_tier": first(intel, "admission_tier", "evaluation_tier"),
                "quality_disposition": first(intel, "quality_disposition", "quality_decision", "plausibility_disposition"),
                "quality_flags": first(intel, "quality_flags", "plausibility_flags"),
                "confidence": first(intel, "confidence", "model_confidence_score"),
                "forecast_eligible": str(forecast_eligible).lower(),
                "recommendation_eligible": str(recommendation_eligible).lower(),
            }
        )

    portfolio_public_rows = []
    for row in portfolio_summary:
        portfolio_public_rows.append(
            {
                "platform": "MTG",
                "asset_subtype": row["lane"].strip(),
                "owned_positions": row["owned_positions"].strip(),
                "cost_basis_usd": row["cost_basis_usd"].strip(),
                "market_value_usd": row["market_value_usd"].strip(),
                "unrealized_gain_loss_usd": row["unrealized_gain_loss_usd"].strip(),
                "currency": "USD",
            }
        )

    platform_status_rows = [
        {
            "platform": "MTG",
            "status": "PRODUCTION_CLOSED",
            "interface_name": INTERFACE_NAME,
            "contract_version": CONTRACT_VERSION,
            "product_count": len(asset_rows),
            "owned_position_count": closeout.get("owned_positions", 14),
            "forecast_eligible_count": sum(as_bool(row["forecast_eligible"]) for row in forecast_rows),
            "recommendation_eligible_count": sum(as_bool(row["recommendation_eligible"]) for row in recommendation_rows),
            "generated_at_utc": generated_at.isoformat(),
            "quota_calls": 0,
        }
    ]

    outputs = {
        "asset_master.csv": (asset_rows, list(asset_rows[0].keys())),
        "forecasts.csv": (forecast_rows, list(forecast_rows[0].keys())),
        "recommendations.csv": (recommendation_rows, list(recommendation_rows[0].keys())),
        "risk_metrics.csv": (risk_rows, list(risk_rows[0].keys())),
        "portfolio_summary.csv": (portfolio_public_rows, list(portfolio_public_rows[0].keys())),
        "platform_status.csv": (platform_status_rows, list(platform_status_rows[0].keys())),
        "diagnostics.csv": (diagnostics, ["asset_id", "diagnostic"]),
    }

    for filename, (rows, fields) in outputs.items():
        write_csv(package_dir / filename, fields, rows)

    row_counts = {filename: len(rows) for filename, (rows, _) in outputs.items()}
    files_manifest = {
        filename: {
            "sha256": sha256(package_dir / filename),
            "rows": row_counts[filename],
        }
        for filename in outputs
    }

    exported_headers = set()
    for _, (_, fields) in outputs.items():
        exported_headers.update(fields)

    checks = {
        "phase_10_9_production_closed": closeout.get("status") == "PRODUCTION_CLOSED",
        "asset_master_rows_equal_1141": len(asset_rows) == EXPECTED_PRODUCTS,
        "forecasts_rows_equal_1141": len(forecast_rows) == EXPECTED_PRODUCTS,
        "recommendations_rows_equal_1141": len(recommendation_rows) == EXPECTED_PRODUCTS,
        "risk_metrics_rows_equal_1141": len(risk_rows) == EXPECTED_PRODUCTS,
        "portfolio_summary_rows_equal_3": len(portfolio_public_rows) == 3,
        "diagnostics_zero": len(diagnostics) == 0,
        "asset_ids_unique": len({row["asset_id"] for row in asset_rows}) == EXPECTED_PRODUCTS,
        "forecast_ids_match_assets": {row["asset_id"] for row in forecast_rows} == {row["asset_id"] for row in asset_rows},
        "recommendation_ids_match_assets": {row["asset_id"] for row in recommendation_rows} == {row["asset_id"] for row in asset_rows},
        "private_position_fields_excluded": not (FORBIDDEN_PRIVATE_FIELDS & exported_headers),
        "currency_usd": all(row["currency"] == "USD" for row in asset_rows),
        "quota_calls_zero": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    package_summary = {
        "package_id": package_id,
        "platform": "MTG",
        "interface_name": INTERFACE_NAME,
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": generated_at.isoformat(),
        "validation_status": status,
        "product_count": len(asset_rows),
        "lane_counts": dict(sorted(Counter(row["asset_subtype"] for row in asset_rows).items())),
        "forecast_eligible_count": sum(as_bool(row["forecast_eligible"]) for row in forecast_rows),
        "recommendation_eligible_count": sum(as_bool(row["recommendation_eligible"]) for row in recommendation_rows),
        "portfolio_summary_only": True,
        "private_position_details_included": False,
        "checks": checks,
        "files": files_manifest,
        "source_artifact_sha256": {
            "registry": sha256(REGISTRY),
            "intelligence": sha256(INTELLIGENCE),
            "portfolio_summary": sha256(PORTFOLIO_SUMMARY),
            "phase_10_9_closeout": sha256(CLOSEOUT),
        },
        "quota_calls": 0,
    }
    (package_dir / "package_summary.json").write_text(
        json.dumps(package_summary, indent=2), encoding="utf-8"
    )

    manifest = {
        "package_id": package_id,
        "validation_status": status,
        "package_summary_sha256": sha256(package_dir / "package_summary.json"),
        "files": {
            path.name: sha256(path)
            for path in sorted(package_dir.iterdir())
            if path.is_file()
        },
    }
    (package_dir / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    if LATEST.exists():
        shutil.rmtree(LATEST)
    shutil.copytree(package_dir, LATEST)

    print(f"PHASE 10.10 UNIVERSAL EXPORT PACKAGE: {status}")
    print(json.dumps(package_summary, indent=2))
    print(f"Package directory: {package_dir}")
    print(f"Latest directory: {LATEST}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
