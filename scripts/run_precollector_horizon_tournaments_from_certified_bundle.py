from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_horizon_tournament_execution_from_certified_bundle_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/horizon_tournament_execution_from_certified_bundle"


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float | None:
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


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_csv_bytes(payload: bytes) -> list[dict[str, str]]:
    text = payload.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def first_column(rows: list[dict[str, str]], aliases: tuple[str, ...]) -> str:
    if not rows:
        return ""
    lookup = {key.casefold(): key for key in rows[0]}
    for alias in aliases:
        if alias.casefold() in lookup:
            return lookup[alias.casefold()]
    return ""


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


def robust_slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    slopes: list[float] = []
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            if j != i:
                slopes.append((values[j] - values[i]) / (j - i))
    return median(slopes) if slopes else 0.0


def nearest_future(rows: list[dict[str, Any]], origin_date: datetime, horizon_days: int, tolerance_days: int) -> dict[str, Any] | None:
    target = origin_date + timedelta(days=horizon_days)
    candidates = [row for row in rows if row["date"] > origin_date]
    if not candidates:
        return None
    chosen = min(candidates, key=lambda row: abs((row["date"] - target).days))
    return chosen if abs((chosen["date"] - target).days) <= tolerance_days else None


def predict_direct(model: str, prices: list[float], steps: float) -> float:
    last = prices[-1]
    logs = [math.log(max(p, 0.01)) for p in prices]
    returns = [logs[i] - logs[i - 1] for i in range(1, len(logs))]
    if model == "NAIVE_LAST_VALUE":
        return last
    if model == "DRIFT":
        drift = (logs[-1] - logs[0]) / max(len(logs) - 1, 1)
        return last * math.exp(drift * steps)
    if model == "ROBUST_LOG_LINEAR":
        slope = robust_slope(logs[-18:])
        return last * math.exp(slope * steps)
    if model == "DAMPED_TREND":
        slope = robust_slope(logs[-18:])
        return last * math.exp(slope * steps * 0.75)
    if model == "EXPONENTIAL_SMOOTHING":
        level = prices[0]
        alpha = 0.35
        for value in prices[1:]:
            level = alpha * value + (1 - alpha) * level
        local = math.log(max(last, 0.01) / max(level, 0.01))
        return last * math.exp(local * min(steps, 12.0) / 12.0)
    if model == "SHRUNK_DIRECT_COMPARABLE_BLEND":
        drift = predict_direct("DRIFT", prices, steps)
        return math.sqrt(max(last, 0.01) * max(drift, 0.01))
    return last


def comparable_prediction(model: str, target_last: float, comparable_returns: list[tuple[float, float]]) -> float:
    if not comparable_returns:
        return target_last
    returns = [value for value, _ in comparable_returns]
    weights = [weight for _, weight in comparable_returns]
    weighted = sum(value * weight for value, weight in comparable_returns) / max(sum(weights), 1e-9)
    med = median(returns)
    if model == "COMPARABLE_MEDIAN_GROWTH":
        growth = med
    elif model == "RANK_DECAY_WEIGHTED_GROWTH":
        growth = weighted
    elif model == "LIFECYCLE_MATCHED_COMPARABLE":
        growth = 0.8 * weighted + 0.2 * med
    elif model == "SHRUNK_COMPARABLE_ENSEMBLE":
        growth = 0.65 * weighted + 0.35 * med
    else:
        growth = weighted
    return target_last * max(0.05, 1 + growth)


def classify_member(name: str, patterns: dict[str, list[str]]) -> list[str]:
    lowered = name.casefold()
    return [role for role, tokens in patterns.items() if any(token.casefold() in lowered for token in tokens)]


