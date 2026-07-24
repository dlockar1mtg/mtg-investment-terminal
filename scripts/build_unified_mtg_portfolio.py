from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path.cwd()
VALIDATION_ROOT = ROOT / "data" / "validation" / "phase_10"
UNIFIED_REGISTRY_PATH = VALIDATION_ROOT / "unified_mtg_registry" / "unified_mtg_product_registry.csv"
SECRET_PORTFOLIO_PATH = VALIDATION_ROOT / "ebay_matching" / "production_refresh" / "owned_portfolio" / "secret_lair_owned_portfolio_positions.csv"
COLLECTOR_PORTFOLIO_PATH = VALIDATION_ROOT / "collector_booster_boxes" / "owned_portfolio" / "collector_booster_box_portfolio_positions.csv"
PRE_COLLECTOR_PORTFOLIO_PATH = VALIDATION_ROOT / "pre_collector_booster_boxes" / "owned_portfolio" / "pre_collector_booster_box_owned_positions.csv"
OUTPUT_ROOT = VALIDATION_ROOT / "unified_mtg_portfolio"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def decimal_or_zero(value: str | None) -> Decimal:
    cleaned = str(value or "").strip()
    if not cleaned:
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def money(value: Decimal | int | float | str) -> str:
    normalized = Decimal(str(value))
    return f"{normalized.quantize(Decimal('0.01')):.2f}"


