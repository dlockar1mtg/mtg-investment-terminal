from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CERTIFIED_PAYLOAD = (
    ROOT
    / "docs"
    / "phase_9"
    / "uip_export"
    / "mtg_v1_uip_export_payload.csv"
)
CERTIFIED_MANIFEST = (
    ROOT
    / "docs"
    / "phase_9"
    / "uip_export"
    / "mtg_v1_uip_export_manifest.json"
)
DEFAULT_OUTPUT = ROOT / "data" / "operations" / "mtg_uip_delivery"

REQUIRED_FIELDS = [
    "mtg_asset_id",
    "mtg_lane",
    "native_asset_id",
    "product_name",
    "lane_authority_state",
    "current_price_usd",
    "current_price_authority_available",
    "forecast_authority_available",
    "forecast_1y_price_usd",
    "forecast_1y_return",
    "risk_authority_available",
    "native_rank",
    "native_rank_type",
    "native_purchase_status",
    "purchase_semantic",
    "evidence_state",
    "actionability_state",
    "execution_ready_purchase_certified",
    "manual_execution_price_check_required",
    "native_authority_pointer",
    "native_authority_sha256",
    "snapshot_population_is_permanent",
    "automatic_purchase_execution",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"CSV has no header: {path}")
        missing = [field for field in REQUIRED_FIELDS if field not in reader.fieldnames]
        if missing:
            raise RuntimeError(f"Certified MTG payload is missing fields: {missing}")
        return list(reader)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_true(value: str) -> bool:
    return str(value).strip().lower() == "true"


def tcgplayer_id(native_asset_id: str) -> str:
    marker = "TCGPLAYER-"
    upper = native_asset_id.upper()
    if marker not in upper:
        return ""
    value = native_asset_id[upper.rfind(marker) + len(marker):].strip()
    return value if value.isdigit() else ""


