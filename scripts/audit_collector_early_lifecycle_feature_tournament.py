from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_early_lifecycle_feature_tournament/candidate_v1_0_0"


def safe_read(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    predictions_path = OUT / "collector_early_lifecycle_feature_tournament_predictions.csv"
    leaderboard_path = OUT / "collector_early_lifecycle_feature_tournament_leaderboard.csv"
    summary_path = OUT / "collector_early_lifecycle_feature_tournament_summary.json"

    predictions = safe_read(predictions_path)
    leaderboard = safe_read(leaderboard_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}

    if predictions.empty:
        failures.append("tournament_predictions_empty")
    else:
        required = {
            "product_key", "product_name", "decision_cutoff", "candidate_method",
            "candidate_signal", "realized_return_365", "future_information_used",
        }
        if not required.issubset(predictions.columns):
            failures.append("required_prediction_fields_missing")
        if predictions["future_information_used"].astype(str).str.lower().eq("true").any():
            failures.append("future_information_detected")
        if predictions["candidate_signal"].isna().any():
            failures.append("missing_candidate_signals")

    if leaderboard.empty:
        failures.append("tournament_leaderboard_empty")
    else:
        required_metrics = {
            "candidate_method", "case_count", "mae", "signed_error", "rank_correlation",
            "top_bottom_spread", "breakout_recall_50", "breakout_recall_70",
            "false_negative_rate_50", "false_negative_rate_70",
            "top_quantile_capture_50", "top_quantile_capture_70",
            "false_positive_rate_50", "qualification_flag", "selection_score",
        }
        if not required_metrics.issubset(leaderboard.columns):
            failures.append("required_leaderboard_fields_missing")
        expected = {
            "MOMENTUM_MEDIAN_BASELINE", "CONTRARIAN_MOMENTUM", "EXPANDING_AGE_PRIOR",
            "EXPANDING_AGE_PRICE_PRIOR", "CONTRARIAN_AGE_BLEND_50_50",
            "CONTRARIAN_AGE_PRICE_BLEND_50_50", "CONTRARIAN_AGE_PRICE_BLEND_25_75",
        }
        if not expected.issubset(set(leaderboard["candidate_method"])):
            failures.append("candidate_methods_missing")

    if summary.get("future_information_used") is not False:
        failures.append("summary_future_information_control_failed")
    if summary.get("owner_review_required") is not True:
        failures.append("owner_review_not_required")
    for key in [
        "methodology_change_authorized", "production_projection_authorized",
        "purchase_recommendation_authorized", "automatic_model_update_allowed",
        "technical_freeze_authorized", "uip_acceptance_authorized",
    ]:
        if summary.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    result = {
        "audit_name": "Collector Early-Lifecycle Feature Tournament Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
