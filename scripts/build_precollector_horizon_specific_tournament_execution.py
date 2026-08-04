from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_horizon_specific_tournament_execution_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/horizon_specific_tournament_execution"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"SUBPROCESS_FAILED:{completed.returncode}:{' '.join(command)}")


def discover_history() -> tuple[Path, pd.DataFrame, str, str, str]:
    id_candidates = ["canonical_product_id", "product_id"]
    date_candidates = ["price_date", "observation_date", "date", "snapshot_date"]
    price_candidates = ["market_price", "price", "governed_price", "historical_price"]
    best: tuple[int, Path, pd.DataFrame, str, str, str] | None = None
    for path in (ROOT / "artifacts/precollector").rglob("*.csv"):
        try:
            frame = pd.read_csv(path, dtype=str).fillna("")
        except Exception:
            continue
        id_col = next((c for c in id_candidates if c in frame.columns), "")
        date_col = next((c for c in date_candidates if c in frame.columns), "")
        price_col = next((c for c in price_candidates if c in frame.columns), "")
        if not (id_col and date_col and price_col):
            continue
        score = len(frame)
        if best is None or score > best[0]:
            best = (score, path, frame, id_col, date_col, price_col)
    if best is None:
        raise RuntimeError("CANONICAL_HISTORY_NOT_DISCOVERED")
    return best[1], best[2], best[3], best[4], best[5]


def prepare_series(frame: pd.DataFrame, id_col: str, date_col: str, price_col: str) -> dict[str, pd.DataFrame]:
    work = frame[[id_col, date_col, price_col]].copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce", utc=True)
    work[price_col] = pd.to_numeric(work[price_col], errors="coerce")
    work = work.dropna(subset=[date_col, price_col])
    work = work[work[price_col] > 0]
    work = work.sort_values([id_col, date_col]).drop_duplicates([id_col, date_col], keep="last")
    return {str(pid): group.reset_index(drop=True) for pid, group in work.groupby(id_col)}


def nearest_future(group: pd.DataFrame, date_col: str, origin_index: int, horizon_days: int) -> tuple[int, float] | None:
    target_date = group.iloc[origin_index][date_col] + pd.Timedelta(days=horizon_days)
    candidates = group[group[date_col] >= target_date]
    if candidates.empty:
        return None
    idx = int(candidates.index[0])
    return idx, float(group.loc[idx, "_price"])


def predict_direct(model: str, train: pd.DataFrame, date_col: str, horizon_days: int) -> float:
    prices = train["_price"].astype(float).to_numpy()
    if len(prices) == 0:
        return math.nan
    last = float(prices[-1])
    if model == "NAIVE_LAST_VALUE":
        return last
    elapsed = (train[date_col] - train[date_col].iloc[0]).dt.total_seconds().to_numpy() / 86400.0
    if len(prices) < 2 or elapsed[-1] <= 0:
        return last
    logs = np.log(prices)
    if model == "DRIFT":
        daily = (logs[-1] - logs[0]) / elapsed[-1]
        return float(math.exp(logs[-1] + daily * horizon_days))
    if model == "ROBUST_LOG_LINEAR":
        slope, intercept = np.polyfit(elapsed, logs, 1)
        residuals = logs - (intercept + slope * elapsed)
        scale = np.median(np.abs(residuals - np.median(residuals))) or 1.0
        keep = np.abs(residuals) <= 3.0 * scale
        if keep.sum() >= 2:
            slope, intercept = np.polyfit(elapsed[keep], logs[keep], 1)
        return float(math.exp(intercept + slope * (elapsed[-1] + horizon_days)))
    if model == "DAMPED_TREND":
        slope, _ = np.polyfit(elapsed, logs, 1)
        damping = 0.75
        return float(math.exp(logs[-1] + slope * horizon_days * damping))
    if model == "EXPONENTIAL_SMOOTHING":
        alpha = 0.35
        level = float(prices[0])
        trend = 0.0
        for value in prices[1:]:
            previous = level
            level = alpha * float(value) + (1 - alpha) * (level + trend)
            trend = alpha * (level - previous) + (1 - alpha) * trend
        periods = max(1.0, horizon_days / max(elapsed[-1] / max(len(prices) - 1, 1), 1.0))
        return max(0.01, float(level + trend * min(periods, 12.0)))
    if model == "SHRUNK_DIRECT_COMPARABLE_BLEND":
        drift = predict_direct("DRIFT", train, date_col, horizon_days)
        return float(math.sqrt(max(last, 0.01) * max(drift, 0.01)))
    return last


