from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
from datetime import date, datetime, timezone
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
    # Plain reader: read_csv() enforces the certified-export columns, which the decisions file lacks.
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "secret_lair_id" not in reader.fieldnames or "call" not in reader.fieldnames:
            raise RuntimeError(f"Secret Lair v2 decisions lack secret_lair_id/call: {path}")
        decisions = {r.get("secret_lair_id", "").strip(): r for r in reader}
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


COLLECTOR_V2_DECISIONS = ROOT / "data" / "history" / "boxes" / "collector_v2_decisions.csv"
PRECOLLECTOR_V2_DECISIONS = ROOT / "data" / "history" / "boxes" / "precollector_v2_decisions.csv"
DAILY_PRICE_MAX_AGE_DAYS = 4   # same limit as the UIP's stale-decision check (MTG_DECISIONS_MAX_AGE_DAYS)
CERTIFIED_PRICE_SOURCE = "CERTIFIED_EXPORT"


def _precollector_product_id(native_asset_id: str) -> str:
    """The TCGplayer id in a Pre-Collector native id (tcgplayer:<id>)."""
    head, _, tail = native_asset_id.strip().partition(":")
    return tail.strip() if head.lower() == "tcgplayer" and tail.strip().isdigit() else ""


# lane -> (daily decisions file, its product id column, price column, price date column,
#          native_asset_id -> that product id, source label)
DAILY_PRICE_LANES = {
    "SECRET_LAIR_V1_1": (SECRET_LAIR_V2_DECISIONS, "secret_lair_id", "market_price", "as_of",
                         lambda native: native.strip(), "SECRET_LAIR_V2_DECISIONS_TCGPLAYER_MARKET"),
    "COLLECTOR_V1": (COLLECTOR_V2_DECISIONS, "tcgplayer_product_id", "market_price", "as_of",
                     tcgplayer_id, "COLLECTOR_V2_DECISIONS_TCGPLAYER_MARKET"),
    "PRE_COLLECTOR_V1": (PRECOLLECTOR_V2_DECISIONS, "tcgplayer_product_id", "price", "price_date",
                         _precollector_product_id, "PRECOLLECTOR_V2_DECISIONS_TCGPLAYER_MARKET"),
}


def _positive_price(value: str) -> str:
    try:
        number = float(str(value).strip())
    except ValueError:
        return ""
    return str(value).strip() if math.isfinite(number) and number > 0 else ""


def _fresh_date(value: str, today: date) -> str:
    """The ISO date when it is at most DAILY_PRICE_MAX_AGE_DAYS old (a day ahead tolerated), else ""."""
    try:
        day = date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return ""
    return day.isoformat() if -1 <= (today - day).days <= DAILY_PRICE_MAX_AGE_DAYS else ""


def _daily_decisions(path: Path, id_field: str) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or id_field not in reader.fieldnames:
            raise RuntimeError(f"Daily MTG decisions lack {id_field}: {path}")
        return {str(r.get(id_field) or "").strip(): r for r in reader if str(r.get(id_field) or "").strip()}


def refresh_daily_prices(rows: list[dict[str, str]], today: date | None = None,
                         lanes: dict[str, tuple] | None = None) -> dict[str, Any]:
    """Refresh current_price_usd from the daily model decisions; the certified price is the fallback.

    The certified Phase 9 export froze its prices on 2026-08-13. Every lane now has a daily decision
    file carrying today's TCGplayer market price (Secret Lair v2, Collector v2, Pre-Collector v2). A
    row takes that price when the decision has a positive price dated within DAILY_PRICE_MAX_AGE_DAYS;
    otherwise it keeps its certified price. Each row gains current_price_as_of (the price date, empty
    for a certified price) and current_price_source. Calls, ranks, purchase semantics and
    lane_authority_state are untouched, and so is the certified native authority file, which the UIP
    verifies byte for byte against the certified SHA-256.
    """
    today = today or datetime.now(timezone.utc).date()
    lanes = DAILY_PRICE_LANES if lanes is None else lanes
    loaded = {lane: _daily_decisions(spec[0], spec[1]) for lane, spec in lanes.items()}
    by_lane: dict[str, dict[str, int]] = {}
    for row in rows:
        lane = row.get("mtg_lane", "").strip()
        counts = by_lane.setdefault(lane, {"refreshed": 0, "certified": 0})
        row["current_price_as_of"] = ""
        row["current_price_source"] = CERTIFIED_PRICE_SOURCE if _positive_price(row.get("current_price_usd", "")) else ""
        spec = lanes.get(lane)
        decision = loaded.get(lane, {}).get(spec[4](row.get("native_asset_id", ""))) if spec else None
        price = _positive_price(decision.get(spec[2], "")) if decision else ""
        as_of = _fresh_date(decision.get(spec[3], ""), today) if price else ""
        if not as_of:
            counts["certified"] += 1
            continue
        row["current_price_usd"] = price
        row["current_price_as_of"] = as_of
        row["current_price_source"] = spec[5]
        counts["refreshed"] += 1
    return {"max_age_days": DAILY_PRICE_MAX_AGE_DAYS, "as_of_date": today.isoformat(),
            "refreshed": sum(c["refreshed"] for c in by_lane.values()),
            "certified_fallback": sum(c["certified"] for c in by_lane.values()),
            "by_lane": dict(sorted(by_lane.items())),
            "sources": {lane: str(spec[0].relative_to(ROOT)) if spec[0].is_relative_to(ROOT) else str(spec[0])
                        for lane, spec in sorted(lanes.items())}}


def build(output_root: Path) -> dict[str, Any]:
    generated = datetime.now(timezone.utc)
    rows = read_csv(CERTIFIED_PAYLOAD)
    validate_payload(rows)
    # Secret Lair model v2 overlay; off unless MTG_SECRET_LAIR_V2=1 (enabled with the UIP v2 projection).
    secret_lair_v2_rows = apply_secret_lair_v2(rows) if os.environ.get(SECRET_LAIR_V2_ENV) == "1" else 0
    print(f"Secret Lair v2 overlay rows: {secret_lair_v2_rows}")
    daily_prices = refresh_daily_prices(rows, today=generated.date())
    print(f"Daily price refresh: {json.dumps(daily_prices['by_lane'], sort_keys=True)}")

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
        daily_price = bool(row.get("current_price_as_of"))
        current_price_available = is_true(row["current_price_authority_available"]) or daily_price
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
            # What current_market_value_usd is as built here: a daily decision price or the certified one.
            # The live overlay may then replace the value; its market_source says which it kept.
            "current_price_as_of": row.get("current_price_as_of", "") if current_price_available else "",
            "current_price_source": row.get("current_price_source", "") if current_price_available else "",
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

    # Byte copy, never the refreshed rows: the UIP import verifies this file against the certified
    # SHA-256 and column list (mtg_v1_uip_export_manifest.json), so daily prices travel in forecasts.csv.
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
        "daily_price_refresh": daily_prices,
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