def load_certified_inputs(contract: dict) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, Any]], list[dict[str, str]]]:
    drift_contract = json.loads((ROOT / contract["drift_gate_contract_path"]).read_text(encoding="utf-8"))
    temp_root = Path(tempfile.gettempdir())
    role_candidates: dict[str, list[tuple[int, str, str, bytes]]] = defaultdict(list)
    lineage: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    required_packages = {item["package_name"]: item["sha256"] for item in drift_contract["required_certified_packages"]}
    package_paths = sorted(temp_root.glob("MTG_PreCollector_*.zip"))
    for package_path in package_paths:
        if package_path.name in required_packages:
            actual = hashlib.sha256(package_path.read_bytes()).hexdigest()
            if actual != required_packages[package_path.name]:
                diagnostics.append({"severity": "BLOCKING", "code": "CERTIFIED_PACKAGE_HASH_DRIFT", "detail": package_path.name})
                continue
        try:
            with zipfile.ZipFile(package_path) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    roles = classify_member(member.filename, drift_contract["artifact_role_patterns"])
                    if not roles:
                        continue
                    payload = archive.read(member)
                    rows = read_csv_bytes(payload) if member.filename.casefold().endswith(".csv") else []
                    for role in roles:
                        role_candidates[role].append((len(rows), package_path.name, member.filename, payload))
        except zipfile.BadZipFile:
            continue
    expected_rows = {
        "ACTIVE_PRODUCT_UNIVERSE": contract["expected_active_product_count"],
        "PRODUCT_HORIZON_MATRIX": contract["expected_product_horizon_rows"],
        "HORIZON_ARCHITECTURE": contract["expected_horizon_count"],
    }
    selected: dict[str, list[dict[str, str]]] = {}
    for role in contract["required_artifact_roles"]:
        candidates = role_candidates.get(role, [])
        if not candidates:
            diagnostics.append({"severity": "BLOCKING", "code": "CERTIFIED_ARTIFACT_ROLE_MISSING", "detail": role})
            continue
        expected = expected_rows.get(role)
        if expected is not None:
            exact = [item for item in candidates if item[0] == expected]
            choice = sorted(exact or candidates, key=lambda item: (-item[0], item[1], item[2]))[0]
        else:
            choice = sorted(candidates, key=lambda item: (-item[0], item[1], item[2]))[0]
        row_count, package_name, member_name, payload = choice
        selected[role] = read_csv_bytes(payload)
        lineage.append({
            "artifact_role": role,
            "package_name": package_name,
            "member_name": member_name,
            "member_sha256": sha256_bytes(payload),
            "row_count": row_count,
        })
    return selected, lineage, diagnostics


