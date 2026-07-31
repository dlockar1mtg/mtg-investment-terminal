from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_forecast_diagnostics_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    out_dir = ROOT / cfg["output_directory"]
    required = [
        "collector_candidate_forecast_diagnostics.csv",
        "collector_candidate_peer_contributions.csv",
        "collector_candidate_forecast_route_summary.csv",
        "collector_comparable_source_discovery.csv",
        "collector_discovered_comparable_edges.csv",
        "collector_candidate_forecast_diagnostics_summary.json",
    ]
    for name in required:
        if not (out_dir / name).exists():
            failures.append(f"missing_output:{name}")

    summary: dict = {}
    if not failures:
        summary = json.loads((out_dir / "collector_candidate_forecast_diagnostics_summary.json").read_text(encoding="utf-8"))
        forecasts = pd.read_csv(out_dir / "collector_candidate_forecast_diagnostics.csv", low_memory=False)
        if len(forecasts) != 51:
            failures.append(f"unexpected_product_count:{len(forecasts)}")
        if forecasts["canonical_tcgplayer_product_id"].astype(str).duplicated().any():
            failures.append("duplicate_product_ids")
        for column in [
            "forecast_method_route", "candidate_model_version", "missing_components",
            "candidate_calculation_complete", "confidence_score", "confidence_class",
            "candidate_projection_authorized", "production_projection_authorized",
            "purchase_recommendation_authorized",
        ]:
            if column not in forecasts.columns:
                failures.append(f"missing_forecast_column:{column}")
        for column in ["candidate_projection_authorized", "production_projection_authorized", "purchase_recommendation_authorized"]:
            if column in forecasts.columns and forecasts[column].astype(str).str.lower().eq("true").any():
                failures.append(f"authorization_true_in_output:{column}")
        if "retrospective_inputs_used_for_diagnostics_only" in forecasts.columns:
            if not forecasts["retrospective_inputs_used_for_diagnostics_only"].astype(str).str.lower().eq("true").all():
                failures.append("retrospective_diagnostic_flag_not_universal")
        else:
            failures.append("missing_retrospective_diagnostic_flag")
        if forecasts["forecast_method_route"].nunique(dropna=True) < 4:
            failures.append("expected_route_coverage_missing")
        future = forecasts[forecasts["future_release"].astype(str).str.lower().eq("true")]
        if not future.empty and future["current_investment_eligible"].astype(str).str.lower().eq("true").any():
            failures.append("future_release_marked_investment_eligible")

    auth = cfg.get("authorizations", {})
    for key, value in auth.items():
        if bool(value):
            failures.append(f"authorization_must_remain_false:{key}")

    result = {
        "audit_name": "Collector Candidate Forecast Diagnostics Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "product_count": summary.get("product_count", 0),
        "candidate_calculation_complete_count": summary.get("candidate_calculation_complete_count", 0),
        "candidate_calculation_incomplete_count": summary.get("candidate_calculation_incomplete_count", 0),
        "discovered_comparable_edge_count": summary.get("discovered_comparable_edge_count", 0),
        "used_peer_contribution_count": summary.get("used_peer_contribution_count", 0),
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "future_information_prohibited": True,
        "governing_note": "This audit validates inactive diagnostic outputs, disclosure, scope, and closed authorizations. It does not certify forecast accuracy or purchase suitability.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if failures and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