def score_predictions(predictions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for keys, group in predictions.groupby(["horizon_code", "forecast_method", "candidate_model"], dropna=False):
        horizon, route, model = keys
        errors = group["absolute_log_error"].astype(float)
        ape = group["absolute_percentage_error"].astype(float)
        rows.append({
            "horizon_code": horizon,
            "forecast_method": route,
            "candidate_model": model,
            "prediction_rows": len(group),
            "product_rows": group["canonical_product_id"].nunique(),
            "test_origin_rows": group[["canonical_product_id", "origin_date"]].drop_duplicates().shape[0],
            "median_absolute_log_error": round(float(errors.median()), 8),
            "mean_absolute_log_error": round(float(errors.mean()), 8),
            "p90_absolute_log_error": round(float(errors.quantile(0.90)), 8),
            "median_absolute_percentage_error": round(float(ape.median()), 8),
            "directional_accuracy": round(float(group["direction_correct"].astype(float).mean()), 8),
        })
    return pd.DataFrame(rows)


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    artifacts_root = ROOT / "artifacts/precollector"
    if artifacts_root.exists():
        shutil.rmtree(artifacts_root)
    run([sys.executable, str(ROOT / contract["upstream_builder_path"])])

    architecture_dir = ROOT / contract["architecture_output_directory"]
    forecast_dir = ROOT / contract["forecast_input_output_directory"]
    eligibility_path = architecture_dir / "precollector_horizon_route_model_eligibility.csv"
    architecture_path = architecture_dir / "precollector_horizon_tournament_architecture.csv"
    product_path = forecast_dir / "precollector_79_product_forecast_input_certification.csv"
    for path in [eligibility_path, architecture_path, product_path]:
        if not path.is_file():
            raise RuntimeError(f"UPSTREAM_OUTPUT_MISSING:{path.name}")

    eligibility = pd.read_csv(eligibility_path, dtype=str).fillna("")
    architecture = pd.read_csv(architecture_path, dtype=str).fillna("")
    products = pd.read_csv(product_path, dtype=str).fillna("")
    history_path, raw_history, id_col, date_col, price_col = discover_history()
    raw_history = raw_history.rename(columns={price_col: "_price"})
    series = prepare_series(raw_history, id_col, date_col, "_price")

    diagnostics: list[dict] = []
    if len(products) != int(contract["expected_active_product_count"]):
        diagnostics.append({"severity": "BLOCKING", "code": "ACTIVE_PRODUCT_COUNT_DRIFT", "detail": str(len(products))})
    if architecture["horizon_code"].nunique() != int(contract["expected_horizon_count"]):
        diagnostics.append({"severity": "BLOCKING", "code": "HORIZON_COUNT_DRIFT", "detail": str(architecture["horizon_code"].nunique())})
    if products["forecast_method"].nunique() != int(contract["expected_route_count"]):
        diagnostics.append({"severity": "BLOCKING", "code": "ROUTE_COUNT_DRIFT", "detail": str(products["forecast_method"].nunique())})

    prediction_rows: list[dict] = []
    horizon_days_map = {str(row["horizon_code"]): int(float(row["horizon_days"])) for _, row in architecture.iterrows()}
    min_train = {"DIRECT_HISTORY_CALIBRATED": 18, "DIRECT_HISTORY_LIMITED": 10, "COMPARABLE_PRODUCT_ADJUSTED": 6}

    for _, product in products.iterrows():
        pid = str(product["canonical_product_id"])
        route = str(product["forecast_method"])
        group = series.get(pid)
        if group is None or group.empty:
            continue
        group = group.copy().reset_index(drop=True)
        group["_price"] = pd.to_numeric(group["_price"], errors="coerce")
        group = group.dropna(subset=["_price"])
        models_by_horizon = eligibility[eligibility["forecast_method"].eq(route)]
        for horizon, candidates in models_by_horizon.groupby("horizon_code"):
            days = horizon_days_map[str(horizon)]
            for model in candidates["candidate_model"].tolist():
                start = max(min_train.get(route, 6) - 1, 1)
                for origin_index in range(start, len(group) - 1):
                    future = nearest_future(group, date_col, origin_index, days)
                    if future is None:
                        continue
                    _, actual = future
                    train = group.iloc[: origin_index + 1].copy()
                    predicted = predict_direct(str(model), train, date_col, days)
                    if not np.isfinite(predicted) or predicted <= 0:
                        continue
                    origin_price = float(train["_price"].iloc[-1])
                    log_error = math.log(predicted / actual)
                    direction_correct = (predicted >= origin_price) == (actual >= origin_price)
                    prediction_rows.append({
                        "canonical_product_id": pid,
                        "product_name": product["product_name"],
                        "product_family": product["product_family"],
                        "forecast_method": route,
                        "horizon_code": horizon,
                        "horizon_days": days,
                        "candidate_model": model,
                        "origin_date": train[date_col].iloc[-1].isoformat(),
                        "origin_price": round(origin_price, 8),
                        "actual_future_price": round(actual, 8),
                        "predicted_future_price": round(predicted, 8),
                        "signed_log_error": round(log_error, 8),
                        "absolute_log_error": round(abs(log_error), 8),
                        "absolute_percentage_error": round(abs(predicted - actual) / actual, 8),
                        "direction_correct": bool(direction_correct),
                    })

    predictions = pd.DataFrame(prediction_rows)
    if predictions.empty:
        diagnostics.append({"severity": "BLOCKING", "code": "NO_ROLLING_ORIGIN_PREDICTIONS", "detail": str(history_path)})
        scorecard = pd.DataFrame(columns=["horizon_code", "forecast_method", "candidate_model"])
    else:
        scorecard = score_predictions(predictions)

    winner_rows: list[dict] = []
    uncertainty_rows: list[dict] = []
    minimum_origins = int(contract["minimum_test_origins_for_competitive_winner"])
    minimum_predictions = int(contract["minimum_aggregate_predictions_for_competitive_winner"])
    floor = float(contract["uncertainty_floor_log"])
    ceiling = float(contract["uncertainty_ceiling_log"])
    quantile = float(contract["uncertainty_quantile"])

    for horizon in architecture["horizon_code"].tolist():
        for route in sorted(products["forecast_method"].unique()):
            eligible_models = eligibility[(eligibility["horizon_code"].eq(horizon)) & (eligibility["forecast_method"].eq(route))]["candidate_model"].tolist()
            subset = scorecard[(scorecard["horizon_code"].eq(horizon)) & (scorecard["forecast_method"].eq(route))].copy() if not scorecard.empty else pd.DataFrame()
            competitive = subset[(subset["test_origin_rows"] >= minimum_origins) & (subset["prediction_rows"] >= minimum_predictions)].copy() if not subset.empty else pd.DataFrame()
            if not competitive.empty:
                competitive = competitive.sort_values(["median_absolute_log_error", "p90_absolute_log_error", "mean_absolute_log_error", "candidate_model"])
                selected = competitive.iloc[0]
                winner = str(selected["candidate_model"])
                fallback_used = False
                status = "COMPETITIVE_WINNER"
                runner_up = str(competitive.iloc[1]["candidate_model"]) if len(competitive) > 1 else contract["fallback_models"][route]
            else:
                winner = contract["fallback_models"][route]
                if winner not in eligible_models:
                    diagnostics.append({"severity": "BLOCKING", "code": "FALLBACK_NOT_ELIGIBLE", "detail": f"{horizon}:{route}:{winner}"})
                fallback_used = True
                status = "CONSERVATIVE_FALLBACK_INSUFFICIENT_ORIGINS"
                runner_up = ""
            winner_rows.append({
                "horizon_code": horizon,
                "horizon_days": horizon_days_map[horizon],
                "forecast_method": route,
                "selected_model": winner,
                "runner_up_model": runner_up,
                "selection_status": status,
                "fallback_used": fallback_used,
                "independent_horizon_competition_completed": True,
                "forecast_generation_authorized": False,
            })
            winner_predictions = predictions[(predictions["horizon_code"].eq(horizon)) & (predictions["forecast_method"].eq(route)) & (predictions["candidate_model"].eq(winner))] if not predictions.empty else pd.DataFrame()
            if winner_predictions.empty:
                calibrated = ceiling
                sample_rows = 0
                calibration_status = "MAXIMUM_UNCERTAINTY_FALLBACK"
            else:
                raw = float(winner_predictions["absolute_log_error"].astype(float).quantile(quantile))
                calibrated = min(max(raw, floor), ceiling)
                sample_rows = len(winner_predictions)
                calibration_status = "CALIBRATED_FROM_ROLLING_ORIGIN_ERRORS"
            uncertainty_rows.append({
                "horizon_code": horizon,
                "forecast_method": route,
                "selected_model": winner,
                "sample_rows": sample_rows,
                "calibrated_log_uncertainty": round(calibrated, 8),
                "approximate_multiplicative_uncertainty_factor": round(math.exp(calibrated), 8),
                "calibration_status": calibration_status,
                "forecast_generation_authorized": False,
            })

    winners = pd.DataFrame(winner_rows)
    uncertainty = pd.DataFrame(uncertainty_rows)
    if len(winners) != int(contract["expected_winner_rows"]):
        diagnostics.append({"severity": "BLOCKING", "code": "WINNER_REGISTRY_ROW_COUNT_DRIFT", "detail": str(len(winners))})
    if winners.groupby("horizon_code")["forecast_method"].nunique().min() != int(contract["expected_route_count"]):
        diagnostics.append({"severity": "BLOCKING", "code": "INCOMPLETE_HORIZON_ROUTE_WINNER_COVERAGE", "detail": ""})

    diagnostics_frame = pd.DataFrame(diagnostics, columns=["severity", "code", "detail"])
    blocking = int(diagnostics_frame["severity"].eq("BLOCKING").sum()) if not diagnostics_frame.empty else 0
    status = "PASS" if blocking == 0 else "REVIEW_REQUIRED"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    frames = {
        outputs["rolling_predictions_csv"]: predictions.sort_values(["horizon_days", "forecast_method", "candidate_model", "product_name", "origin_date"]) if not predictions.empty else predictions,
        outputs["model_scorecard_csv"]: scorecard.sort_values(["horizon_code", "forecast_method", "median_absolute_log_error", "candidate_model"]) if not scorecard.empty else scorecard,
        outputs["winner_registry_csv"]: winners.sort_values(["horizon_days", "forecast_method"]),
        outputs["uncertainty_calibration_csv"]: uncertainty.sort_values(["horizon_code", "forecast_method"]),
        outputs["diagnostics_csv"]: diagnostics_frame,
    }
    output_paths: dict[str, Path] = {}
    for filename, frame in frames.items():
        path = OUTPUT_DIR / filename
        frame.to_csv(path, index=False)
        output_paths[filename] = path

    summary = {
        "certification_status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "active_product_rows": len(products),
        "forecast_horizon_count": architecture["horizon_code"].nunique(),
        "route_count": products["forecast_method"].nunique(),
        "rolling_prediction_rows": len(predictions),
        "model_scorecard_rows": len(scorecard),
        "winner_registry_rows": len(winners),
        "competitive_winner_rows": int(winners["selection_status"].eq("COMPETITIVE_WINNER").sum()),
        "fallback_winner_rows": int(winners["fallback_used"].astype(bool).sum()),
        "uncertainty_calibration_rows": len(uncertainty),
        "blocking_diagnostic_rows": blocking,
        "history_source_path": str(history_path.relative_to(ROOT)),
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
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "history_source_sha256": sha256_file(history_path),
        "architecture_sha256": sha256_file(architecture_path),
        "eligibility_sha256": sha256_file(eligibility_path),
        "output_sha256": {name: sha256_file(path) for name, path in sorted(output_paths.items())},
        "forecast_generation_authorized": False,
    }
    manifest_path = OUTPUT_DIR / outputs["manifest_json"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_EXECUTION_BUILD" if status == "PASS" else "REVIEW_PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_EXECUTION_BUILD")
    for key in ["active_product_rows", "forecast_horizon_count", "route_count", "rolling_prediction_rows", "model_scorecard_rows", "winner_registry_rows", "competitive_winner_rows", "fallback_winner_rows", "uncertainty_calibration_rows", "blocking_diagnostic_rows"]:
        print(f"{key.upper()}={summary[key]}")
    print(f"NEXT_STAGE={summary['next_stage']}")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    print("UIP_DELIVERY_AUTHORIZED=FALSE")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