def decimal_sum(values) -> Decimal:
    return sum(values, Decimal("0"))


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    registry_rows = read_csv(UNIFIED_REGISTRY_PATH)
    secret_rows = read_csv(SECRET_PORTFOLIO_PATH)
    collector_rows = read_csv(COLLECTOR_PORTFOLIO_PATH)
    pre_collector_rows = read_csv(PRE_COLLECTOR_PORTFOLIO_PATH)

    registry_by_lane_source = {
        (row["lane"].strip(), row["source_product_id"].strip()): row
        for row in registry_rows
    }

    unified_positions: list[dict[str, str]] = []
    diagnostics: list[dict[str, str]] = []

    def append_position(
        *,
        lane: str,
        source_product_id: str,
        canonical_product_name: str,
        quantity: Decimal,
        acquisition_date: str,
        total_cost_basis: Decimal,
        unit_market_value: Decimal,
        total_market_value: Decimal,
        unrealized_gain_loss: Decimal,
        admission_tier: str,
        forecast_status: str,
        recommendation_status: str,
        recommendation_action: str,
        recommendation_eligible: str,
        source_holding_id: str,
    ) -> None:
        registry = registry_by_lane_source.get((lane, source_product_id))
        if registry is None:
            diagnostics.append({
                "lane": lane,
                "source_product_id": source_product_id,
                "diagnostic": "MISSING_UNIFIED_REGISTRY_ROW",
            })
            return

        unified_positions.append({
            "universal_mtg_product_id": registry["universal_mtg_product_id"],
            "lane": lane,
            "source_product_id": source_product_id,
            "source_holding_id": source_holding_id,
            "canonical_product_name": canonical_product_name or registry["canonical_product_name"],
            "product_class": registry["product_class"],
            "quantity": str(quantity),
            "acquisition_date": acquisition_date,
            "total_cost_basis_usd": money(total_cost_basis),
            "unit_market_value_usd": money(unit_market_value),
            "total_market_value_usd": money(total_market_value),
            "unrealized_gain_loss_usd": money(unrealized_gain_loss),
            "admission_tier": admission_tier or registry["admission_tier"],
            "forecast_status": forecast_status or registry["forecast_status"],
            "recommendation_status": recommendation_status or registry["recommendation_status"],
            "recommendation_action": recommendation_action,
            "recommendation_eligible": recommendation_eligible,
            "currency": "USD",
        })

    for row in secret_rows:
        action = row.get("guarded_recommendation", "").strip()
        append_position(
            lane="SECRET_LAIR",
            source_product_id=row["investment_product_id"].strip(),
            canonical_product_name=row.get("canonical_product_name", "").strip(),
            quantity=decimal_or_zero(row.get("quantity")),
            acquisition_date=row.get("acquisition_date", "").strip(),
            total_cost_basis=decimal_or_zero(row.get("acquisition_cost_total")),
            unit_market_value=decimal_or_zero(row.get("current_modeled_unit_value_usd")),
            total_market_value=decimal_or_zero(row.get("current_modeled_value_usd")),
            unrealized_gain_loss=decimal_or_zero(row.get("unrealized_gain_usd")),
            admission_tier=row.get("evaluation_tier", "").strip(),
            forecast_status="",
            recommendation_status="",
            recommendation_action=action,
            recommendation_eligible="YES" if action not in {"", "NO_ACTION"} else "NO",
            source_holding_id="",
        )

    for row in collector_rows:
        append_position(
            lane="COLLECTOR_BOOSTER_BOX",
            source_product_id=row["canonical_product_id"].strip(),
            canonical_product_name=row.get("canonical_product_name", "").strip(),
            quantity=decimal_or_zero(row.get("quantity")),
            acquisition_date=row.get("acquisition_date", "").strip(),
            total_cost_basis=decimal_or_zero(row.get("total_cost_basis_usd")),
            unit_market_value=decimal_or_zero(row.get("unit_market_value_usd")),
            total_market_value=decimal_or_zero(row.get("total_market_value_usd")),
            unrealized_gain_loss=decimal_or_zero(row.get("unrealized_gain_loss_usd")),
            admission_tier=row.get("admission_tier", "").strip(),
            forecast_status=row.get("forecast_status", "").strip(),
            recommendation_status=row.get("recommendation_status", "").strip(),
            recommendation_action=row.get("recommendation_action", "").strip(),
            recommendation_eligible=row.get("recommendation_eligible", "").strip(),
            source_holding_id=row.get("holding_id", "").strip(),
        )

    for row in pre_collector_rows:
        source_id = row.get("canonical_product_id", "").strip()
        if not source_id:
            diagnostics.append({
                "lane": "PRE_COLLECTOR_BOOSTER_BOX",
                "source_product_id": "",
                "diagnostic": "BLANK_SOURCE_PRODUCT_ID",
            })
            continue
        append_position(
            lane="PRE_COLLECTOR_BOOSTER_BOX",
            source_product_id=source_id,
            canonical_product_name=row.get("canonical_product_name", "").strip(),
            quantity=decimal_or_zero(row.get("quantity")),
            acquisition_date=row.get("acquisition_date", "").strip(),
            total_cost_basis=decimal_or_zero(row.get("total_cost_basis_usd")),
            unit_market_value=decimal_or_zero(row.get("current_unit_value_usd")),
            total_market_value=decimal_or_zero(row.get("modeled_market_value_usd")),
            unrealized_gain_loss=decimal_or_zero(row.get("unrealized_gain_loss_usd")),
            admission_tier=row.get("admission_tier", "").strip(),
            forecast_status=row.get("forecast_eligible", "").strip(),
            recommendation_status=row.get("recommendation_eligible", "").strip(),
            recommendation_action=row.get("recommendation_action", "").strip(),
            recommendation_eligible=row.get("recommendation_eligible", "").strip(),
            source_holding_id="",
        )

    unified_positions.sort(key=lambda row: (row["lane"], row["canonical_product_name"], row["source_product_id"]))
    lane_counts = Counter(row["lane"] for row in unified_positions)

    total_quantity = decimal_sum(decimal_or_zero(row["quantity"]) for row in unified_positions)
    total_cost_basis = decimal_sum(decimal_or_zero(row["total_cost_basis_usd"]) for row in unified_positions)
    total_market_value = decimal_sum(decimal_or_zero(row["total_market_value_usd"]) for row in unified_positions)
    total_unrealized = decimal_sum(decimal_or_zero(row["unrealized_gain_loss_usd"]) for row in unified_positions)
    reconciled_unrealized = total_market_value - total_cost_basis

    lane_summary_rows: list[dict[str, str]] = []
    for lane in ("SECRET_LAIR", "COLLECTOR_BOOSTER_BOX", "PRE_COLLECTOR_BOOSTER_BOX"):
        lane_rows = [row for row in unified_positions if row["lane"] == lane]
        lane_summary_rows.append({
            "lane": lane,
            "owned_positions": str(len(lane_rows)),
            "owned_quantity": str(decimal_sum(decimal_or_zero(row["quantity"]) for row in lane_rows)),
            "cost_basis_usd": money(decimal_sum(decimal_or_zero(row["total_cost_basis_usd"]) for row in lane_rows)),
            "market_value_usd": money(decimal_sum(decimal_or_zero(row["total_market_value_usd"]) for row in lane_rows)),
            "unrealized_gain_loss_usd": money(decimal_sum(decimal_or_zero(row["unrealized_gain_loss_usd"]) for row in lane_rows)),
        })

    universal_ids = [row["universal_mtg_product_id"] for row in unified_positions]
    checks = {
        "registry_products_equal_1141": len(registry_rows) == 1141,
        "secret_input_positions_equal_12": len(secret_rows) == 12,
        "collector_input_positions_equal_2": len(collector_rows) == 2,
        "pre_collector_input_positions_equal_0": len(pre_collector_rows) == 0,
        "unified_positions_equal_14": len(unified_positions) == 14,
        "secret_positions_equal_12": lane_counts["SECRET_LAIR"] == 12,
        "collector_positions_equal_2": lane_counts["COLLECTOR_BOOSTER_BOX"] == 2,
        "pre_collector_positions_equal_0": lane_counts["PRE_COLLECTOR_BOOSTER_BOX"] == 0,
        "all_positions_resolve_to_registry": len(diagnostics) == 0,
        "universal_ids_populated": all(universal_ids),
        "currency_usd_all_positions": all(row["currency"] == "USD" for row in unified_positions),
        "quantity_positive_all_positions": all(decimal_or_zero(row["quantity"]) > 0 for row in unified_positions),
        "cost_basis_nonnegative": all(decimal_or_zero(row["total_cost_basis_usd"]) >= 0 for row in unified_positions),
        "market_value_nonnegative": all(decimal_or_zero(row["total_market_value_usd"]) >= 0 for row in unified_positions),
        "portfolio_gain_reconciles": abs(total_unrealized - reconciled_unrealized) <= Decimal("0.05"),
        "quota_calls_zero": True,
    }
    status = "CERTIFIED" if all(checks.values()) else "FAILED"

    position_path = OUTPUT_ROOT / "unified_mtg_owned_positions.csv"
    summary_path = OUTPUT_ROOT / "unified_mtg_portfolio_lane_summary.csv"
    diagnostics_path = OUTPUT_ROOT / "unified_mtg_portfolio_diagnostics.csv"

    with position_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "universal_mtg_product_id", "lane", "source_product_id", "source_holding_id",
            "canonical_product_name", "product_class", "quantity", "acquisition_date",
            "total_cost_basis_usd", "unit_market_value_usd", "total_market_value_usd",
            "unrealized_gain_loss_usd", "admission_tier", "forecast_status",
            "recommendation_status", "recommendation_action", "recommendation_eligible", "currency",
        ])
        writer.writeheader()
        writer.writerows(unified_positions)

    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "lane", "owned_positions", "owned_quantity", "cost_basis_usd",
            "market_value_usd", "unrealized_gain_loss_usd",
        ])
        writer.writeheader()
        writer.writerows(lane_summary_rows)

    with diagnostics_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["lane", "source_product_id", "diagnostic"])
        writer.writeheader()
        writer.writerows(diagnostics)

    manifest = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "10.9.2",
        "registry_products": len(registry_rows),
        "owned_positions": len(unified_positions),
        "lane_position_counts": dict(sorted(lane_counts.items())),
        "owned_quantity": float(total_quantity),
        "cost_basis_usd": float(total_cost_basis),
        "market_value_usd": float(total_market_value),
        "unrealized_gain_loss_usd": float(total_unrealized),
        "reconciled_unrealized_gain_loss_usd": float(reconciled_unrealized),
        "diagnostics": len(diagnostics),
        "checks": checks,
        "quota_calls": 0,
        "source_sha256": {
            "unified_registry": hashlib.sha256(UNIFIED_REGISTRY_PATH.read_bytes()).hexdigest(),
            "secret_lair_portfolio": hashlib.sha256(SECRET_PORTFOLIO_PATH.read_bytes()).hexdigest(),
            "collector_portfolio": hashlib.sha256(COLLECTOR_PORTFOLIO_PATH.read_bytes()).hexdigest(),
            "pre_collector_portfolio": hashlib.sha256(PRE_COLLECTOR_PORTFOLIO_PATH.read_bytes()).hexdigest(),
        },
        "outputs": {
            "positions": str(position_path.resolve()),
            "lane_summary": str(summary_path.resolve()),
            "diagnostics": str(diagnostics_path.resolve()),
        },
    }

    (OUTPUT_ROOT / "unified_mtg_portfolio_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    lines = [
        "# Phase 10.9.2 Unified MTG Portfolio Certification",
        "",
        f"**Status:** {status}",
        "",
        f"- Unified registry products: {len(registry_rows)}",
        f"- Owned positions: {len(unified_positions)}",
        f"- Secret Lair positions: {lane_counts['SECRET_LAIR']}",
        f"- Collector Booster Box positions: {lane_counts['COLLECTOR_BOOSTER_BOX']}",
        f"- Pre-Collector Booster Box positions: {lane_counts['PRE_COLLECTOR_BOOSTER_BOX']}",
        f"- Owned quantity: {total_quantity}",
        f"- Cost basis: ${money(total_cost_basis)}",
        f"- Modeled market value: ${money(total_market_value)}",
        f"- Unrealized gain/loss: ${money(total_unrealized)}",
        f"- Diagnostics: {len(diagnostics)}",
        "- API quota calls: 0",
        "",
        "## Checks",
        "",
        *[f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items()],
        "",
    ]
    (OUTPUT_ROOT / "PHASE_10_9_2_UNIFIED_MTG_PORTFOLIO_CERTIFICATION.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"PHASE 10.9.2 UNIFIED MTG PORTFOLIO: {status}")
    print(json.dumps(manifest, indent=2))
    return 0 if status == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
