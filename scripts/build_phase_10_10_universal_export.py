from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "data" / "validation" / "phase_10"
REGISTRY = VALIDATION / "unified_mtg_registry" / "unified_mtg_product_registry.csv"
INTELLIGENCE = VALIDATION / "unified_mtg_intelligence" / "unified_mtg_intelligence_interface.csv"
PORTFOLIO_SUMMARY = VALIDATION / "unified_mtg_portfolio" / "unified_mtg_portfolio_lane_summary.csv"
CLOSEOUT = VALIDATION / "unified_mtg_closeout" / "phase_10_9_unified_mtg_production_closeout.json"
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


def value(row: dict[str, str], name: str) -> str:
    return str(row.get(name, "") or "").strip()


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
        product_id = asset["universal_mtg_product_id"].strip()
        intelligence_row = intelligence_by_id.get(product_id)
        if intelligence_row is None:
            diagnostics.append(
                {
                    "universal_mtg_product_id": product_id,
                    "diagnostic": "MISSING_INTELLIGENCE_ROW",
                }
            )
            continue

        asset_rows.append(
            {
                "asset_id": product_id,
                "asset_name": value(asset, "canonical_product_name"),
                "asset_class": "MTG",
                "asset_subclass": value(asset, "lane"),
                "product_class": value(asset, "product_class"),
                "source_product_id": value(asset, "source_product_id"),
                "canonical_set_name": value(asset, "canonical_set_name"),
                "release_date": value(asset, "release_date"),
                "registry_status": value(asset, "registry_status"),
                "currency": value(asset, "currency") or "USD",
            }
        )

        forecast_rows.append(
            {
                "asset_id": product_id,
                "forecast_eligible": value(intelligence_row, "forecast_eligible"),
                "forecast_status": value(intelligence_row, "forecast_status"),
                "forecast_method": value(intelligence_row, "forecast_method"),
                "current_market_value_usd": value(intelligence_row, "current_market_value_usd"),
                "native_forecast_low_usd": value(intelligence_row, "native_forecast_low_usd"),
                "native_forecast_base_usd": value(intelligence_row, "native_forecast_base_usd"),
                "native_forecast_high_usd": value(intelligence_row, "native_forecast_high_usd"),
                "one_year_downside_usd": value(intelligence_row, "one_year_downside_usd"),
                "one_year_base_usd": value(intelligence_row, "one_year_base_usd"),
                "one_year_upside_usd": value(intelligence_row, "one_year_upside_usd"),
                "three_year_downside_usd": value(intelligence_row, "three_year_downside_usd"),
                "three_year_base_usd": value(intelligence_row, "three_year_base_usd"),
                "three_year_upside_usd": value(intelligence_row, "three_year_upside_usd"),
                "five_year_downside_usd": value(intelligence_row, "five_year_downside_usd"),
                "five_year_base_usd": value(intelligence_row, "five_year_base_usd"),
                "five_year_upside_usd": value(intelligence_row, "five_year_upside_usd"),
                "confidence": value(intelligence_row, "confidence"),
                "currency": value(intelligence_row, "currency") or "USD",
            }
        )

        recommendation_rows.append(
            {
                "asset_id": product_id,
                "recommendation_eligible": value(intelligence_row, "recommendation_eligible"),
                "recommendation_status": value(intelligence_row, "recommendation_status"),
                "recommendation_action": value(intelligence_row, "recommendation_action"),
                "recommendation_rationale": value(intelligence_row, "rationale"),
                "suppression_reason": value(intelligence_row, "suppression_reason"),
                "confidence": value(intelligence_row, "confidence"),
                "currency": value(intelligence_row, "currency") or "USD",
            }
        )

        risk_rows.append(
            {
                "asset_id": product_id,
                "admission_tier": value(intelligence_row, "admission_tier"),
                "quality_disposition": value(intelligence_row, "quality_disposition"),
                "quality_flags": value(intelligence_row, "suppression_reason"),
                "confidence": value(intelligence_row, "confidence"),
                "forecast_eligible": value(intelligence_row, "forecast_eligible"),
                "recommendation_eligible": value(intelligence_row, "recommendation_eligible"),
            }
        )

    platform_status_rows = [
        {
            "platform": "MTG",
            "status": "PRODUCTION_CLOSED",
            "interface_name": INTERFACE_NAME,
            "contract_version": CONTRACT_VERSION,
            "products": len(asset_rows),
            "owned_positions": closeout.get("owned_positions", 0),
            "forecast_eligible": sum(
                as_bool(row["forecast_eligible"]) for row in forecast_rows
            ),
            "recommendation_eligible": sum(
                as_bool(row["recommendation_eligible"])
                for row in recommendation_rows
            ),
            "diagnostics": len(diagnostics),
            "generated_at_utc": generated_at.isoformat(),
        }
    ]

    public_portfolio_rows = [
        {
            "asset_subclass": value(row, "lane"),
            "owned_positions": value(row, "owned_positions"),
            "cost_basis_usd": value(row, "cost_basis_usd"),
            "market_value_usd": value(row, "market_value_usd"),
            "unrealized_gain_loss_usd": value(row, "unrealized_gain_loss_usd"),
            "currency": "USD",
        }
        for row in portfolio_summary
    ]

    write_csv(package_dir / "asset_master.csv", list(asset_rows[0]), asset_rows)
    write_csv(package_dir / "forecasts.csv", list(forecast_rows[0]), forecast_rows)
    write_csv(
        package_dir / "recommendations.csv",
        list(recommendation_rows[0]),
        recommendation_rows,
    )
    write_csv(package_dir / "risk_metrics.csv", list(risk_rows[0]), risk_rows)
    write_csv(
        package_dir / "portfolio_summary.csv",
        list(public_portfolio_rows[0]),
        public_portfolio_rows,
    )
    write_csv(
        package_dir / "platform_status.csv",
        list(platform_status_rows[0]),
        platform_status_rows,
    )
    write_csv(
        package_dir / "diagnostics.csv",
        ["universal_mtg_product_id", "diagnostic"],
        diagnostics,
    )

    exported_files = [
        "asset_master.csv",
        "forecasts.csv",
        "recommendations.csv",
        "risk_metrics.csv",
        "portfolio_summary.csv",
        "platform_status.csv",
        "diagnostics.csv",
    ]

    manifest = {
        "package_id": package_id,
        "interface_name": INTERFACE_NAME,
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": generated_at.isoformat(),
        "source_closeout_status": closeout.get("status"),
        "products": len(asset_rows),
        "forecast_eligible": platform_status_rows[0]["forecast_eligible"],
        "recommendation_eligible": platform_status_rows[0][
            "recommendation_eligible"
        ],
        "portfolio_summary_rows": len(public_portfolio_rows),
        "diagnostics": len(diagnostics),
        "privacy_boundary": {
            "position_level_holdings_exported": False,
            "forbidden_private_fields": sorted(FORBIDDEN_PRIVATE_FIELDS),
        },
        "files": {
            name: {
                "sha256": sha256(package_dir / name),
                "bytes": (package_dir / name).stat().st_size,
            }
            for name in exported_files
        },
        "quota_calls": 0,
    }

    (package_dir / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    summary = {
        "status": "PASS"
        if (
            len(asset_rows) == EXPECTED_PRODUCTS
            and not diagnostics
            and closeout.get("status") == "PRODUCTION_CLOSED"
        )
        else "FAIL",
        **manifest,
    }
    (package_dir / "package_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    if LATEST.exists():
        shutil.rmtree(LATEST)
    shutil.copytree(package_dir, LATEST)

    print(f"PHASE 10.10 UNIVERSAL EXPORT PACKAGE: {summary['status']}")
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
