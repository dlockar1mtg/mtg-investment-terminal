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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_comparable_model_tournament_calibration_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/comparable_model_tournament_calibration"


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


def normalized(values: pd.Series) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce").fillna(0.0).clip(lower=0.0)
    total = float(clean.sum())
    if total <= 0:
        return pd.Series(np.repeat(1.0 / len(clean), len(clean)), index=clean.index)
    return clean / total


def model_weights(group: pd.DataFrame, model: str) -> pd.Series:
    if model == "APPROVED_POLICY_WEIGHTED":
        return normalized(group["approved_contribution_weight"])
    if model == "INVERSE_DISTANCE":
        distance = pd.to_numeric(group["comparable_distance_score"], errors="coerce").fillna(0.0)
        return normalized(1.0 / (1.0 + distance.clip(lower=0.0)))
    if model == "RANK_DECAY":
        rank = pd.to_numeric(group["comparable_rank"], errors="raise")
        return normalized(1.0 / rank)
    if model == "ROBUST_MEDIAN":
        return pd.Series(np.repeat(1.0 / len(group), len(group)), index=group.index)
    raise RuntimeError(f"UNSUPPORTED_MODEL:{model}")


def prediction(group: pd.DataFrame, model: str) -> float:
    prices = pd.to_numeric(group["candidate_current_price"], errors="raise").clip(lower=0.01)
    if model == "ROBUST_MEDIAN":
        return float(prices.median())
    weights = model_weights(group, model)
    return float(np.exp(np.sum(weights * np.log(prices))))


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    artifacts_root = ROOT / "artifacts/precollector"
    if artifacts_root.exists():
        shutil.rmtree(artifacts_root)
    run([sys.executable, str(ROOT / contract["upstream_builder_path"])])

    upstream = ROOT / contract["upstream_output_directory"]
    routing = ROOT / contract["routing_output_directory"]
    ledger_path = upstream / "precollector_owner_approved_comparable_ledger.csv"
    routes_path = routing / "precollector_79_product_forecast_method_routes.csv"
    targets_path = routing / "precollector_79_product_comparable_target_status.csv"
    for path in [ledger_path, routes_path, targets_path]:
        if not path.is_file():
            raise RuntimeError(f"UPSTREAM_OUTPUT_MISSING:{path.name}")

    ledger = pd.read_csv(ledger_path, dtype=str).fillna("")
    routes = pd.read_csv(routes_path, dtype=str).fillna("")
    targets = pd.read_csv(targets_path, dtype=str).fillna("")
    if len(routes) != int(contract["expected_active_product_count"]):
        raise RuntimeError("ACTIVE_PRODUCT_COUNT_DRIFT")
    if len(ledger) != int(contract["expected_approved_comparable_rows"]):
        raise RuntimeError("APPROVED_LEDGER_COUNT_DRIFT")

    required_ids = set(targets.loc[
        targets["comparable_support_required"].astype(str).str.lower().eq("true"),
        "canonical_product_id",
    ])
    if len(required_ids) != int(contract["expected_required_comparable_target_count"]):
        raise RuntimeError("REQUIRED_TARGET_COUNT_DRIFT")

    route_info = routes.set_index("canonical_product_id")[[
        "product_name", "product_family", "forecast_method", "governed_current_price"
    ]].to_dict("index")
    diagnostics: list[dict] = []
    prediction_rows: list[dict] = []

    for target_id, group in ledger.groupby("target_canonical_product_id", sort=True):
        info = route_info.get(target_id)
        if info is None:
            diagnostics.append({"severity": "BLOCKING", "code": "TARGET_ROUTE_MISSING", "target_id": target_id, "detail": ""})
            continue
        actual = max(float(info["governed_current_price"]), 0.01)
        for model in contract["candidate_models"]:
            predicted = max(prediction(group, model), 0.01)
            log_error = math.log(predicted / actual)
            prediction_rows.append({
                "target_canonical_product_id": target_id,
                "target_product_name": info["product_name"],
                "product_family": info["product_family"],
                "forecast_method": info["forecast_method"],
                "model_name": model,
                "actual_governed_current_price": round(actual, 8),
                "reconstructed_price": round(predicted, 8),
                "signed_log_error": round(log_error, 8),
                "absolute_log_error": round(abs(log_error), 8),
                "absolute_percentage_error": round(abs(predicted - actual) / actual, 8),
                "donor_count": len(group),
                "required_comparable_target": target_id in required_ids,
            })

    predictions = pd.DataFrame(prediction_rows)
    score_rows: list[dict] = []
    for model, group in predictions.groupby("model_name"):
        errors = group["absolute_log_error"].astype(float)
        score_rows.append({
            "model_name": model,
            "target_rows": len(group),
            "required_target_rows": int(group["required_comparable_target"].sum()),
            "median_absolute_log_error": round(float(errors.median()), 8),
            "mean_absolute_log_error": round(float(errors.mean()), 8),
            "p90_absolute_log_error": round(float(errors.quantile(0.90)), 8),
            "median_absolute_percentage_error": round(float(group["absolute_percentage_error"].astype(float).median()), 8),
        })
    scorecard = pd.DataFrame(score_rows).sort_values([
        "median_absolute_log_error", "p90_absolute_log_error", "mean_absolute_log_error", "model_name"
    ]).reset_index(drop=True)
    scorecard["tournament_rank"] = np.arange(1, len(scorecard) + 1)
    winner = str(scorecard.iloc[0]["model_name"])
    scorecard["selected_winner"] = scorecard["model_name"].eq(winner)

    family_route = predictions.groupby(["model_name", "product_family", "forecast_method"], dropna=False).agg(
        target_rows=("target_canonical_product_id", "count"),
        median_absolute_log_error=("absolute_log_error", "median"),
        p90_absolute_log_error=("absolute_log_error", lambda x: x.astype(float).quantile(0.90)),
    ).reset_index()
    family_route[["median_absolute_log_error", "p90_absolute_log_error"]] = family_route[[
        "median_absolute_log_error", "p90_absolute_log_error"
    ]].round(8)

    winner_predictions = predictions[predictions["model_name"].eq(winner)].copy()
    calibration_rows: list[dict] = []
    floor = float(contract["uncertainty_floor_log"])
    ceiling = float(contract["uncertainty_ceiling_log"])
    for (family, route), group in winner_predictions.groupby(["product_family", "forecast_method"], dropna=False):
        errors = group["absolute_log_error"].astype(float)
        raw = float(errors.quantile(0.80)) if len(errors) > 1 else float(errors.iloc[0])
        calibrated = min(max(raw, floor), ceiling)
        calibration_rows.append({
            "selected_model": winner,
            "product_family": family,
            "forecast_method": route,
            "sample_rows": len(group),
            "median_absolute_log_error": round(float(errors.median()), 8),
            "p80_absolute_log_error": round(raw, 8),
            "calibrated_log_uncertainty": round(calibrated, 8),
            "approximate_multiplicative_uncertainty_factor": round(math.exp(calibrated), 8),
            "calibration_status": "CALIBRATED_FOR_FORECAST_INPUT_CERTIFICATION_ONLY",
        })
    calibration = pd.DataFrame(calibration_rows)

    required_coverage = int(winner_predictions["required_comparable_target"].sum())
    winner_row = scorecard.iloc[0]
    if required_coverage < int(contract["minimum_required_target_coverage"]):
        diagnostics.append({"severity": "BLOCKING", "code": "REQUIRED_TARGET_COVERAGE_FAILURE", "target_id": "", "detail": str(required_coverage)})
    if float(winner_row["median_absolute_log_error"]) > float(contract["maximum_winner_median_absolute_log_error"]):
        diagnostics.append({"severity": "BLOCKING", "code": "WINNER_MEDIAN_ERROR_THRESHOLD_FAILURE", "target_id": "", "detail": str(winner_row["median_absolute_log_error"])})
    if float(winner_row["p90_absolute_log_error"]) > float(contract["maximum_winner_p90_absolute_log_error"]):
        diagnostics.append({"severity": "BLOCKING", "code": "WINNER_P90_ERROR_THRESHOLD_FAILURE", "target_id": "", "detail": str(winner_row["p90_absolute_log_error"])})
    if predictions.isna().any().any() or not np.isfinite(predictions[["actual_governed_current_price", "reconstructed_price", "absolute_log_error"]].astype(float).to_numpy()).all():
        diagnostics.append({"severity": "BLOCKING", "code": "NONFINITE_TOURNAMENT_OUTPUT", "target_id": "", "detail": ""})

    diagnostics_frame = pd.DataFrame(diagnostics, columns=["severity", "code", "target_id", "detail"])
    blocking = int(diagnostics_frame["severity"].eq("BLOCKING").sum()) if not diagnostics_frame.empty else 0
    status = "PASS" if blocking == 0 else "REVIEW_REQUIRED"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    frames = {
        outputs["tournament_predictions_csv"]: predictions.sort_values(["model_name", "target_product_name"]),
        outputs["model_scorecard_csv"]: scorecard,
        outputs["family_route_scorecard_csv"]: family_route.sort_values(["model_name", "product_family", "forecast_method"]),
        outputs["winner_calibration_csv"]: calibration.sort_values(["product_family", "forecast_method"]),
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
        "active_product_rows": len(routes),
        "required_comparable_target_rows": len(required_ids),
        "approved_comparable_ledger_rows": len(ledger),
        "candidate_model_rows": len(scorecard),
        "tournament_prediction_rows": len(predictions),
        "selected_model": winner,
        "winner_median_absolute_log_error": float(winner_row["median_absolute_log_error"]),
        "winner_p90_absolute_log_error": float(winner_row["p90_absolute_log_error"]),
        "winner_required_target_coverage": required_coverage,
        "calibration_rows": len(calibration),
        "blocking_diagnostic_rows": blocking,
        "validation_scope": "CROSS_SECTIONAL_GOVERNED_PRICE_RECONSTRUCTION_NOT_FORWARD_FORECAST_PERFORMANCE",
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
        "upstream_ledger_sha256": sha256_file(ledger_path),
        "upstream_routes_sha256": sha256_file(routes_path),
        "output_sha256": {name: sha256_file(path) for name, path in sorted(output_paths.items())},
        "forecast_generation_authorized": False,
    }
    manifest_path = OUTPUT_DIR / outputs["manifest_json"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_COMPARABLE_MODEL_TOURNAMENT_CALIBRATION_BUILD" if status == "PASS" else "REVIEW_PRECOLLECTOR_COMPARABLE_MODEL_TOURNAMENT_CALIBRATION_BUILD")
    print(f"ACTIVE_PRODUCT_ROWS={len(routes)}")
    print(f"REQUIRED_COMPARABLE_TARGET_ROWS={len(required_ids)}")
    print(f"APPROVED_COMPARABLE_LEDGER_ROWS={len(ledger)}")
    print(f"CANDIDATE_MODEL_ROWS={len(scorecard)}")
    print(f"TOURNAMENT_PREDICTION_ROWS={len(predictions)}")
    print(f"SELECTED_MODEL={winner}")
    print(f"WINNER_MEDIAN_ABSOLUTE_LOG_ERROR={winner_row['median_absolute_log_error']}")
    print(f"WINNER_P90_ABSOLUTE_LOG_ERROR={winner_row['p90_absolute_log_error']}")
    print(f"BLOCKING_DIAGNOSTIC_ROWS={blocking}")
    print(f"NEXT_STAGE={summary['next_stage']}")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    print("UIP_DELIVERY_AUTHORIZED=FALSE")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
