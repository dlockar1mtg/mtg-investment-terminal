from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_horizon_tournament_execution_contract_v1.json"
ARCH = ROOT / "data/governance/permanence/certification/collector_v1_horizon_specific_tournament_architecture"
PREMODEL = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution"
LEDGER = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger.csv"
RELEASE = ROOT / "data/governance/permanence/certification/collector_v1_wizards_release_date_authority/collector_wizards_release_date_authority.csv"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_horizon_specific_tournament_execution"


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_date(value: Any) -> datetime | None:
    text = clean(value)[:10]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return ordered[lo]
    weight = position - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def linear_slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    xs = list(range(len(values)))
    xbar = sum(xs) / len(xs)
    ybar = sum(values) / len(values)
    denominator = sum((x - xbar) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    slopes = []
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            dx = xs[j] - xs[i]
            if dx:
                slopes.append((values[j] - values[i]) / dx)
    return median(slopes) if slopes else sum((x - xbar) * (y - ybar) for x, y in zip(xs, values)) / denominator


def predict_direct(model: str, prices: list[float], steps: float) -> float:
    last = prices[-1]
    logs = [math.log(max(p, 0.01)) for p in prices]
    returns = [logs[i] - logs[i - 1] for i in range(1, len(logs))]
    if model == "NAIVE_LAST_VALUE":
        return last
    if model == "MEDIAN_LOG_DRIFT":
        drift = median(returns[-12:]) if returns else 0.0
        return last * math.exp(drift * steps)
    slope = linear_slope(logs[-18:])
    if model == "ROBUST_LOG_TREND":
        return last * math.exp(slope * steps)
    if model == "DAMPED_LOG_TREND":
        return last * math.exp(slope * steps * 0.65)
    if model == "EXPONENTIAL_SMOOTHING":
        level = prices[0]
        alpha = 0.35
        for value in prices[1:]:
            level = alpha * value + (1 - alpha) * level
        local = math.log(max(last, 0.01) / max(level, 0.01))
        return last * math.exp(local * min(steps, 3) / 3)
    raise ValueError(model)


def nearest_future(rows: list[dict[str, Any]], origin_date: datetime, horizon_days: int, tolerance_days: int) -> dict[str, Any] | None:
    target = origin_date + timedelta(days=horizon_days)
    candidates = [row for row in rows if row["date"] > origin_date]
    if not candidates:
        return None
    chosen = min(candidates, key=lambda row: abs((row["date"] - target).days))
    return chosen if abs((chosen["date"] - target).days) <= tolerance_days else None


def comparable_prediction(model: str, target_last: float, comparable_returns: list[tuple[float, float]], target_age_days: int) -> float:
    if not comparable_returns:
        return target_last
    returns = [r for r, _ in comparable_returns]
    weights = [w for _, w in comparable_returns]
    if model == "COMPARABLE_MEDIAN_GROWTH":
        growth = median(returns)
    elif model == "COMPARABLE_WEIGHTED_GROWTH":
        growth = sum(r * w for r, w in comparable_returns) / max(sum(weights), 1e-9)
    elif model == "COMPARABLE_LIFECYCLE_MATCHED":
        lifecycle_weights = [w * (1.25 if target_age_days <= 540 else 1.0) for w in weights]
        growth = sum(r * w for r, w in zip(returns, lifecycle_weights)) / max(sum(lifecycle_weights), 1e-9)
    elif model == "COMPARABLE_SHRUNK_ENSEMBLE":
        weighted = sum(r * w for r, w in comparable_returns) / max(sum(weights), 1e-9)
        growth = 0.65 * weighted + 0.35 * median(returns)
    else:
        raise ValueError(model)
    return target_last * max(0.05, 1 + growth)


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    arch_summary = json.loads((ARCH / "collector_horizon_specific_tournament_architecture_summary.json").read_text(encoding="utf-8"))
    premodel_summary = json.loads((PREMODEL / "collector_final_premodel_user_exclusion_resolution_summary.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    if arch_summary.get("status") != contract["required_architecture_status"]:
        failures.append("ARCHITECTURE_NOT_CERTIFIED")
    if premodel_summary.get("status") != contract["required_premodel_status"]:
        failures.append("PREMODEL_NOT_CERTIFIED")

    routing = read_csv(PREMODEL / "collector_final_method_routing.csv")
    comparable_pool = read_csv(PREMODEL / "collector_comparable_pool_certification.csv")
    ledger_raw = read_csv(LEDGER)
    release_rows = read_csv(RELEASE)
    release_by_id = {clean(r.get("canonical_product_id")): parse_date(r.get("official_release_date") or r.get("release_date")) for r in release_rows}
    route_by_id = {clean(r.get("canonical_product_id")): clean(r.get("final_forecast_method")) for r in routing if clean(r.get("forecast_output_allowed")).lower() == "true"}
    name_by_id = {clean(r.get("canonical_product_id")): clean(r.get("product_name")) for r in routing}
    comparables_by_target: dict[str, list[str]] = defaultdict(list)
    for row in comparable_pool:
        comparables_by_target[clean(row.get("target_canonical_product_id"))].append(clean(row.get("comparable_canonical_product_id")))

    series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ledger_raw:
        cid = clean(row.get("canonical_product_id"))
        date = parse_date(row.get("observation_date"))
        price = num(row.get("selected_price"))
        if cid and date and price and price > 0:
            series[cid].append({"date": date, "price": price})
    for cid in series:
        series[cid].sort(key=lambda r: r["date"])

    model_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    early_rows: list[dict[str, Any]] = []
    tolerance = contract["rolling_origin"]["future_match_tolerance_days"]

    realized_365: dict[str, float] = {}
    for cid, rows in series.items():
        release = release_by_id.get(cid)
        if not release:
            continue
        origin_candidates = [r for r in rows if r["date"] >= release]
        if not origin_candidates:
            continue
        origin = origin_candidates[0]
        future = nearest_future(rows, origin["date"], 365, tolerance)
        if future:
            realized_365[cid] = future["price"] / origin["price"] - 1
    growth_floor = max(contract["major_365_growth_definition"]["absolute_return_floor"], percentile(list(realized_365.values()), contract["major_365_growth_definition"]["cross_product_quantile"]))

    for horizon in contract["horizons"]:
        label = horizon["label"]
        days = horizon["days"]
        min_train = horizon["minimum_training_observations"]
        steps = days / 30.4375
        for cid, route in route_by_id.items():
            rows = series.get(cid, [])
            if route == "DIRECT_HISTORY_CALIBRATED":
                models = contract["direct_calibrated_models"]
            elif route == "DIRECT_HISTORY_LIMITED":
                models = contract["direct_limited_models"]
            elif route == "COMPARABLE_PRODUCT_ADJUSTED":
                models = contract["comparable_models"]
            else:
                continue
            release = release_by_id.get(cid)
            for origin_index in range(min_train - 1, len(rows) - 1):
                origin = rows[origin_index]
                future = nearest_future(rows, origin["date"], days, tolerance)
                if not future:
                    continue
                history = [r["price"] for r in rows[: origin_index + 1]]
                actual = future["price"]
                actual_return = actual / origin["price"] - 1
                age_days = (origin["date"] - release).days if release else None
                for model in models:
                    if route.startswith("DIRECT_HISTORY"):
                        predicted = predict_direct(model, history, steps)
                    else:
                        comparable_returns: list[tuple[float, float]] = []
                        for rank, comp_id in enumerate(comparables_by_target.get(cid, []), start=1):
                            comp_rows = series.get(comp_id, [])
                            comp_hist = [r for r in comp_rows if r["date"] <= origin["date"]]
                            if len(comp_hist) < 2:
                                continue
                            comp_future = nearest_future(comp_rows, origin["date"], days, tolerance)
                            if not comp_future:
                                continue
                            comp_return = comp_future["price"] / comp_hist[-1]["price"] - 1
                            comparable_returns.append((comp_return, 1 / rank))
                        if len(comparable_returns) < 1:
                            continue
                        predicted = comparable_prediction(model, origin["price"], comparable_returns, age_days or 9999)
                    predicted = max(0.01, predicted)
                    error = predicted - actual
                    ape = abs(error) / actual if actual else 0.0
                    predicted_return = predicted / origin["price"] - 1
                    fold_rows.append({
                        "horizon_label": label,
                        "horizon_days": days,
                        "route": route,
                        "canonical_product_id": cid,
                        "product_name": name_by_id.get(cid, ""),
                        "model_name": model,
                        "origin_date": origin["date"].date().isoformat(),
                        "target_date": future["date"].date().isoformat(),
                        "training_observations": origin_index + 1,
                        "origin_price": round(origin["price"], 4),
                        "actual_price": round(actual, 4),
                        "predicted_price": round(predicted, 4),
                        "actual_return": round(actual_return, 6),
                        "predicted_return": round(predicted_return, 6),
                        "absolute_error": round(abs(error), 6),
                        "absolute_percentage_error": round(ape, 6),
                        "signed_error": round(error, 6),
                        "direction_correct": (predicted_return >= 0) == (actual_return >= 0),
                        "origin_age_days": age_days if age_days is not None else "",
                        "current_only_features_used": False,
                    })

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in fold_rows:
        grouped[(row["horizon_label"], row["route"], row["model_name"])].append(row)
    score_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (label, route, model), rows in grouped.items():
        apes = [float(r["absolute_percentage_error"]) for r in rows]
        aes = [float(r["absolute_error"]) for r in rows]
        signed = [float(r["signed_error"]) for r in rows]
        direction = [bool(r["direction_correct"]) for r in rows]
        products = {r["canonical_product_id"] for r in rows}
        med_ape = median(apes) if apes else 999.0
        mae = sum(aes) / len(aes) if aes else 999.0
        bias = median(signed) if signed else 999.0
        stability = percentile(apes, 0.75) - percentile(apes, 0.25) if apes else 999.0
        result = {
            "horizon_label": label,
            "route": route,
            "model_name": model,
            "fold_count": len(rows),
            "product_count": len(products),
            "median_absolute_percentage_error": round(med_ape, 6),
            "mean_absolute_error": round(mae, 6),
            "directional_accuracy": round(sum(direction) / len(direction), 6) if direction else 0.0,
            "median_bias": round(bias, 6),
            "fold_stability": round(stability, 6),
        }
        model_rows.append(result)
        score_by_group[(label, route)].append(result)

    winner_rows: list[dict[str, Any]] = []
    for horizon in contract["horizons"]:
        label = horizon["label"]
        for route in ["DIRECT_HISTORY_CALIBRATED", "DIRECT_HISTORY_LIMITED", "COMPARABLE_PRODUCT_ADJUSTED"]:
            candidates = score_by_group.get((label, route), [])
            candidates.sort(key=lambda r: (r["median_absolute_percentage_error"], r["mean_absolute_error"], -r["directional_accuracy"], abs(r["median_bias"]), r["fold_stability"], r["model_name"]))
            baseline = next((r for r in candidates if r["model_name"] == "NAIVE_LAST_VALUE"), None)
            winner = candidates[0] if candidates else None
            min_folds = contract["rolling_origin"]["minimum_folds_per_tournament"]
            enough = bool(winner and winner["fold_count"] >= min_folds)
            beats = bool(winner and (baseline is None or winner["median_absolute_percentage_error"] <= baseline["median_absolute_percentage_error"]))
            status = "WINNER_SELECTED" if enough and beats else "GOVERNED_NO_WINNER"
            winner_rows.append({
                "horizon_label": label,
                "horizon_days": horizon["days"],
                "route": route,
                "winner_model": winner["model_name"] if status == "WINNER_SELECTED" else "",
                "winner_mape": winner["median_absolute_percentage_error"] if winner else "",
                "baseline_mape": baseline["median_absolute_percentage_error"] if baseline else "",
                "fold_count": winner["fold_count"] if winner else 0,
                "product_count": winner["product_count"] if winner else 0,
                "selection_status": status,
                "production_promotion_authorized": False,
            })

    one_year_predictions = [r for r in fold_rows if r["horizon_label"] == "1_YEAR"]
    winner_1y = {(r["route"]): r["winner_model"] for r in winner_rows if r["horizon_label"] == "1_YEAR" and r["selection_status"] == "WINNER_SELECTED"}
    for row in one_year_predictions:
        if winner_1y.get(row["route"]) != row["model_name"]:
            continue
        cid = row["canonical_product_id"]
        realized = float(row["actual_return"])
        predicted = float(row["predicted_return"])
        origin_age = int(row["origin_age_days"]) if clean(row["origin_age_days"]) else 99999
        actual_price = float(row["actual_price"])
        origin_price = float(row["origin_price"])
        is_major = realized >= growth_floor
        upside_captured = 1.0
        if is_major and actual_price > 0 and origin_price > 0:
            start_candidates = [r for r in series[cid] if release_by_id.get(cid) and r["date"] >= release_by_id[cid]]
            if start_candidates:
                start_price = start_candidates[0]["price"]
                total_gain = max(actual_price - start_price, 1e-9)
                upside_captured = max(0.0, min(1.0, (origin_price - start_price) / total_gain))
        early_eligible = origin_age <= contract["major_365_growth_definition"]["early_origin_max_age_days"] and origin_price / actual_price <= contract["major_365_growth_definition"]["maximum_origin_to_day365_price_ratio"] and upside_captured <= contract["major_365_growth_definition"]["maximum_upside_already_captured"]
        signal = predicted >= growth_floor
        early_rows.append({
            "canonical_product_id": cid,
            "product_name": row["product_name"],
            "route": row["route"],
            "winner_model": row["model_name"],
            "origin_date": row["origin_date"],
            "origin_age_days": origin_age,
            "origin_price": origin_price,
            "day365_price": actual_price,
            "realized_365_return": realized,
            "predicted_365_return": predicted,
            "major_growth_threshold": round(growth_floor, 6),
            "actual_major_grower": is_major,
            "model_major_grower_signal": signal,
            "upside_already_captured_at_signal": round(upside_captured, 6),
            "early_detection_eligible": early_eligible,
            "early_detection_success": bool(is_major and signal and early_eligible),
            "late_signal": bool(is_major and signal and not early_eligible),
            "false_positive": bool(signal and not is_major),
            "price_band_gate_used": False,
        })

    major_rows = [r for r in early_rows if r["actual_major_grower"]]
    signal_rows = [r for r in early_rows if r["model_major_grower_signal"]]
    success_rows = [r for r in early_rows if r["early_detection_success"]]
    false_rows = [r for r in early_rows if r["false_positive"]]
    late_rows = [r for r in early_rows if r["late_signal"]]
    early_metrics = [{
        "major_growth_threshold": round(growth_floor, 6),
        "evaluated_rows": len(early_rows),
        "actual_major_grower_rows": len(major_rows),
        "signal_rows": len(signal_rows),
        "early_detection_success_rows": len(success_rows),
        "major_grower_precision": round((len([r for r in signal_rows if r["actual_major_grower"]]) / len(signal_rows)), 6) if signal_rows else 0.0,
        "major_grower_recall": round((len([r for r in major_rows if r["model_major_grower_signal"]]) / len(major_rows)), 6) if major_rows else 0.0,
        "early_detection_rate": round(len(success_rows) / len(major_rows), 6) if major_rows else 0.0,
        "late_signal_rate": round(len(late_rows) / len(major_rows), 6) if major_rows else 0.0,
        "false_positive_rate": round(len(false_rows) / len(signal_rows), 6) if signal_rows else 0.0,
        "median_upside_captured_at_success": round(median([float(r["upside_already_captured_at_signal"]) for r in success_rows]), 6) if success_rows else "",
        "median_days_from_release_at_success": round(median([int(r["origin_age_days"]) for r in success_rows]), 2) if success_rows else "",
        "absolute_price_band_required": False,
    }]

    no_winner = [r for r in winner_rows if r["selection_status"] != "WINNER_SELECTED"]
    all_controls_complete = not failures and len(winner_rows) == 18 and len(fold_rows) > 0
    summary = {
        "block_name": "Collector Horizon-Specific Rolling Tournament Execution",
        "block_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "forecast_horizons": len(contract["horizons"]),
        "route_horizon_tournaments": len(winner_rows),
        "rolling_origin_prediction_rows": len(fold_rows),
        "model_score_rows": len(model_rows),
        "winner_selected_tournaments": len(winner_rows) - len(no_winner),
        "governed_no_winner_tournaments": len(no_winner),
        "major_365_growth_threshold": round(growth_floor, 6),
        "early_detection_rows": len(early_rows),
        "price_band_used_as_hard_gate": False,
        "current_supply_demand_used_in_backtest": False,
        "current_supply_demand_overlay_authorized_after_forecast": True,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": contract["expected_status"] if all_controls_complete else "FAIL_COLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_EXECUTION",
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_rolling_origin_predictions.csv", fold_rows, list(fold_rows[0].keys()) if fold_rows else ["horizon_label"])
    write_csv(OUTPUT / "collector_model_tournament_scores.csv", model_rows, list(model_rows[0].keys()) if model_rows else ["horizon_label"])
    write_csv(OUTPUT / "collector_horizon_route_winners.csv", winner_rows, list(winner_rows[0].keys()))
    write_csv(OUTPUT / "collector_365_day_early_growth_detection.csv", early_rows, list(early_rows[0].keys()) if early_rows else ["canonical_product_id"])
    write_csv(OUTPUT / "collector_365_day_early_growth_metrics.csv", early_metrics, list(early_metrics[0].keys()))
    (OUTPUT / "collector_horizon_specific_tournament_execution_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if all_controls_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
