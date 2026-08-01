from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_methodology_v2_3_approval.json"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    out_dir = ROOT / cfg["output_directory"]
    files = {
        "forecasts": out_dir / "collector_candidate_methodology_v2_3_forecasts.csv",
        "comparison": out_dir / "collector_candidate_methodology_v2_3_comparison.csv",
        "route_summary": out_dir / "collector_candidate_methodology_v2_3_route_summary.csv",
        "approval_register": out_dir / "collector_candidate_methodology_v2_3_owner_approval_register.csv",
        "summary": out_dir / "collector_candidate_methodology_v2_3_summary.json",
    }
    failures = [f"missing_output:{name}:{path}" for name, path in files.items() if not path.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    forecasts = pd.read_csv(files["forecasts"], low_memory=False)
    routes = pd.read_csv(files["route_summary"], low_memory=False)
    approvals = pd.read_csv(files["approval_register"], low_memory=False)
    summary = json.loads(files["summary"].read_text(encoding="utf-8"))

    if len(forecasts) != 51:
        failures.append("product_count_not_51")
    if forecasts["canonical_tcgplayer_product_id"].astype(str).nunique() != 51:
        failures.append("product_ids_not_unique")
    complete = int(forecasts["candidate_v2_3_calculation_complete"].map(truthy).sum())
    if complete != 50:
        failures.append("complete_count_not_50")
    if len(routes) != 4:
        failures.append("route_count_not_4")
    if len(approvals) != 2:
        failures.append("approval_count_not_2")
    expected_decisions = {"COL-SCEN-001", "COL-CONF-001"}
    if set(approvals["decision_id"].astype(str)) != expected_decisions:
        failures.append("approval_decision_ids_mismatch")
    if approvals["activation_authorized"].map(truthy).any():
        failures.append("activation_authorized_true")

    downside = pd.to_numeric(forecasts["candidate_v2_3_downside_annual_rate"], errors="coerce")
    if (downside < -0.95 - 1e-12).any():
        failures.append("downside_below_loss_floor")
    widths = pd.to_numeric(forecasts["candidate_v2_3_scenario_width_final"], errors="coerce")
    route_mins = cfg["scenario_decision"]["route_minimum_widths"]
    route_maxs = cfg["scenario_decision"]["route_maximum_widths"]
    for _, row in forecasts.iterrows():
        route = str(row["forecast_method_route"])
        width = pd.to_numeric(pd.Series([row["candidate_v2_3_scenario_width_final"]]), errors="coerce").iloc[0]
        rate = pd.to_numeric(pd.Series([row["candidate_v2_3_base_annual_rate"]]), errors="coerce").iloc[0]
        if pd.isna(width):
            failures.append(f"missing_width:{row['canonical_tcgplayer_product_id']}")
            continue
        if width > float(route_maxs[route]) + 1e-12:
            failures.append(f"route_max_width_violation:{row['canonical_tcgplayer_product_id']}")
        if not pd.isna(rate):
            allowable = float(rate) - (-0.95)
            expected_min = min(float(route_mins[route]), max(0.0, allowable))
            if width + 1e-12 < expected_min:
                failures.append(f"route_min_width_violation:{row['canonical_tcgplayer_product_id']}")

    confidence = pd.to_numeric(forecasts["candidate_v2_3_confidence_score_0_to_100"], errors="coerce")
    if confidence.isna().any() or (confidence < 0).any() or (confidence > 100).any():
        failures.append("confidence_outside_0_to_100")
    reverse = forecasts["candidate_v2_3_method_status"].astype(str).str.startswith("DIAGNOSTIC_ONLY_REVERSE_SCORE")
    if (confidence[reverse] > 10 + 1e-12).any():
        failures.append("reverse_confidence_above_10")
    inactive = forecasts["candidate_v2_3_method_status"].astype(str) == "FORMULA_INACTIVE_OWNER_DECISION"
    if int(inactive.sum()) != 1:
        failures.append("inactive_hybrid_count_not_1")
    if (confidence[inactive] > 15 + 1e-12).any():
        failures.append("inactive_confidence_above_15")

    closed_columns = [
        "candidate_projection_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
    ]
    for column in closed_columns:
        if forecasts[column].map(truthy).any():
            failures.append(f"authorization_open:{column}")

    result = {
        "audit_name": "Collector Candidate Methodology v2.3 Audit",
        "audit_version": "2.3.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(forecasts)),
        "complete_count": complete,
        "route_count": int(len(routes)),
        "owner_decision_count": int(len(approvals)),
        "minimum_downside_rate": None if downside.dropna().empty else float(downside.min()),
        "minimum_confidence_0_to_100": None if confidence.dropna().empty else float(confidence.min()),
        "maximum_confidence_0_to_100": None if confidence.dropna().empty else float(confidence.max()),
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "governing_note": "This audit verifies Candidate v2.3 scenario bounds, confidence normalization, owner ceilings, and closed authorization boundaries. It does not certify forecast accuracy or authorize production or purchases.",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
