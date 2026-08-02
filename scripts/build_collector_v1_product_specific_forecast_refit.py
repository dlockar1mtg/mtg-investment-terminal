from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_product_specific_forecast_refit_contract_v1.json"
HISTORY = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger.csv"
CURRENT = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_blocker_resolution/collector_final_current_price_authority.csv"
ROUTING = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution/collector_final_method_routing.csv"
COMPARABLES = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution/collector_comparable_pool_certification.csv"
RELEASES = ROOT / "data/governance/permanence/certification/collector_v1_wizards_release_date_authority/collector_wizards_release_date_authority.csv"
CHAMPIONS = ROOT / "data/governance/permanence/certification/collector_v1_round3_final_champion_challenge/collector_round3_final_champions.csv"
ROUND1_PREDICTIONS = ROOT / "data/governance/permanence/certification/collector_v1_horizon_specific_tournament_execution/collector_rolling_origin_predictions.csv"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_product_specific_forecast_refit"


def clean(value: Any) -> str:
    return str(value or "").strip()


def num(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def parse_date(value: Any) -> datetime | None:
    text = clean(value)[:10]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def first(row: dict[str, Any], names: list[str]) -> str:
    for name in names:
        if clean(row.get(name)):
            return clean(row.get(name))
    return ""


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def robust_slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    slopes: list[float] = []
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            distance = j - i
            if distance:
                slopes.append((values[j] - values[i]) / distance)
    return median(slopes) if slopes else 0.0


def nearest_row(rows: list[dict[str, Any]], target: datetime, tolerance_days: int) -> dict[str, Any] | None:
    if not rows:
        return None
    chosen = min(rows, key=lambda row: abs((row["date"] - target).days))
    return chosen if abs((chosen["date"] - target).days) <= tolerance_days else None


def direct_forecast(model: str, prices: list[float], current_price: float, horizon_days: int) -> tuple[float, str]:
    if model == "NAIVE_LAST_VALUE":
        return current_price, "PRODUCT_CURRENT_PRICE_NAIVE"
    if model != "ROBUST_LOG_TREND":
        raise ValueError(f"UNSUPPORTED_DIRECT_MODEL:{model}")
    logs = [math.log(max(price, 0.01)) for price in prices[-18:]]
    slope = robust_slope(logs)
    steps = horizon_days / 30.4375
    forecast = current_price * math.exp(slope * steps)
    return max(0.01, forecast), f"PRODUCT_HISTORY_ROBUST_LOG_TREND_{len(logs)}_OBS"


def comparable_returns_latest(
    member_ids: list[str],
    series: dict[str, list[dict[str, Any]]],
    snapshot_date: datetime,
    horizon_days: int,
    tolerance_days: int,
) -> list[tuple[str, float, float]]:
    results: list[tuple[str, float, float]] = []
    origin_target = snapshot_date - timedelta(days=horizon_days)
    for rank, member_id in enumerate(member_ids, start=1):
        rows = [row for row in series.get(member_id, []) if row["date"] <= snapshot_date]
        if len(rows) < 2:
            continue
        origin = nearest_row(rows, origin_target, tolerance_days)
        latest = rows[-1]
        if origin is None or origin["date"] >= latest["date"] or origin["price"] <= 0:
            continue
        result = latest["price"] / origin["price"] - 1
        results.append((member_id, result, 1.0 / rank))
    return results


def comparable_returns_lifecycle(
    target_age_days: int,
    member_ids: list[str],
    series: dict[str, list[dict[str, Any]]],
    release_by_id: dict[str, datetime],
    horizon_days: int,
    tolerance_days: int,
) -> list[tuple[str, float, float]]:
    results: list[tuple[str, float, float]] = []
    for rank, member_id in enumerate(member_ids, start=1):
        release = release_by_id.get(member_id)
        rows = series.get(member_id, [])
        if release is None or len(rows) < 2:
            continue
        origin_target = release + timedelta(days=max(target_age_days, 0))
        future_target = origin_target + timedelta(days=horizon_days)
        origin = nearest_row(rows, origin_target, tolerance_days)
        future = nearest_row(rows, future_target, tolerance_days)
        if origin is None or future is None or origin["date"] >= future["date"] or origin["price"] <= 0:
            continue
        result = future["price"] / origin["price"] - 1
        age_gap = abs((origin["date"] - origin_target).days)
        lifecycle_weight = (1.0 / rank) * (1.0 / (1.0 + age_gap / 90.0))
        results.append((member_id, result, lifecycle_weight))
    return results


def comparable_forecast(
    model: str,
    current_price: float,
    member_returns: list[tuple[str, float, float]],
) -> tuple[float, float]:
    if not member_returns:
        raise ValueError("NO_USABLE_TARGET_SPECIFIC_COMPARABLE_RETURNS")
    returns = [value for _, value, _ in member_returns]
    if model == "COMPARABLE_MEDIAN_GROWTH":
        growth = median(returns)
    elif model == "COMPARABLE_LIFECYCLE_MATCHED":
        numerator = sum(value * weight for _, value, weight in member_returns)
        denominator = sum(weight for _, _, weight in member_returns)
        growth = numerator / max(denominator, 1e-12)
    else:
        raise ValueError(f"UNSUPPORTED_COMPARABLE_MODEL:{model}")
    growth = max(-0.95, growth)
    return max(0.01, current_price * (1.0 + growth)), growth


def champion_model(row: dict[str, str]) -> str:
    return first(row, [
        "round3_candidate_model",
        "final_model_name",
        "production_model",
        "model_name",
        "selected_model",
    ])


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    required = [HISTORY, CURRENT, ROUTING, COMPARABLES, RELEASES, CHAMPIONS, ROUND1_PREDICTIONS]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_INPUTS:" + ";".join(missing))

    history_rows = read_csv(HISTORY)
    current_rows = read_csv(CURRENT)
    routing_rows = read_csv(ROUTING)
    comparable_rows = read_csv(COMPARABLES)
    release_rows = read_csv(RELEASES)
    champion_rows = read_csv(CHAMPIONS)
    round1_rows = read_csv(ROUND1_PREDICTIONS)
    failures: list[str] = []

    snapshot_date = datetime.fromisoformat(contract["snapshot_date"])
    tolerance = int(contract["future_match_tolerance_days"])

    current_by_id: dict[str, dict[str, Any]] = {}
    for row in current_rows:
        cid = clean(row.get("canonical_product_id"))
        price = num(row.get("current_price"))
        if cid and price is not None and price > 0:
            current_by_id[cid] = {
                "price": price,
                "name": clean(row.get("product_name")),
                "tcgplayer_product_id": clean(row.get("tcgplayer_product_id")),
            }

    route_by_id: dict[str, str] = {}
    for row in routing_rows:
        allowed = clean(row.get("forecast_output_allowed")).lower() == "true"
        if allowed:
            route_by_id[clean(row.get("canonical_product_id"))] = clean(row.get("final_forecast_method"))

    release_by_id: dict[str, datetime] = {}
    for row in release_rows:
        cid = clean(row.get("canonical_product_id"))
        date = parse_date(first(row, ["official_release_date", "release_date"]))
        if cid and date:
            release_by_id[cid] = date

    series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in history_rows:
        cid = clean(row.get("canonical_product_id"))
        date = parse_date(first(row, ["observation_date", "observed_at_utc", "date"]))
        price = num(first(row, ["selected_price", "market_price", "price", "observed_price"]))
        if cid and date and price is not None and price > 0:
            series[cid].append({"date": date, "price": price})
    for cid in series:
        series[cid].sort(key=lambda item: item["date"])

    comparables_by_target: dict[str, list[str]] = defaultdict(list)
    comparable_seen: dict[str, set[str]] = defaultdict(set)
    for row in comparable_rows:
        target = clean(row.get("target_canonical_product_id"))
        member = clean(row.get("comparable_canonical_product_id"))
        if target and member and member not in comparable_seen[target]:
            comparables_by_target[target].append(member)
            comparable_seen[target].add(member)

    champions: dict[tuple[int, str], str] = {}
    for row in champion_rows:
        certified = clean(row.get("production_model_certified")).lower() == "true"
        if not certified:
            continue
        horizon = int(num(first(row, ["horizon_days", "ranking_horizon_days"])) or 0)
        route = clean(row.get("route"))
        model = champion_model(row)
        if horizon and route and model:
            champions[(horizon, route)] = model

    if len(champions) != contract["required_certified_champion_groups"]:
        failures.append("CERTIFIED_CHAMPION_GROUP_COUNT_MISMATCH")
    if any(model not in contract["allowed_models"] for model in champions.values()):
        failures.append("UNSUPPORTED_CERTIFIED_MODEL")

    residuals: dict[tuple[int, str, str], list[float]] = defaultdict(list)
    for row in round1_rows:
        horizon = int(num(first(row, ["horizon_days"])) or 0)
        route = clean(row.get("route"))
        model = clean(row.get("model_name"))
        actual = num(row.get("actual_price"))
        predicted = num(row.get("predicted_price"))
        if horizon and route and model and actual and predicted and actual > 0:
            residuals[(horizon, route, model)].append((actual - predicted) / predicted)

    output_rows: list[dict[str, Any]] = []
    provenance_rows: list[dict[str, Any]] = []
    for cid, route in sorted(route_by_id.items()):
        current = current_by_id.get(cid)
        if current is None:
            continue
        for (horizon, champion_route), model in sorted(champions.items()):
            if route != champion_route:
                continue
            current_price = float(current["price"])
            members_used: list[tuple[str, float, float]] = []
            source_method = ""
            try:
                if route.startswith("DIRECT_HISTORY"):
                    prices = [item["price"] for item in series.get(cid, [])]
                    if len(prices) < contract["minimum_direct_history_observations"] and model != "NAIVE_LAST_VALUE":
                        raise ValueError("INSUFFICIENT_PRODUCT_HISTORY")
                    forecast_price, source_method = direct_forecast(model, prices, current_price, horizon)
                else:
                    member_ids = comparables_by_target.get(cid, [])
                    if len(member_ids) < contract["minimum_comparable_members"]:
                        raise ValueError("TARGET_SPECIFIC_COMPARABLE_POOL_MISSING")
                    target_release = release_by_id.get(cid)
                    target_age_days = (snapshot_date - target_release).days if target_release else 0
                    if model == "COMPARABLE_LIFECYCLE_MATCHED":
                        members_used = comparable_returns_lifecycle(
                            target_age_days,
                            member_ids,
                            series,
                            release_by_id,
                            horizon,
                            tolerance,
                        )
                        source_method = "TARGET_SPECIFIC_LIFECYCLE_MATCHED_COMPARABLE_POOL"
                    else:
                        members_used = comparable_returns_latest(
                            member_ids,
                            series,
                            snapshot_date,
                            horizon,
                            tolerance,
                        )
                        source_method = "TARGET_SPECIFIC_RECENT_COMPARABLE_POOL_MEDIAN"
                    forecast_price, _ = comparable_forecast(model, current_price, members_used)
            except ValueError as exc:
                failures.append(f"FORECAST_BUILD_FAILED:{cid}:{horizon}:{exc}")
                continue

            expected_return = forecast_price / current_price - 1.0
            error_distribution = residuals.get((horizon, route, model), [])
            lower_error = percentile(error_distribution, 0.10) if error_distribution else -0.20
            upper_error = percentile(error_distribution, 0.90) if error_distribution else 0.20
            lower_price = max(0.01, forecast_price * (1.0 + lower_error))
            upper_price = max(lower_price, forecast_price * (1.0 + upper_error))
            member_ids_used = [member_id for member_id, _, _ in members_used]
            member_returns = [value for _, value, _ in members_used]

            output_rows.append({
                "canonical_product_id": cid,
                "tcgplayer_product_id": current["tcgplayer_product_id"],
                "product_name": current["name"],
                "route": route,
                "horizon_days": horizon,
                "certified_model": model,
                "current_price": round(current_price, 4),
                "product_specific_forecast_price": round(forecast_price, 4),
                "product_specific_expected_return": round(expected_return, 6),
                "lower_forecast_price": round(lower_price, 4),
                "upper_forecast_price": round(upper_price, 4),
                "history_observations_used": len(series.get(cid, [])) if route.startswith("DIRECT_HISTORY") else 0,
                "comparable_members_available": len(comparables_by_target.get(cid, [])),
                "comparable_members_used": len(member_ids_used),
                "comparable_member_ids": "|".join(member_ids_used),
                "source_method": source_method,
                "current_supply_demand_used": False,
                "production_forecast_authorized": False,
                "ranking_authorized": False,
                "purchase_recommendation_authorized": False,
            })
            provenance_rows.append({
                "canonical_product_id": cid,
                "product_name": current["name"],
                "route": route,
                "horizon_days": horizon,
                "certified_model": model,
                "source_method": source_method,
                "target_history_observation_count": len(series.get(cid, [])),
                "target_comparable_pool_size": len(comparables_by_target.get(cid, [])),
                "used_comparable_count": len(member_ids_used),
                "used_comparable_ids": "|".join(member_ids_used),
                "used_comparable_returns": "|".join(f"{value:.6f}" for value in member_returns),
                "identical_return_explanation": "NAIVE_LAST_VALUE_CERTIFIED_BASELINE" if model == "NAIVE_LAST_VALUE" else "",
            })

    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in output_rows:
        grouped[(int(row["horizon_days"]), clean(row["route"]))].append(row)

    dispersion_rows: list[dict[str, Any]] = []
    for (horizon, route), rows in sorted(grouped.items()):
        returns = [round(float(row["product_specific_expected_return"]), 6) for row in rows]
        counts = Counter(returns)
        unique_ratio = len(counts) / len(returns) if returns else 0.0
        max_share = max(counts.values()) / len(returns) if returns else 1.0
        model = clean(rows[0].get("certified_model")) if rows else ""
        exempt = model == "NAIVE_LAST_VALUE"
        passed = exempt or (
            unique_ratio >= contract["minimum_within_route_unique_return_ratio"]
            and max_share <= contract["maximum_single_return_share"]
        )
        dispersion_rows.append({
            "horizon_days": horizon,
            "route": route,
            "certified_model": model,
            "forecast_rows": len(rows),
            "unique_returns": len(counts),
            "unique_return_ratio": round(unique_ratio, 6),
            "largest_identical_return_share": round(max_share, 6),
            "minimum_return": min(returns) if returns else "",
            "median_return": median(returns) if returns else "",
            "maximum_return": max(returns) if returns else "",
            "naive_baseline_exemption": exempt,
            "differentiation_gate_passed": passed,
        })
        if not passed:
            failures.append(f"DIFFERENTIATION_GATE_FAILED:{horizon}:{route}")

    forecasted_products = len({row["canonical_product_id"] for row in output_rows})
    if len(current_rows) != contract["required_product_rows"]:
        failures.append("CURRENT_PRODUCT_ROW_COUNT_MISMATCH")
    if len(output_rows) != contract["required_forecast_rows"]:
        failures.append("PRODUCT_SPECIFIC_FORECAST_ROW_COUNT_MISMATCH")
    if forecasted_products != contract["required_forecasted_products"]:
        failures.append("PRODUCT_SPECIFIC_FORECASTED_PRODUCT_COUNT_MISMATCH")
    if any(row["current_supply_demand_used"] for row in output_rows):
        failures.append("CURRENT_SUPPLY_DEMAND_ENTERED_REFIT")

    fields = [
        "canonical_product_id", "tcgplayer_product_id", "product_name", "route", "horizon_days",
        "certified_model", "current_price", "product_specific_forecast_price",
        "product_specific_expected_return", "lower_forecast_price", "upper_forecast_price",
        "history_observations_used", "comparable_members_available", "comparable_members_used",
        "comparable_member_ids", "source_method", "current_supply_demand_used",
        "production_forecast_authorized", "ranking_authorized", "purchase_recommendation_authorized",
    ]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_product_specific_forecasts.csv", output_rows, fields)
    write_csv(OUTPUT / "collector_product_specific_forecast_provenance.csv", provenance_rows, [
        "canonical_product_id", "product_name", "route", "horizon_days", "certified_model",
        "source_method", "target_history_observation_count", "target_comparable_pool_size",
        "used_comparable_count", "used_comparable_ids", "used_comparable_returns",
        "identical_return_explanation",
    ])
    write_csv(OUTPUT / "collector_product_specific_forecast_dispersion.csv", dispersion_rows, [
        "horizon_days", "route", "certified_model", "forecast_rows", "unique_returns",
        "unique_return_ratio", "largest_identical_return_share", "minimum_return", "median_return",
        "maximum_return", "naive_baseline_exemption", "differentiation_gate_passed",
    ])

    summary = {
        "block_name": "Collector Product-Specific Forecast Refit",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "current_product_rows": len(current_rows),
        "product_specific_forecast_rows": len(output_rows),
        "forecasted_products": forecasted_products,
        "blocked_products": len(current_rows) - forecasted_products,
        "certified_champion_groups": len(champions),
        "dispersion_groups": len(dispersion_rows),
        "dispersion_groups_passed": sum(bool(row["differentiation_gate_passed"]) for row in dispersion_rows),
        "direct_forecasts": sum(clean(row["route"]).startswith("DIRECT_HISTORY") for row in output_rows),
        "comparable_forecasts": sum(clean(row["route"]) == "COMPARABLE_PRODUCT_ADJUSTED" for row in output_rows),
        "current_supply_demand_used": False,
        "product_specific_refit_certified": not failures,
        "production_forecast_authorized": False,
        "ranking_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": "PASS_COLLECTOR_PRODUCT_SPECIFIC_FORECAST_REFIT" if not failures else "FAIL_COLLECTOR_PRODUCT_SPECIFIC_FORECAST_REFIT",
    }
    (OUTPUT / "collector_product_specific_forecast_refit_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
