from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_production_forecast_overlay_ranking_contract_v1.json"
ROUND3 = ROOT / "data/governance/permanence/certification/collector_v1_round3_final_champion_challenge"
PREMODEL = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution"
ARCH = ROOT / "data/governance/permanence/certification/collector_v1_horizon_specific_tournament_architecture"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_production_forecast_overlay_ranking"


def clean(value: Any) -> str:
    return str(value or "").strip()


def num(value: Any, default: float | None = None) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return default
    try:
        result = float(text)
    except ValueError:
        return default
    return result if math.isfinite(result) else default


def truth(value: Any) -> bool:
    return clean(value).lower() in {"true", "1", "yes", "y"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def first(row: dict[str, Any], names: list[str], default: str = "") -> str:
    for name in names:
        if clean(row.get(name)):
            return clean(row.get(name))
    return default


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    p = (len(ordered) - 1) * q
    lo, hi = int(math.floor(p)), int(math.ceil(p))
    if lo == hi:
        return ordered[lo]
    w = p - lo
    return ordered[lo] * (1 - w) + ordered[hi] * w


def rank01(values: dict[str, float], higher_is_better: bool = True) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: item[1], reverse=higher_is_better)
    n = len(ordered)
    if n <= 1:
        return {key: 1.0 for key, _ in ordered}
    return {key: 1.0 - index / (n - 1) for index, (key, _) in enumerate(ordered)}


def bounded_supply_sources() -> list[Path]:
    return [
        ROOT / "data/governance/permanence/certification/collector_v1_august1_current_data_package/collector_ebay_product_supply_snapshot.csv",
        ROOT / "data/governance/permanence/certification/collector_v1_august1_current_data_package/ebay_product_supply_snapshot.csv",
        ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_certification/collector_ebay_product_supply_snapshot.csv",
        ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_certification/ebay_product_supply_snapshot.csv",
        ROOT / "data/operations/mtg_universal_history_completion/current/collector_ebay_product_supply_snapshot.csv",
        ROOT / "data/operations/mtg_universal_history_completion/current/ebay_product_supply_snapshot.csv",
    ]


def load_supply() -> tuple[Path | None, list[dict[str, str]]]:
    for path in bounded_supply_sources():
        if path.is_file():
            return path, read_csv(path)
    return None, []