def validate_payload(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError("Certified MTG payload is empty.")

    asset_ids = [row["mtg_asset_id"].strip() for row in rows]
    if any(not asset_id for asset_id in asset_ids):
        raise RuntimeError("Certified MTG payload contains a missing mtg_asset_id.")
    if len(set(asset_ids)) != len(asset_ids):
        raise RuntimeError("Certified MTG payload contains duplicate mtg_asset_id values.")

    native_ids = [row["native_asset_id"].strip() for row in rows]
    if any(not native_id for native_id in native_ids):
        raise RuntimeError("Certified MTG payload contains a missing native_asset_id.")

    lanes = {row["mtg_lane"].strip() for row in rows}
    required_lanes = {"COLLECTOR_V1", "PRE_COLLECTOR_V1", "SECRET_LAIR_V1_1"}
    if lanes != required_lanes:
        raise RuntimeError(
            "Certified MTG payload lane set changed unexpectedly: "
            f"found={sorted(lanes)} expected={sorted(required_lanes)}"
        )

    if any(is_true(row["automatic_purchase_execution"]) for row in rows):
        raise RuntimeError("Certified MTG payload must not authorize automatic execution.")
    if any(is_true(row["execution_ready_purchase_certified"]) for row in rows):
        raise RuntimeError("Certified MTG payload must not certify execution-ready purchases.")


SECRET_LAIR_V2_DECISIONS = ROOT / "data" / "history" / "tcgcsv_weekly" / "secret_lair_v2_decisions.csv"
SECRET_LAIR_V2_ENV = "MTG_SECRET_LAIR_V2"
SECRET_LAIR_V2_STATUS = {
    "BUY": ("BUY_CANDIDATE_NOW", "MODEL_QUALIFIED_ENTRY_CANDIDATE", "true"),
    "WAIT": ("WAIT_FOR_LISTING_DISCOUNT", "MODEL_ENTRY_PRICE_CONDITION_NOT_SATISFIED", "false"),
    "NO_PRICE": ("NO_CURRENT_MARKET_PRICE", "MODEL_EVIDENCE_REVIEW_REQUIRED", "false"),
}


def apply_secret_lair_v2(rows: list[dict[str, str]], path: Path = SECRET_LAIR_V2_DECISIONS) -> int:
    """Secret Lair model v2 (scripts/build_secret_lair_v2_decisions.py) replaces the August calls.

    Priced products get the current market price, the v2 call and the v2 rank (expected 6-month
    return after selling costs). The August 1-year forecast is withdrawn: v2 forecasts 6 months and
    its details travel in the v2 decisions file. Safety fields keep their meaning: a BUY stays a
    model-qualified entry candidate with a manual price check and is never execution-ready.
    """
    if not path.is_file():
        return 0
    decisions = {r.get("secret_lair_id", "").strip(): r for r in read_csv(path)}
    applied = 0
    for row in rows:
        if row.get("mtg_lane", "").strip() != "SECRET_LAIR_V1_1":
            continue
        decision = decisions.get(row.get("native_asset_id", "").strip())
        if not decision or decision.get("call") not in SECRET_LAIR_V2_STATUS:
            continue
        status, semantic, manual_check = SECRET_LAIR_V2_STATUS[decision["call"]]
        row["native_purchase_status"] = status
        row["purchase_semantic"] = semantic
        row["manual_execution_price_check_required"] = manual_check
        row["native_rank_type"] = "SECRET_LAIR_V2_EXPECTED_NET_RETURN_6M"
        row["forecast_authority_available"] = "false"
        row["forecast_1y_price_usd"] = ""
        row["forecast_1y_return"] = ""
        if decision["call"] == "NO_PRICE":
            row["native_rank"] = ""
        else:
            row["current_price_usd"] = decision.get("market_price", "")
            row["current_price_authority_available"] = "true"
            row["native_rank"] = decision.get("rank", "")
        applied += 1
    return applied


def build(output_root: Path) -> dict[str, Any]:
    generated = datetime.now(timezone.utc)
    rows = read_csv(CERTIFIED_PAYLOAD)
    validate_payload(rows)
    # Secret Lair model v2 overlay; off unless MTG_SECRET_LAIR_V2=1 (enabled with the UIP v2 projection).
    secret_lair_v2_rows = apply_secret_lair_v2(rows) if os.environ.get(SECRET_LAIR_V2_ENV) == "1" else 0
    print(f"Secret Lair v2 overlay rows: {secret_lair_v2_rows}")

    source_manifest = json.loads(CERTIFIED_MANIFEST.read_text(encoding="utf-8"))
    package_id = generated.strftime("mtg-hosted-r2-%Y%m%dT%H%M%SZ")
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

    for row in rows:
        asset_id = row["mtg_asset_id"].strip()
        lane = row["mtg_lane"].strip()
        native_id = row["native_asset_id"].strip()
        name = row["product_name"].strip()
        tcgid = tcgplayer_id(native_id)
        lane_counts[lane] = lane_counts.get(lane, 0) + 1

        asset_rows.append({
            "asset_id": asset_id,
            "asset_name": name,
            "asset_class": "MTG",
            "asset_subclass": lane,
            "source_product_id": native_id,
            "tcgplayer_product_id": tcgid,
            "lane_authority_state": row["lane_authority_state"],
            "evidence_state": row["evidence_state"],
            "actionability_state": row["actionability_state"],
            "currency": "USD",
        })

        forecast_available = is_true(row["forecast_authority_available"])
        current_price_available = is_true(row["current_price_authority_available"])
        forecast_rows.append({
            "asset_id": asset_id,
            "source_product_id": native_id,
            "tcgplayer_product_id": tcgid,
            "forecast_eligible": "YES" if forecast_available else "NO",
            "forecast_status": (
                "CERTIFIED_NATIVE_1Y" if forecast_available else "NATIVE_FORECAST_UNAVAILABLE"
            ),
            "forecast_method": "NATIVE_CERTIFIED_1Y" if forecast_available else "",
            "current_market_value_usd": row["current_price_usd"] if current_price_available else "",
            "native_forecast_low_usd": "",
            "native_forecast_base_usd": row["forecast_1y_price_usd"] if forecast_available else "",
            "native_forecast_high_usd": "",
            "one_year_downside_usd": "",
            "one_year_base_usd": row["forecast_1y_price_usd"] if forecast_available else "",
            "one_year_upside_usd": "",
            "three_year_downside_usd": "",
            "three_year_base_usd": "",
            "three_year_upside_usd": "",
            "five_year_downside_usd": "",
            "five_year_base_usd": "",
            "five_year_upside_usd": "",
            "forecast_1y_return": row["forecast_1y_return"] if forecast_available else "",
            "currency": "USD",
        })

        native_purchase_status = row["native_purchase_status"].strip()
        recommendation_rows.append({
            "asset_id": asset_id,
            "source_product_id": native_id,
            "tcgplayer_product_id": tcgid,
            "recommendation_eligible": "YES" if native_purchase_status else "NO",
            "recommendation_status": native_purchase_status,
            "recommendation_action": native_purchase_status or "NO_NATIVE_STATUS",
            "native_purchase_status": native_purchase_status,
            "purchase_semantic": row["purchase_semantic"],
            "actionability_state": row["actionability_state"],
            "execution_ready_purchase_certified": row["execution_ready_purchase_certified"],
            "manual_execution_price_check_required": row["manual_execution_price_check_required"],
            "automatic_purchase_execution": row["automatic_purchase_execution"],
            "currency": "USD",
        })

        risk_rows.append({
            "asset_id": asset_id,
            "source_product_id": native_id,
            "tcgplayer_product_id": tcgid,
            "risk_authority_available": row["risk_authority_available"],
            "native_rank": row["native_rank"],
            "native_rank_type": row["native_rank_type"],
            "evidence_state": row["evidence_state"],
            "actionability_state": row["actionability_state"],
        })

    asset_rows.sort(key=lambda item: (item["asset_subclass"], item["asset_name"], item["asset_id"]))

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

    platform_rows = [{
        "platform": "MTG",
        "status": "PASS",
        "interface_name": "mtg-hosted-uip-delivery-v2",
        "contract_version": "2",
        "products": str(len(asset_rows)),
        "forecast_eligible": str(sum(row["forecast_eligible"] == "YES" for row in forecast_rows)),
        "recommendation_rows": str(len(recommendation_rows)),
        "diagnostics": "0",
        "semantic_authority": "mtg_native_authority.csv",
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

    shutil.copy2(CERTIFIED_PAYLOAD, package / "mtg_native_authority.csv")
    shutil.copy2(CERTIFIED_MANIFEST, package / "mtg_native_authority_manifest.json")

    exported = [
        "asset_master.csv",
        "forecasts.csv",
        "recommendations.csv",
        "risk_metrics.csv",
        "portfolio_positions.csv",
        "platform_status.csv",
        "diagnostics.csv",
        "mtg_native_authority.csv",
        "mtg_native_authority_manifest.json",
    ]

    manifest = {
        "status": "PASS",
        "delivery_contract": "uip-mtg-delivery-v2",
        "package_id": package_id,
        "generated_at_utc": generated.isoformat(),
        "products": len(asset_rows),
        "lane_counts": lane_counts,
        "portfolio_positions": 0,
        "diagnostics": 0,
        "semantic_authority_file": "mtg_native_authority.csv",
        "semantic_authority_sha256": sha256(package / "mtg_native_authority.csv"),
        "source_manifest_status": source_manifest.get("status", ""),
        "snapshot_population_is_permanent": False,
        "automatic_purchase_execution": False,
        "execution_ready_purchase_certified": False,
        "generic_surfaces_are_semantic_authority": False,
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
        "semantic_authority": str(package / "mtg_native_authority.csv"),
    }
    (output_root / "latest.json").write_text(
        json.dumps(latest_pointer, indent=2), encoding="utf-8"
    )

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the hosted MTG UIP delivery package from certified Phase 9 authority.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build(args.output_root)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
