from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = ROOT / "data" / "operations" / "mtg_uip_delivery" / "latest"
DEFAULT_MARKET = ROOT / "data" / "operations" / "mtg_marketplace"

ID_FIELDS = (
    "source_product_id", "investment_product_id", "canonical_product_id",
    "product_id", "tcgplayer_product_id", "asset_id",
)
PRICE_FIELDS = (
    "consolidated_market_price_usd", "consolidated_market_price",
    "consolidated_price_usd", "consolidated_price",
    "market_price_usd", "median_price_usd", "current_price_usd",
    "current_price", "price_usd", "price",
)
SIGNAL_FIELDS = ("signal", "recommendation_action", "action", "recommendation")
CONFIDENCE_FIELDS = ("confidence", "confidence_score", "model_confidence_score")
OBSERVED_FIELDS = (
    "observed_at_utc", "observation_timestamp", "collected_at_utc",
    "generated_at_utc", "as_of_utc",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def first(row: dict[str, str], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = str(row.get(field, "") or "").strip()
        if value:
            return value
    return ""


def identifiers(row: dict[str, str]) -> set[str]:
    found: set[str] = set()
    for field in ID_FIELDS:
        value = str(row.get(field, "") or "").strip()
        if not value:
            continue
        found.add(value)
        if value.startswith("MTG:"):
            found.add(value.rsplit(":", 1)[-1])
        trailing_numeric = re.search(r"(?:^|[-:])([0-9]+)$", value)
        if trailing_numeric:
            found.add(trailing_numeric.group(1))
    return found


def build_asset_aliases(
    assets: list[dict[str, str]],
) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for asset in assets:
        asset_id = str(asset.get("asset_id", "") or "").strip()
        if asset_id:
            aliases[asset_id] = identifiers(asset)
    return aliases


def row_identifiers(
    row: dict[str, str],
    asset_aliases: dict[str, set[str]],
) -> set[str]:
    found = identifiers(row)
    asset_id = str(row.get("asset_id", "") or "").strip()
    if asset_id:
        found.update(asset_aliases.get(asset_id, set()))
    return found


def index_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        for identifier in identifiers(row):
            index[identifier] = row
    return index


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Overlay certified live MTG marketplace data onto the hosted UIP package.")
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET)
    args = parser.parse_args()

    package = args.package.resolve()
    market = args.market_root.resolve()
    prices_path = market / "consolidated_marketplace_prices.csv"
    decisions_path = market / "certified_marketplace_decisions.csv"
    quality_path = market / "marketplace_quality_certification.json"
    decision_summary_path = market / "marketplace_decision_summary.json"

    required = (
        package / "asset_master.csv",
        package / "forecasts.csv",
        package / "recommendations.csv",
        package / "risk_metrics.csv",
        package / "platform_status.csv",
        package / "package_summary.json",
        package / "export_manifest.json",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("Hosted MTG package is incomplete: " + ", ".join(missing))

    price_rows = read_csv(prices_path)
    decision_rows = read_csv(decisions_path)
    if not price_rows or not decision_rows:
        raise SystemExit("Live MTG overlay requires consolidated prices and certified decisions.")

    price_index = index_rows(price_rows)
    decision_index = index_rows(decision_rows)

    forecasts = read_csv(package / "forecasts.csv")
    recommendations = read_csv(package / "recommendations.csv")
    risks = read_csv(package / "risk_metrics.csv")
    assets = read_csv(package / "asset_master.csv")

    generated = datetime.now(timezone.utc).isoformat()
    live_price_count = 0
    live_decision_count = 0
    live_asset_ids: set[str] = set()
    asset_aliases = build_asset_aliases(assets)

    for row in forecasts:
        ids = row_identifiers(row, asset_aliases)
        match = next((price_index[item] for item in ids if item in price_index), None)
        if match:
            price = first(match, PRICE_FIELDS)
            if price:
                row["current_market_value_usd"] = price
                row["market_data_status"] = "LIVE_CERTIFIED"
                row["market_observed_at_utc"] = first(match, OBSERVED_FIELDS) or generated
                row["market_source"] = first(match, ("source", "marketplace", "source_system")) or "CERTIFIED_MARKETPLACE"
                live_price_count += 1
                asset_id = str(row.get("asset_id", "") or "").strip()
                if asset_id:
                    live_asset_ids.add(asset_id)
                continue
        row["market_data_status"] = "BASELINE_FALLBACK"
        row["market_observed_at_utc"] = ""
        row["market_source"] = "PHASE_10_CERTIFIED_BASELINE"

    for row in recommendations:
        ids = row_identifiers(row, asset_aliases)
        match = next((decision_index[item] for item in ids if item in decision_index), None)
        if match:
            signal = first(match, SIGNAL_FIELDS)
            if signal:
                row["recommendation_action"] = signal
                row["recommendation_status"] = "LIVE_CERTIFIED"
                row["recommendation_eligible"] = "NO" if signal.upper() in {"", "WATCH", "NO_ACTION"} else "YES"
                confidence = first(match, CONFIDENCE_FIELDS)
                if confidence:
                    row["confidence"] = confidence
                row["decision_observed_at_utc"] = first(match, OBSERVED_FIELDS) or generated
                row["decision_source"] = "CERTIFIED_MARKETPLACE"
                live_decision_count += 1
                asset_id = str(row.get("asset_id", "") or "").strip()
                if asset_id:
                    live_asset_ids.add(asset_id)
                continue
        row["decision_observed_at_utc"] = ""
        row["decision_source"] = "PHASE_10_CERTIFIED_BASELINE"

    if live_price_count < 1:
        print("MTG LIVE UIP OVERLAY: FAILED - CERTIFIED PRICES DID NOT APPLY")
        return 2
    if live_decision_count < 1:
        print("MTG LIVE UIP OVERLAY: FAILED - CERTIFIED DECISIONS DID NOT APPLY")
        return 2

    for row in risks:
        asset_id = str(row.get("asset_id", "") or "").strip()
        row["market_data_status"] = (
            "LIVE_CERTIFIED" if asset_id in live_asset_ids else "BASELINE_FALLBACK"
        )

    for row in assets:
        asset_id = str(row.get("asset_id", "") or "").strip()
        is_live = asset_id in live_asset_ids
        row["market_data_status"] = "LIVE_CERTIFIED" if is_live else "BASELINE_FALLBACK"
        row["last_market_refresh_at_utc"] = generated if is_live else ""

    write_csv(package / "asset_master.csv", assets)
    write_csv(package / "forecasts.csv", forecasts)
    write_csv(package / "recommendations.csv", recommendations)
    write_csv(package / "risk_metrics.csv", risks)

    summary = json.loads((package / "package_summary.json").read_text(encoding="utf-8"))
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.is_file() else {}
    decision_summary = json.loads(decision_summary_path.read_text(encoding="utf-8")) if decision_summary_path.is_file() else {}

    summary["live_overlay"] = {
        "status": "PASS",
        "applied_at_utc": generated,
        "certified_price_rows_available": len(price_rows),
        "certified_decision_rows_available": len(decision_rows),
        "products_with_live_prices": live_price_count,
        "products_with_live_decisions": live_decision_count,
        "products_with_any_live_overlay": len(live_asset_ids),
        "products_using_baseline_fallback": max(
            0,
            int(summary.get("products", 0)) - len(live_asset_ids),
        ),
        "quality_status": quality.get("status", ""),
        "decision_status": decision_summary.get("status", ""),
        "price_source": str(prices_path),
        "decision_source": str(decisions_path),
    }

    exported = [
        "asset_master.csv", "forecasts.csv", "recommendations.csv",
        "risk_metrics.csv", "portfolio_positions.csv", "platform_status.csv",
        "diagnostics.csv",
    ]
    summary["files"] = {
        name: {
            "sha256": sha256(package / name),
            "size_bytes": (package / name).stat().st_size,
        }
        for name in exported if (package / name).is_file()
    }
    (package / "package_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (package / "export_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    history = package.parent / "history" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    history.parent.mkdir(parents=True, exist_ok=True)
    if history.exists():
        shutil.rmtree(history)
    shutil.copytree(package, history)

    print(json.dumps(summary["live_overlay"], indent=2))
    print("MTG LIVE UIP OVERLAY: PASS")
    print(f"Historical snapshot: {history}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