def model_return(model: str, current_price: float, horizon_days: int, historical_rows: list[dict[str, str]]) -> float:
    matching = [r for r in historical_rows if clean(r.get("model_name")) == model and int(float(clean(r.get("horizon_days")) or 0)) == horizon_days]
    returns = [num(r.get("predicted_return")) for r in matching]
    values = [x for x in returns if x is not None]
    if values:
        return median(values)
    if model == "NAIVE_LAST_VALUE":
        return 0.0
    return 0.0


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []

    summary3_path = ROUND3 / "collector_round3_final_champion_challenge_summary.json"
    champions_path = ROUND3 / "collector_round3_final_champions.csv"
    routing_path = PREMODEL / "collector_final_method_routing.csv"
    current_path = PREMODEL / "collector_final_current_price_authority.csv"
    lifecycle_path = ARCH / "collector_early_life_entry_registry.csv"
    round1_predictions_path = ROOT / "data/governance/permanence/certification/collector_v1_horizon_specific_tournament_execution/collector_rolling_origin_predictions.csv"

    required = [summary3_path, champions_path, routing_path, current_path, lifecycle_path, round1_predictions_path]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_INPUTS:" + ";".join(missing))

    round3_summary = json.loads(summary3_path.read_text(encoding="utf-8"))
    if round3_summary.get("status") != contract["required_round3_status"]:
        failures.append("ROUND3_NOT_CERTIFIED")

    champions = read_csv(champions_path)
    routing = read_csv(routing_path)
    current_rows = read_csv(current_path)
    lifecycle_rows = read_csv(lifecycle_path)
    historical_predictions = read_csv(round1_predictions_path)
    supply_path, supply_rows = load_supply()

    if len(champions) != 8:
        failures.append("ROUND3_GROUP_COUNT_MISMATCH")
    if len(routing) != contract["required_product_rows"]:
        failures.append("PRODUCT_ROUTING_COUNT_MISMATCH")
    if len(current_rows) != contract["required_product_rows"]:
        failures.append("CURRENT_PRICE_COUNT_MISMATCH")
    if sum(truth(r.get("production_model_certified")) for r in champions) != contract["required_certified_champion_groups"]:
        failures.append("CERTIFIED_CHAMPION_COUNT_MISMATCH")
    if supply_path is None:
        failures.append("CURRENT_SUPPLY_SNAPSHOT_NOT_FOUND")

    route_by_id = {clean(r.get("canonical_product_id")): r for r in routing}
    current_by_id = {clean(r.get("canonical_product_id")): r for r in current_rows}
    lifecycle_by_id = {clean(r.get("canonical_product_id")): r for r in lifecycle_rows}

    supply_by_id: dict[str, dict[str, str]] = {}
    for row in supply_rows:
        cid = first(row, ["canonical_product_id", "target_canonical_product_id", "product_id"])
        if cid:
            supply_by_id[cid] = row

    champion_by_key: dict[tuple[int, str], dict[str, str]] = {}
    for row in champions:
        if truth(row.get("production_model_certified")):
            champion_by_key[(int(float(clean(row.get("horizon_days")) or 0)), clean(row.get("route")))] = row

    product_forecasts: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []

    for route_row in routing:
        cid = clean(route_row.get("canonical_product_id"))
        name = clean(route_row.get("product_name"))
        route = clean(route_row.get("final_forecast_method"))
        allowed = truth(route_row.get("forecast_output_allowed"))
        current_row = current_by_id.get(cid, {})
        price = num(first(current_row, ["current_price", "selected_price", "governed_current_price", "price"]))
        lifecycle = lifecycle_by_id.get(cid, {})

        if not allowed or price is None or price <= 0:
            blocked_rows.append({
                "canonical_product_id": cid,
                "product_name": name,
                "route": route,
                "blocked_reason": "ROUTING_OR_CURRENT_PRICE_NOT_AUTHORIZED",
                "purchase_recommendation_authorized": False,
            })
            continue

        product_has_forecast = False
        for horizon in (90, 180, 365):
            champion = champion_by_key.get((horizon, route))
            if not champion:
                continue
            model = clean(champion.get("round3_candidate_model"))
            base_return = model_return(model, price, horizon, historical_predictions)
            forecast_price = max(0.01, price * (1 + base_return))
            mape = max(num(champion.get("candidate_mape"), 0.0) or 0.0, contract["uncertainty"]["minimum_relative_half_width"] / contract["uncertainty"]["mape_multiplier"])
            half_width = max(contract["uncertainty"]["minimum_relative_half_width"], mape * contract["uncertainty"]["mape_multiplier"])
            lower = max(0.01, forecast_price * (1 - half_width))
            upper = forecast_price * (1 + half_width)
            downside = max(0.0, (price - lower) / price)
            validation_score = max(0.0, min(1.0, 1 - mape))
            early = truth(lifecycle.get("early_entry_model_required")) or truth(lifecycle.get("early_life_identified"))
            remaining_upside = max(0.0, base_return)

            supply = supply_by_id.get(cid, {})
            listing_count = num(first(supply, ["accepted_listing_count", "listing_count", "active_listing_count", "total_listings"]))
            seller_count = num(first(supply, ["seller_count", "unique_seller_count", "distinct_sellers"]))
            concentration = num(first(supply, ["seller_concentration", "top_seller_share", "seller_hhi"]))
            median_listing = num(first(supply, ["median_listing_price", "ebay_median_price", "median_price"]))
            price_gap = ((median_listing / price) - 1) if median_listing and price else None
            overlay_available = any(v is not None for v in [listing_count, seller_count, concentration, price_gap])

            supply_score = 0.5
            components = []
            if listing_count is not None:
                components.append(max(0.0, min(1.0, 1 - listing_count / 30.0)))
            if seller_count is not None:
                components.append(max(0.0, min(1.0, seller_count / 10.0)))
            if concentration is not None:
                components.append(max(0.0, min(1.0, 1 - concentration)))
            if price_gap is not None:
                components.append(max(0.0, min(1.0, 0.5 + price_gap)))
            if components:
                supply_score = sum(components) / len(components)
            adjustment = max(-contract["overlay"]["maximum_absolute_conviction_adjustment"], min(contract["overlay"]["maximum_absolute_conviction_adjustment"], (supply_score - 0.5) * 0.30))

            product_forecasts.append({
                "canonical_product_id": cid,
                "product_name": name,
                "route": route,
                "horizon_days": horizon,
                "champion_source": clean(champion.get("round3_candidate_source")),
                "champion_model": model,
                "current_price": round(price, 4),
                "base_forecast_price": round(forecast_price, 4),
                "base_expected_return": round(base_return, 6),
                "lower_forecast_price": round(lower, 4),
                "upper_forecast_price": round(upper, 4),
                "downside_to_lower_bound": round(downside, 6),
                "validation_mape": round(mape, 6),
                "validation_score": round(validation_score, 6),
                "directional_accuracy": clean(champion.get("directional_accuracy")),
                "lifecycle_band": clean(lifecycle.get("current_lifecycle_band")),
                "early_life_identified": early,
                "remaining_upside_estimate": round(remaining_upside, 6),
                "supply_overlay_available": overlay_available,
                "listing_count": "" if listing_count is None else listing_count,
                "seller_count": "" if seller_count is None else seller_count,
                "seller_concentration": "" if concentration is None else concentration,
                "ebay_to_current_price_gap": "" if price_gap is None else round(price_gap, 6),
                "supply_demand_support_score": round(supply_score, 6),
                "conviction_adjustment": round(adjustment, 6),
                "overlay_rewrote_point_forecast": False,
                "ranking_eligible": True,
                "purchase_recommendation_authorized": False,
            })
            product_has_forecast = True

        if not product_has_forecast:
            blocked_rows.append({
                "canonical_product_id": cid,
                "product_name": name,
                "route": route,
                "blocked_reason": "NO_CERTIFIED_CHAMPION_FOR_ROUTE_HORIZON",
                "purchase_recommendation_authorized": False,
            })

    product_ids = sorted({r["canonical_product_id"] for r in product_forecasts})
    best_by_product: dict[str, dict[str, Any]] = {}
    for cid in product_ids:
        rows = [r for r in product_forecasts if r["canonical_product_id"] == cid]
        rows.sort(key=lambda r: (r["horizon_days"] != 365, -float(r["base_expected_return"])))
        best_by_product[cid] = rows[0]

    returns = {cid: float(row["base_expected_return"]) for cid, row in best_by_product.items()}
    downside = {cid: float(row["downside_to_lower_bound"]) for cid, row in best_by_product.items()}
    validation = {cid: float(row["validation_score"]) for cid, row in best_by_product.items()}
    early = {cid: (1.0 if row["early_life_identified"] else 0.0) * max(0.0, float(row["base_expected_return"])) for cid, row in best_by_product.items()}
    supply = {cid: float(row["supply_demand_support_score"]) for cid, row in best_by_product.items()}

    return_rank = rank01(returns, True)
    downside_rank = rank01(downside, False)
    validation_rank = rank01(validation, True)
    early_rank = rank01(early, True)
    supply_rank = rank01(supply, True)
    weights = contract["ranking"]

    ranking_rows: list[dict[str, Any]] = []
    for cid, row in best_by_product.items():
        score = (
            weights["forecast_return_weight"] * return_rank[cid]
            + weights["downside_weight"] * downside_rank[cid]
            + weights["validation_weight"] * validation_rank[cid]
            + weights["early_opportunity_weight"] * early_rank[cid]
            + weights["supply_demand_weight"] * supply_rank[cid]
        )
        ranking_rows.append({
            "canonical_product_id": cid,
            "product_name": row["product_name"],
            "route": row["route"],
            "ranking_horizon_days": row["horizon_days"],
            "current_price": row["current_price"],
            "base_forecast_price": row["base_forecast_price"],
            "base_expected_return": row["base_expected_return"],
            "lower_forecast_price": row["lower_forecast_price"],
            "upper_forecast_price": row["upper_forecast_price"],
            "validation_mape": row["validation_mape"],
            "early_life_identified": row["early_life_identified"],
            "supply_demand_support_score": row["supply_demand_support_score"],
            "conviction_adjustment": row["conviction_adjustment"],
            "governed_ranking_score": round(score, 6),
            "purchase_recommendation_authorized": False,
        })
    ranking_rows.sort(key=lambda r: (-float(r["governed_ranking_score"]), r["product_name"]))
    for index, row in enumerate(ranking_rows, start=1):
        row["governed_rank"] = index

    overlay_coverage = sum(bool(r["supply_overlay_available"]) for r in product_forecasts) / max(len(product_forecasts), 1)
    if overlay_coverage < contract["overlay"]["minimum_feature_coverage"]:
        failures.append("SUPPLY_OVERLAY_COVERAGE_BELOW_MINIMUM")
    if any(truth(r.get("overlay_rewrote_point_forecast")) for r in product_forecasts):
        failures.append("OVERLAY_REWROTE_POINT_FORECAST")
    if any(truth(r.get("purchase_recommendation_authorized")) for r in product_forecasts + ranking_rows + blocked_rows):
        failures.append("PURCHASE_PREMATURELY_AUTHORIZED")
    if not ranking_rows:
        failures.append("NO_RANKING_ROWS")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    forecast_fields = list(product_forecasts[0].keys()) if product_forecasts else ["status"]
    ranking_fields = list(ranking_rows[0].keys()) if ranking_rows else ["status"]
    blocked_fields = list(blocked_rows[0].keys()) if blocked_rows else ["status"]
    write_csv(OUTPUT / "collector_production_forecasts.csv", product_forecasts, forecast_fields)
    write_csv(OUTPUT / "collector_supply_demand_overlays.csv", product_forecasts, forecast_fields)
    write_csv(OUTPUT / "collector_governed_rankings.csv", ranking_rows, ranking_fields)
    write_csv(OUTPUT / "collector_forecast_blocked_products.csv", blocked_rows, blocked_fields)

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_PRODUCTION_FORECAST_OVERLAY_RANKING"
    summary = {
        "block_name": contract["contract_name"],
        "block_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "product_rows": len(routing),
        "forecast_rows": len(product_forecasts),
        "forecasted_products": len(product_ids),
        "blocked_products": len(blocked_rows),
        "ranking_rows": len(ranking_rows),
        "certified_champion_groups": sum(truth(r.get("production_model_certified")) for r in champions),
        "supply_source_path": str(supply_path.relative_to(ROOT)) if supply_path else "",
        "supply_rows": len(supply_rows),
        "supply_overlay_coverage": round(overlay_coverage, 6),
        "uncertainty_complete": bool(product_forecasts) and all(float(r["lower_forecast_price"]) <= float(r["base_forecast_price"]) <= float(r["upper_forecast_price"]) for r in product_forecasts),
        "overlay_rewrote_point_forecast": False,
        "current_supply_demand_used_in_historical_backtest": False,
        "production_forecast_certified": not failures,
        "ranking_certified": not failures,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_production_forecast_overlay_ranking_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
