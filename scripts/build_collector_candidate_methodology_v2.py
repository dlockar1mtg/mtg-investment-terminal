from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APPROVAL = ROOT / "config/mtg/governance/collector_candidate_methodology_v2_approval.json"
RECON_ROOT = ROOT / "data/operations/collector_route_reconciliation/candidate_v1_0_0"
SENS_ROOT = ROOT / "data/operations/collector_methodology_sensitivity_review/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_candidate_methodology_v2/candidate_v2_0_0"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    required = {
        "approval": APPROVAL,
        "forecasts": RECON_ROOT / "collector_reconciled_candidate_forecasts.csv",
        "sensitivity": SENS_ROOT / "collector_methodology_sensitivity_product_review.csv",
    }
    missing = [f"missing_{k}:{v}" for k, v in required.items() if not v.exists()]
    if missing:
        print(json.dumps({"status": "FAIL", "failures": missing}, indent=2))
        return 1 if args.strict else 0

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    forecasts = pd.read_csv(required["forecasts"], low_memory=False)
    sensitivity = pd.read_csv(required["sensitivity"], low_memory=False)
    merged = forecasts.merge(
        sensitivity[[
            "canonical_tcgplayer_product_id",
            "variant_peer_trimmed_mean_10_percent",
            "variant_short_history_simple_return",
            "variant_exclude_dominant_peer",
            "variant_spread",
            "high_peer_concentration_flag",
            "extreme_base_rate_flag",
            "negative_base_rate_flag",
            "short_history_flag",
        ]],
        on="canonical_tcgplayer_product_id",
        how="left",
        suffixes=("", "_sensitivity"),
    )

    rows = []
    for _, row in merged.iterrows():
        out = row.to_dict()
        route = str(row.get("forecast_method_route", ""))
        baseline = num(row.get("base_annual_rate"))
        fundamental = num(row.get("fundamental_adjustment_annual_rate")) or 0.0
        history = num(row.get("history_component_annual_rate"))
        trimmed = num(row.get("variant_peer_trimmed_mean_10_percent"))
        simple_history = num(row.get("variant_short_history_simple_return"))

        method_status = "APPROVED_CANDIDATE_V2"
        candidate_rate = baseline
        if route == "COMPARABLE_PRODUCT_ADJUSTED":
            candidate_rate = None if trimmed is None else trimmed + fundamental
        elif route == "DIRECT_HISTORY_LIMITED":
            if truthy(row.get("reverse_pair_candidate_used")):
                method_status = "DIAGNOSTIC_ONLY_REVERSE_SCORE_NOT_PRODUCTION_ELIGIBLE"
            candidate_rate = None if simple_history is None or trimmed is None else (0.25 * simple_history) + (0.75 * trimmed) + fundamental
        elif route == "FUNDAMENTAL_COMPARABLE_HYBRID":
            method_status = "FORMULA_INACTIVE_OWNER_DECISION"
            candidate_rate = None

        width = num(row.get("uncertainty_width"))
        downside = None if candidate_rate is None or width is None else candidate_rate - width
        upside = None if candidate_rate is None or width is None else candidate_rate + width
        dominant_variant = num(row.get("variant_exclude_dominant_peer"))
        dominant_delta = None if candidate_rate is None or dominant_variant is None else candidate_rate - dominant_variant

        out.update({
            "candidate_methodology_version": "2.0.0",
            "candidate_v2_base_annual_rate": candidate_rate,
            "candidate_v2_downside_annual_rate": downside,
            "candidate_v2_upside_annual_rate": upside,
            "baseline_to_v2_change": None if candidate_rate is None or baseline is None else candidate_rate - baseline,
            "candidate_v2_method_status": method_status,
            "candidate_v2_peer_aggregation": "PEER_TRIMMED_MEAN_10_PERCENT" if route in {"COMPARABLE_PRODUCT_ADJUSTED", "DIRECT_HISTORY_LIMITED"} else "NOT_APPLICABLE",
            "candidate_v2_short_history_treatment": "SIMPLE_RETURN_UNTIL_365_DAYS_OBSERVED" if route == "DIRECT_HISTORY_LIMITED" else "NOT_APPLICABLE",
            "dominant_peer_review_required": bool(abs(dominant_delta) >= 0.10) if dominant_delta is not None else False,
            "dominant_peer_candidate_difference": dominant_delta,
            "extreme_rate_review_required": bool(candidate_rate is not None and abs(candidate_rate) >= 1.0),
            "candidate_v2_calculation_complete": candidate_rate is not None,
            "candidate_projection_authorized": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
            "automatic_model_update_allowed": False,
        })
        rows.append(out)

    result = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT / "collector_candidate_methodology_v2_forecasts.csv", index=False)

    comparison = result[[
        "canonical_tcgplayer_product_id", "product_name", "forecast_method_route",
        "base_annual_rate", "candidate_v2_base_annual_rate", "baseline_to_v2_change",
        "candidate_v2_method_status", "dominant_peer_review_required",
        "extreme_rate_review_required", "candidate_v2_calculation_complete",
    ]].copy()
    comparison.to_csv(OUT / "collector_candidate_methodology_v2_comparison.csv", index=False)

    route_summary = result.groupby("forecast_method_route", dropna=False).agg(
        product_count=("canonical_tcgplayer_product_id", "count"),
        complete_count=("candidate_v2_calculation_complete", lambda s: int(s.map(truthy).sum())),
        mean_baseline_rate=("base_annual_rate", "mean"),
        mean_candidate_v2_rate=("candidate_v2_base_annual_rate", "mean"),
        mean_change=("baseline_to_v2_change", "mean"),
        dominant_peer_review_count=("dominant_peer_review_required", lambda s: int(s.map(truthy).sum())),
        extreme_rate_review_count=("extreme_rate_review_required", lambda s: int(s.map(truthy).sum())),
    ).reset_index()
    route_summary.to_csv(OUT / "collector_candidate_methodology_v2_route_summary.csv", index=False)

    decision_register = pd.DataFrame([
        {"decision_id": k, "owner_decision": v, "approval_scope": approval["scope"], "activation_authorized": False}
        for k, v in approval["owner_decisions"].items()
    ])
    decision_register.to_csv(OUT / "collector_candidate_methodology_v2_owner_approval_register.csv", index=False)

    complete_count = int(result["candidate_v2_calculation_complete"].map(truthy).sum())
    inactive_count = int((result["candidate_v2_method_status"] == "FORMULA_INACTIVE_OWNER_DECISION").sum())
    reverse_diag_count = int((result["candidate_v2_method_status"] == "DIAGNOSTIC_ONLY_REVERSE_SCORE_NOT_PRODUCTION_ELIGIBLE").sum())
    summary = {
        "audit_name": "Collector Candidate Methodology v2",
        "audit_version": "2.0.0",
        "status": "PASS",
        "product_count": int(len(result)),
        "candidate_v2_calculation_complete_count": complete_count,
        "candidate_v2_calculation_incomplete_count": int(len(result) - complete_count),
        "japanese_hybrid_inactive_count": inactive_count,
        "reverse_score_diagnostic_only_count": reverse_diag_count,
        "owner_decision_count": 6,
        "candidate_development_authorized": True,
        "candidate_testing_authorized": True,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "governing_note": "Owner approvals authorize development and testing of candidate methodology v2 only. Japanese FINAL FANTASY remains inactive; reverse-score routes remain diagnostic only; no production or purchase authorization is granted.",
        "failure_count": 0,
        "failures": [],
    }
    if len(result) != 51 or inactive_count != 1 or reverse_diag_count != 7 or len(decision_register) != 6:
        summary["status"] = "FAIL"
        summary["failures"] = ["structural_expectation_failed"]
        summary["failure_count"] = 1
    (OUT / "collector_candidate_methodology_v2_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and summary["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