def build_series(rows: list[dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    id_col = first_column(rows, ("canonical_product_id", "product_id", "canonical_id", "tcgplayer_product_id"))
    date_col = first_column(rows, ("observation_date", "price_date", "date", "snapshot_date", "observed_at"))
    price_col = first_column(rows, ("selected_price", "market_price", "governed_price", "historical_price", "price"))
    if not (id_col and date_col and price_col):
        raise RuntimeError("CANONICAL_HISTORY_SCHEMA_UNRESOLVED")
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cid = clean(row.get(id_col))
        date = parse_date(row.get(date_col))
        price = number(row.get(price_col))
        if cid and date and price and price > 0:
            result[cid].append({"date": date, "price": price})
    for cid in result:
        result[cid].sort(key=lambda item: item["date"])
    return result


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    artifacts, lineage, diagnostics = load_certified_inputs(contract)
    if diagnostics:
        blocking = sum(1 for row in diagnostics if row["severity"] == "BLOCKING")
        if blocking:
            write_csv(OUTPUT_DIR / contract["outputs"]["diagnostics_csv"], diagnostics, ["severity", "code", "detail"])
            return 2

    products = artifacts["ACTIVE_PRODUCT_UNIVERSE"]
    matrix = artifacts["PRODUCT_HORIZON_MATRIX"]
    architecture = artifacts["HORIZON_ARCHITECTURE"]
    eligibility = artifacts["ROUTE_MODEL_ELIGIBILITY"]
    comparable_rows = artifacts["APPROVED_COMPARABLE_LEDGER"]
    history_rows = artifacts["CANONICAL_HISTORICAL_PRICE"]

    if len(products) != contract["expected_active_product_count"]:
        diagnostics.append({"severity": "BLOCKING", "code": "ACTIVE_PRODUCT_COUNT_DRIFT", "detail": str(len(products))})
    if len(matrix) != contract["expected_product_horizon_rows"]:
        diagnostics.append({"severity": "BLOCKING", "code": "PRODUCT_HORIZON_COUNT_DRIFT", "detail": str(len(matrix))})
    if len(architecture) != contract["expected_horizon_count"]:
        diagnostics.append({"severity": "BLOCKING", "code": "HORIZON_COUNT_DRIFT", "detail": str(len(architecture))})

    product_id_col = first_column(products, ("canonical_product_id", "product_id"))
    product_name_col = first_column(products, ("product_name", "name"))
    route_col = first_column(products, ("forecast_method", "final_forecast_method", "route"))
    horizon_code_col = first_column(architecture, ("horizon_code", "horizon_label"))
    horizon_days_col = first_column(architecture, ("horizon_days", "days"))
    eligible_horizon_col = first_column(eligibility, ("horizon_code", "horizon_label"))
    eligible_route_col = first_column(eligibility, ("forecast_method", "route"))
    eligible_model_col = first_column(eligibility, ("candidate_model", "model_name"))
    if not all((product_id_col, route_col, horizon_code_col, horizon_days_col, eligible_horizon_col, eligible_route_col, eligible_model_col)):
        diagnostics.append({"severity": "BLOCKING", "code": "CERTIFIED_INPUT_SCHEMA_UNRESOLVED", "detail": "routing_or_architecture"})

    series = build_series(history_rows)
    target_col = first_column(comparable_rows, ("target_canonical_product_id", "target_product_id", "canonical_product_id"))
    comp_col = first_column(comparable_rows, ("comparable_canonical_product_id", "comparable_product_id"))
    rank_col = first_column(comparable_rows, ("comparable_rank", "rank", "selection_rank"))
    comparables_by_target: dict[str, list[tuple[str, float]]] = defaultdict(list)
    if target_col and comp_col:
        for row in comparable_rows:
            target = clean(row.get(target_col))
            comp = clean(row.get(comp_col))
            rank = number(row.get(rank_col)) if rank_col else None
            if target and comp:
                comparables_by_target[target].append((comp, 1.0 / max(rank or len(comparables_by_target[target]) + 1, 1.0)))

    horizons = {clean(row.get(horizon_code_col)): int(number(row.get(horizon_days_col)) or 0) for row in architecture}
    models_by_group: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in eligibility:
        key = (clean(row.get(eligible_horizon_col)), clean(row.get(eligible_route_col)))
        model = clean(row.get(eligible_model_col))
        if model:
            models_by_group[key].append(model)

    prediction_rows: list[dict[str, Any]] = []
    tolerance = int(contract["future_match_tolerance_days"])
    min_train = contract["minimum_training_observations"]
    for product in products:
        cid = clean(product.get(product_id_col))
        route = clean(product.get(route_col))
        name = clean(product.get(product_name_col)) if product_name_col else ""
        rows = series.get(cid, [])
        for horizon_code, horizon_days in horizons.items():
            models = models_by_group.get((horizon_code, route), [])
            if not rows or not models:
                continue
            for origin_index in range(max(int(min_train.get(route, 6)) - 1, 1), len(rows) - 1):
                origin = rows[origin_index]
                future = nearest_future(rows, origin["date"], horizon_days, tolerance)
                if not future:
                    continue
                prices = [item["price"] for item in rows[: origin_index + 1]]
                actual = future["price"]
                steps = horizon_days / 30.4375
                comparable_returns: list[tuple[float, float]] = []
                for comp_id, weight in comparables_by_target.get(cid, []):
                    comp_rows = series.get(comp_id, [])
                    comp_hist = [item for item in comp_rows if item["date"] <= origin["date"]]
                    comp_future = nearest_future(comp_rows, origin["date"], horizon_days, tolerance)
                    if comp_hist and comp_future:
                        comparable_returns.append((comp_future["price"] / comp_hist[-1]["price"] - 1, weight))
                for model in models:
                    if route == "COMPARABLE_PRODUCT_ADJUSTED":
                        predicted = comparable_prediction(model, origin["price"], comparable_returns)
                    else:
                        predicted = predict_direct(model, prices, steps)
                    if not math.isfinite(predicted) or predicted <= 0:
                        continue
                    actual_return = actual / origin["price"] - 1
                    predicted_return = predicted / origin["price"] - 1
                    signed_log_error = math.log(predicted / actual)
                    prediction_rows.append({
                        "horizon_code": horizon_code,
                        "horizon_days": horizon_days,
                        "forecast_method": route,
                        "canonical_product_id": cid,
                        "product_name": name,
                        "candidate_model": model,
                        "origin_date": origin["date"].date().isoformat(),
                        "target_date": future["date"].date().isoformat(),
                        "training_observations": origin_index + 1,
                        "origin_price": round(origin["price"], 8),
                        "actual_future_price": round(actual, 8),
                        "predicted_future_price": round(predicted, 8),
                        "absolute_log_error": round(abs(signed_log_error), 8),
                        "absolute_percentage_error": round(abs(predicted - actual) / actual, 8),
                        "direction_correct": (predicted_return >= 0) == (actual_return >= 0),
                        "current_only_features_used": False,
                    })

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in prediction_rows:
        grouped[(row["horizon_code"], row["forecast_method"], row["candidate_model"])].append(row)
    score_rows: list[dict[str, Any]] = []
    score_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (horizon, route, model), rows in grouped.items():
        log_errors = [float(row["absolute_log_error"]) for row in rows]
        apes = [float(row["absolute_percentage_error"]) for row in rows]
        directions = [bool(row["direction_correct"]) for row in rows]
        result = {
            "horizon_code": horizon,
            "forecast_method": route,
            "candidate_model": model,
            "prediction_rows": len(rows),
            "product_rows": len({row["canonical_product_id"] for row in rows}),
            "test_origin_rows": len({(row["canonical_product_id"], row["origin_date"]) for row in rows}),
            "median_absolute_log_error": round(median(log_errors), 8),
            "mean_absolute_log_error": round(sum(log_errors) / len(log_errors), 8),
            "p90_absolute_log_error": round(percentile(log_errors, 0.90), 8),
            "median_absolute_percentage_error": round(median(apes), 8),
            "directional_accuracy": round(sum(directions) / len(directions), 8),
        }
        score_rows.append(result)
        score_by_group[(horizon, route)].append(result)

    routes = sorted({clean(row.get(route_col)) for row in products if clean(row.get(route_col))})
    winner_rows: list[dict[str, Any]] = []
    uncertainty_rows: list[dict[str, Any]] = []
    min_origins = int(contract["minimum_test_origins_for_competitive_winner"])
    min_predictions = int(contract["minimum_prediction_rows_for_competitive_winner"])
    for horizon, days in horizons.items():
        for route in routes:
            candidates = score_by_group.get((horizon, route), [])
            competitive = [row for row in candidates if row["test_origin_rows"] >= min_origins and row["prediction_rows"] >= min_predictions]
            competitive.sort(key=lambda row: (row["median_absolute_log_error"], row["p90_absolute_log_error"], row["mean_absolute_log_error"], -row["directional_accuracy"], row["candidate_model"]))
            if competitive:
                winner = competitive[0]["candidate_model"]
                runner_up = competitive[1]["candidate_model"] if len(competitive) > 1 else contract["fallback_models"][route]
                status = "COMPETITIVE_WINNER"
                fallback = False
            else:
                winner = contract["fallback_models"][route]
                runner_up = ""
                status = "CONSERVATIVE_FALLBACK_INSUFFICIENT_EVIDENCE"
                fallback = True
            winner_rows.append({
                "horizon_code": horizon,
                "horizon_days": days,
                "forecast_method": route,
                "selected_model": winner,
                "runner_up_model": runner_up,
                "selection_status": status,
                "fallback_used": fallback,
                "round_two_refinement_required": True,
                "final_winner_certification_authorized": False,
                "forecast_generation_authorized": False,
            })
            winner_predictions = [row for row in prediction_rows if row["horizon_code"] == horizon and row["forecast_method"] == route and row["candidate_model"] == winner]
            errors = [float(row["absolute_log_error"]) for row in winner_predictions]
            raw = percentile(errors, float(contract["uncertainty_quantile"])) if errors else float(contract["uncertainty_ceiling_log"])
            calibrated = min(max(raw, float(contract["uncertainty_floor_log"])), float(contract["uncertainty_ceiling_log"]))
            uncertainty_rows.append({
                "horizon_code": horizon,
                "forecast_method": route,
                "selected_model": winner,
                "sample_rows": len(errors),
                "calibrated_log_uncertainty": round(calibrated, 8),
                "approximate_multiplicative_uncertainty_factor": round(math.exp(calibrated), 8),
                "calibration_status": "ROUND_ONE_EVIDENCE_ONLY" if errors else "MAXIMUM_UNCERTAINTY_FALLBACK",
                "final_uncertainty_certification_authorized": False,
            })

    blocking = sum(1 for row in diagnostics if row["severity"] == "BLOCKING")
    if len(winner_rows) != int(contract["expected_winner_rows"]):
        diagnostics.append({"severity": "BLOCKING", "code": "WINNER_REGISTRY_ROW_COUNT_DRIFT", "detail": str(len(winner_rows))})
        blocking += 1
    status = "PASS" if blocking == 0 else "REVIEW_REQUIRED"

    outputs = contract["outputs"]
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, ["artifact_role", "package_name", "member_name", "member_sha256", "row_count"])
    write_csv(OUTPUT_DIR / outputs["rolling_predictions_csv"], prediction_rows, ["horizon_code", "horizon_days", "forecast_method", "canonical_product_id", "product_name", "candidate_model", "origin_date", "target_date", "training_observations", "origin_price", "actual_future_price", "predicted_future_price", "absolute_log_error", "absolute_percentage_error", "direction_correct", "current_only_features_used"])
    write_csv(OUTPUT_DIR / outputs["model_scorecard_csv"], score_rows, ["horizon_code", "forecast_method", "candidate_model", "prediction_rows", "product_rows", "test_origin_rows", "median_absolute_log_error", "mean_absolute_log_error", "p90_absolute_log_error", "median_absolute_percentage_error", "directional_accuracy"])
    write_csv(OUTPUT_DIR / outputs["winner_registry_csv"], winner_rows, ["horizon_code", "horizon_days", "forecast_method", "selected_model", "runner_up_model", "selection_status", "fallback_used", "round_two_refinement_required", "final_winner_certification_authorized", "forecast_generation_authorized"])
    write_csv(OUTPUT_DIR / outputs["uncertainty_csv"], uncertainty_rows, ["horizon_code", "forecast_method", "selected_model", "sample_rows", "calibrated_log_uncertainty", "approximate_multiplicative_uncertainty_factor", "calibration_status", "final_uncertainty_certification_authorized"])
    write_csv(OUTPUT_DIR / outputs["diagnostics_csv"], diagnostics, ["severity", "code", "detail"])

    summary = {
        "certification_status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governing_snapshot_id": contract["governing_snapshot_id"],
        "active_product_rows": len(products),
        "forecast_horizon_count": len(horizons),
        "route_count": len(routes),
        "product_horizon_input_rows": len(matrix),
        "rolling_prediction_rows": len(prediction_rows),
        "model_scorecard_rows": len(score_rows),
        "winner_registry_rows": len(winner_rows),
        "competitive_winner_rows": sum(1 for row in winner_rows if row["selection_status"] == "COMPETITIVE_WINNER"),
        "fallback_winner_rows": sum(1 for row in winner_rows if row["fallback_used"]),
        "uncertainty_evidence_rows": len(uncertainty_rows),
        "blocking_diagnostic_rows": blocking,
        "recursive_upstream_rebuild_performed": False,
        "live_network_collection_performed": False,
        "round_two_refinement_required": True,
        "final_winner_certification_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "uip_delivery_authorized": False,
    }
    summary_path = OUTPUT_DIR / outputs["summary_json"]
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        "input_lineage": lineage,
        "output_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in OUTPUT_DIR.iterdir() if path.is_file() and path.name != outputs["manifest_json"]},
        "recursive_upstream_rebuild_performed": False,
        "live_network_collection_performed": False,
        "forecast_generation_authorized": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_HORIZON_TOURNAMENT_EXECUTION_FROM_CERTIFIED_BUNDLE" if status == "PASS" else "REVIEW_PRECOLLECTOR_HORIZON_TOURNAMENT_EXECUTION_FROM_CERTIFIED_BUNDLE")
    for key in ["active_product_rows", "forecast_horizon_count", "route_count", "product_horizon_input_rows", "rolling_prediction_rows", "model_scorecard_rows", "winner_registry_rows", "competitive_winner_rows", "fallback_winner_rows", "uncertainty_evidence_rows", "blocking_diagnostic_rows"]:
        print(f"{key.upper()}={summary[key]}")
    print("RECURSIVE_UPSTREAM_REBUILD_PERFORMED=FALSE")
    print("LIVE_NETWORK_COLLECTION_PERFORMED=FALSE")
    print("ROUND_TWO_REFINEMENT_REQUIRED=TRUE")
    print(f"NEXT_STAGE={summary['next_stage']}")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
