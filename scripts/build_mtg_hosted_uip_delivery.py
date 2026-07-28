from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data" / "reference" / "phase_11" / "mtg_hosted_baseline"
UNIFIED_INTERFACE = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "unified_mtg_intelligence"
    / "unified_mtg_intelligence_interface.csv"
)
DEFAULT_OUTPUT = ROOT / "data" / "operations" / "mtg_uip_delivery"

FILES = {
    "secret_lair": (
        BASELINE / "secret_lair_registry.csv",
        BASELINE / "secret_lair_evaluation.csv",
    ),
    "collector_booster_box": (
        BASELINE / "collector_registry.csv",
        BASELINE / "collector_evaluation.csv",
    ),
    "pre_collector_booster_box": (
        BASELINE / "pre_collector_registry.csv",
        BASELINE / "pre_collector_evaluation.csv",
    ),
}

LANE_NAMES = {
    "secret_lair": "SECRET_LAIR",
    "collector_booster_box": "COLLECTOR_BOOSTER_BOX",
    "pre_collector_booster_box": "PRE_COLLECTOR_BOOSTER_BOX",
}

EXPECTED_COUNTS = {
    "secret_lair": 973,
    "collector_booster_box": 49,
    "pre_collector_booster_box": 119,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def first(row: dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = str(row.get(name, "") or "").strip()
        if value:
            return value
    return default


def source_id(row: dict[str, str]) -> str:
    return first(
        row,
        "investment_product_id",
        "canonical_product_id",
        "source_product_id",
        "product_id",
        "tcgplayer_product_id",
    )


def tcgplayer_id(row: dict[str, str]) -> str:
    return first(
        row,
        "approved_tcgplayer_product_id",
        "tcgplayer_product_id",
        "tcgplayer_product_id_str",
    )


def universal_id(lane: str, source: str) -> str:
    if source.startswith("MTG:"):
        return source
    return f"MTG:{lane}:{source}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_bool(value: str) -> str:
    return "YES" if str(value).strip().upper() in {
        "YES", "TRUE", "1", "ELIGIBLE", "PASS", "SCENARIO_READY"
    } else "NO"


def build(output_root: Path) -> dict[str, Any]:
    generated = datetime.now(timezone.utc)
    package_id = generated.strftime("mtg-hosted-%Y%m%dT%H%M%SZ")
    package = output_root / package_id
    if package.exists():
        shutil.rmtree(package)
    package.mkdir(parents=True, exist_ok=True)

    asset_rows: list[dict[str, str]] = []
    forecast_rows: list[dict[str, str]] = []
    recommendation_rows: list[dict[str, str]] = []
    risk_rows: list[dict[str, str]] = []
    diagnostics: list[dict[str, str]] = []

    lane_counts: dict[str, int] = {}

    unified_rows = read_csv(UNIFIED_INTERFACE)

    if len(unified_rows) != 1141:
        raise RuntimeError(
            "Unified intelligence interface must contain 1,141 rows; "
            f"found {len(unified_rows)}"
        )

    unified_ids = {
        first(row, "universal_mtg_product_id")
        for row in unified_rows
        if first(row, "universal_mtg_product_id")
    }

    if len(unified_ids) != len(unified_rows):
        raise RuntimeError(
            "Unified intelligence interface contains duplicate or "
            "missing universal product IDs."
        )

    for key, (registry_path, _legacy_evaluation_path) in FILES.items():
        lane = LANE_NAMES[key]
        registry = read_csv(registry_path)

        evaluation = [
            row
            for row in unified_rows
            if first(row, "lane") == lane
        ]

        lane_counts[lane] = len(registry)

        evaluation_by_id = {
            source_id(row): row
            for row in evaluation
            if source_id(row)
        }

        if len(registry) != EXPECTED_COUNTS[key]:
            diagnostics.append({
                "lane": lane,
                "source_product_id": "",
                "diagnostic": f"REGISTRY_COUNT_{len(registry)}_EXPECTED_{EXPECTED_COUNTS[key]}",
            })

        for base in registry:
            sid = source_id(base)
            if not sid:
                diagnostics.append({
                    "lane": lane,
                    "source_product_id": "",
                    "diagnostic": "MISSING_SOURCE_PRODUCT_ID",
                })
                continue

            evaluation_row = evaluation_by_id.get(sid)
            if evaluation_row is None:
                diagnostics.append({
                    "lane": lane,
                    "source_product_id": sid,
                    "diagnostic": "MISSING_EVALUATION_ROW",
                })
                continue

            uid = universal_id(lane, sid)
            tcgid = tcgplayer_id(base) or tcgplayer_id(evaluation_row)
            name = first(
                base,
                "canonical_product_name",
                "product_name",
                "name",
                default=first(evaluation_row, "canonical_product_name", "product_name", "name"),
            )
            current_value = first(
                evaluation_row,
                "current_market_value_usd",
                "current_unit_value_usd",
                "market_value_usd",
                "current_price",
                "evaluated_market_value_usd",
                default=first(base, "current_market_value_usd"),
            )
            confidence = first(
                evaluation_row,
                "model_confidence_score",
                "confidence",
                default=first(base, "confidence"),
            )
            admission = first(
                evaluation_row,
                "evaluation_tier",
                "admission_tier",
                default=first(base, "admission_tier"),
            )
            forecast_status = first(
                evaluation_row,
                "forecast_status",
                default=first(base, "forecast_status"),
            )
            recommendation_status = first(
                evaluation_row,
                "recommendation_status",
                default=first(base, "recommendation_status"),
            )
            recommendation_action = first(
                evaluation_row,
                "guarded_recommendation",
                "recommendation_action",
                "action",
                default=first(base, "guarded_recommendation"),
            )

            asset_rows.append({
                "asset_id": uid,
                "asset_name": name,
                "asset_class": "MTG",
                "asset_subclass": lane,
                "source_product_id": sid,
                "tcgplayer_product_id": tcgid,
                "product_class": first(base, "product_class", default=lane),
                "canonical_set_name": first(base, "canonical_set_name", "set_name"),
                "release_date": first(base, "release_date"),
                "registry_status": first(base, "registry_status", default="GOVERNED"),
                "currency": first(base, "currency", default="USD"),
            })

            horizon_certified = normalize_bool(
                first(evaluation_row, "horizon_model_certified", default="NO")
            ) == "YES"

            forecast_rows.append({
                "asset_id": uid,
                "source_product_id": sid,
                "tcgplayer_product_id": tcgid,
                "forecast_eligible": normalize_bool(
                    first(evaluation_row, "forecast_eligible", default=forecast_status)
                ),
                "forecast_status": forecast_status,
                "forecast_method": first(
                    evaluation_row, "forecast_method", "valuation_method"
                ),
                "current_market_value_usd": current_value,
                "native_forecast_low_usd": first(
                    evaluation_row, "forecast_low_usd", "native_forecast_low_usd"
                ),
                "native_forecast_base_usd": first(
                    evaluation_row, "forecast_base_usd", "native_forecast_base_usd"
                ),
                "native_forecast_high_usd": first(
                    evaluation_row, "forecast_high_usd", "native_forecast_high_usd"
                ),
                "one_year_downside_usd": first(evaluation_row, "1y_downside_usd", "one_year_downside_usd") if horizon_certified else "",
                "one_year_base_usd": first(evaluation_row, "1y_base_usd", "one_year_base_usd") if horizon_certified else "",
                "one_year_upside_usd": first(evaluation_row, "1y_upside_usd", "one_year_upside_usd") if horizon_certified else "",
                "three_year_downside_usd": first(evaluation_row, "3y_downside_usd", "three_year_downside_usd") if horizon_certified else "",
                "three_year_base_usd": first(evaluation_row, "3y_base_usd", "three_year_base_usd") if horizon_certified else "",
                "three_year_upside_usd": first(evaluation_row, "3y_upside_usd", "three_year_upside_usd") if horizon_certified else "",
                "five_year_downside_usd": first(evaluation_row, "5y_downside_usd", "five_year_downside_usd") if horizon_certified else "",
                "five_year_base_usd": first(evaluation_row, "5y_base_usd", "five_year_base_usd") if horizon_certified else "",
                "five_year_upside_usd": first(evaluation_row, "5y_upside_usd", "five_year_upside_usd") if horizon_certified else "",
                "confidence": confidence,
                "currency": "USD",
            })

            eligible = (
                normalize_bool(
                    first(
                        evaluation_row,
                        "recommendation_eligible",
                        default="NO",
                    )
                )
                == "YES"
            )
            recommendation_rows.append({
                "asset_id": uid,
                "source_product_id": sid,
                "tcgplayer_product_id": tcgid,
                "recommendation_eligible": "YES" if eligible else "NO",
                "recommendation_status": recommendation_status,
                "recommendation_action": recommendation_action or "NO_ACTION",
                "recommendation_rationale": first(
                    evaluation_row, "rationale", "recommendation_rationale"
                ),
                "suppression_reason": first(
                    evaluation_row, "suppression_reason", "plausibility_flags"
                ),
                "confidence": confidence,
                "currency": "USD",
            })

            risk_rows.append({
                "asset_id": uid,
                "source_product_id": sid,
                "tcgplayer_product_id": tcgid,
                "admission_tier": admission,
                "quality_disposition": first(
                    evaluation_row,
                    "quality_disposition",
                    default=first(base, "quality_disposition"),
                ),
                "quality_flags": first(
                    evaluation_row,
                    "quality_flags",
                    "suppression_reason",
                    "plausibility_flags",
                ),
                "confidence": confidence,
                "forecast_eligible": normalize_bool(
                    first(evaluation_row, "forecast_eligible", default=forecast_status)
                ),
                "recommendation_eligible": "YES" if eligible else "NO",
            })

    asset_rows.sort(key=lambda row: (row["asset_subclass"], row["asset_name"], row["asset_id"]))

    positions_fields = [
        "position_id",
        "asset_id",
        "quantity",
        "unit_cost_usd",
        "cost_basis_usd",
        "current_unit_value_usd",
        "market_value_usd",
        "currency",
        "source_system",
    ]
    position_rows: list[dict[str, str]] = []

    aftermath_rows = [
        row
        for row in forecast_rows
        if row["source_product_id"] == "TCGCSV-22876-489207"
    ]

    if len(aftermath_rows) != 1:
        raise RuntimeError(
            "Expected exactly one hosted Aftermath forecast row."
        )

    aftermath = aftermath_rows[0]

    if aftermath["current_market_value_usd"] != "227.18":
        raise RuntimeError(
            "Hosted Aftermath current value regressed: "
            f"{aftermath['current_market_value_usd']}"
        )

    if aftermath["forecast_method"] != "NATIVE_MONTE_CARLO_RANGE":
        raise RuntimeError(
            "Hosted Aftermath forecast method regressed: "
            f"{aftermath['forecast_method']}"
        )

    if aftermath["native_forecast_base_usd"] != "340.58":
        raise RuntimeError(
            "Hosted Aftermath native forecast base regressed: "
            f"{aftermath['native_forecast_base_usd']}"
        )

    if any(
        aftermath[field]
        for field in (
            "one_year_base_usd",
            "three_year_base_usd",
            "five_year_base_usd",
        )
    ):
        raise RuntimeError(
            "Hosted Aftermath contains uncertified horizon values."
        )

    platform_rows = [{
        "platform": "MTG",
        "status": "PASS" if not diagnostics else "WARN",
        "interface_name": "mtg-hosted-uip-delivery-v1",
        "contract_version": "1",
        "products": str(len(asset_rows)),
        "forecast_eligible": str(sum(row["forecast_eligible"] == "YES" for row in forecast_rows)),
        "recommendation_eligible": str(sum(row["recommendation_eligible"] == "YES" for row in recommendation_rows)),
        "diagnostics": str(len(diagnostics)),
        "generated_at_utc": generated.isoformat(),
    }]

    write_csv(package / "asset_master.csv", asset_rows, list(asset_rows[0]))
    write_csv(package / "forecasts.csv", forecast_rows, list(forecast_rows[0]))
    write_csv(package / "recommendations.csv", recommendation_rows, list(recommendation_rows[0]))
    write_csv(package / "risk_metrics.csv", risk_rows, list(risk_rows[0]))
    write_csv(package / "portfolio_positions.csv", position_rows, positions_fields)
    write_csv(package / "platform_status.csv", platform_rows, list(platform_rows[0]))
    write_csv(
        package / "diagnostics.csv",
        diagnostics,
        ["lane", "source_product_id", "diagnostic"],
    )

    exported = [
        "asset_master.csv",
        "forecasts.csv",
        "recommendations.csv",
        "risk_metrics.csv",
        "portfolio_positions.csv",
        "platform_status.csv",
        "diagnostics.csv",
    ]

    manifest = {
        "status": "PASS" if len(asset_rows) == 1141 and not diagnostics else "WARN",
        "delivery_contract": "uip-mtg-delivery-v1",
        "package_id": package_id,
        "generated_at_utc": generated.isoformat(),
        "products": len(asset_rows),
        "lane_counts": lane_counts,
        "portfolio_positions": len(position_rows),
        "diagnostics": len(diagnostics),
        "files": {
            name: {
                "sha256": sha256(package / name),
                "size_bytes": (package / name).stat().st_size,
            }
            for name in exported
        },
    }
    (package / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (package / "package_summary.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    latest = output_root / "latest"
    if latest.exists():
        shutil.rmtree(latest)
    shutil.copytree(package, latest)

    latest_pointer = {
        "package_id": package_id,
        "delivery_directory": str(package),
        "manifest": str(package / "export_manifest.json"),
    }
    (output_root / "latest.json").write_text(
        json.dumps(latest_pointer, indent=2), encoding="utf-8"
    )

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the hosted MTG UIP delivery package.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build(args.output_root)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
