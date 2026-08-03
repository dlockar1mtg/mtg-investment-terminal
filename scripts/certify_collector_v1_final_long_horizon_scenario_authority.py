from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_long_horizon_scenario_authority"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_final_long_horizon_scenario_authority_summary.json"
    results_path = OUT_DIR / "collector_v1_final_long_horizon_scenario_results.csv"
    winners_path = OUT_DIR / "collector_v1_final_long_horizon_method_winners.csv"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    results = pd.read_csv(results_path)
    winners = pd.read_csv(winners_path)

    expected_routes = {
        "COMPARABLE_PRODUCT_ADJUSTED",
        "DIRECT_HISTORY_CALIBRATED",
        "DIRECT_HISTORY_LIMITED",
        "EARLY_OPPORTUNITY_COHORT_FALLBACK",
    }
    required_scenarios = {
        "BASE",
        "SCARCITY_UPSIDE",
        "SUPPLY_EXPANSION",
        "DEMAND_CONTRACTION",
        "LIQUIDITY_SHOCK",
    }

    checks = [
        ("summary_complete", summary.get("final_scenario_authority_complete") is True),
        ("four_routes_present", set(results["route"].astype(str)) == expected_routes),
        ("four_method_winners_present", set(winners["route"].astype(str)) == expected_routes),
        ("two_horizons_present", set(results["horizon_days"].astype(int)) == {1095, 1825}),
        ("five_scenarios_present", set(results["scenario"].astype(str)) == required_scenarios),
        ("forty_cells_present", len(results) == 40),
        ("ten_thousand_simulations_each", (results["simulations"].astype(int) == 10000).all()),
        ("four_hundred_thousand_draws", int(results["simulations"].sum()) == 400000),
        ("all_quantiles_ordered", ((results["p05_terminal_index"] <= results["p10_terminal_index"]) & (results["p10_terminal_index"] <= results["p25_terminal_index"]) & (results["p25_terminal_index"] <= results["median_terminal_index"]) & (results["median_terminal_index"] <= results["p75_terminal_index"]) & (results["p75_terminal_index"] <= results["p90_terminal_index"]) & (results["p90_terminal_index"] <= results["p95_terminal_index"])).all()),
        ("probabilities_bounded", results[["probability_of_loss", "probability_gain_25pct", "probability_gain_50pct"]].apply(lambda s: s.between(0, 1).all()).all()),
        ("deterministic_seed_present", results["deterministic_seed"].notna().all()),
        ("no_direct_3y_5y_backtest_claim", summary.get("direct_three_five_year_backtest_claimed") is False),
        ("decision_readiness_authorized", summary.get("decision_readiness_tournament_authorized_after_certification") is True),
        ("production_not_authorized", summary.get("production_forecasting_authorized") is False),
        ("purchase_not_authorized", summary.get("purchase_recommendations_authorized") is False),
        ("uip_not_authorized", summary.get("uip_delivery_authorized") is False),
    ]

    failures = [name for name, passed in checks if not passed]
    certified = not failures
    payload = {
        "block_name": "Collector V1 Final Long-Horizon Scenario Authority Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failures),
        "critical_failures": failures,
        "final_long_horizon_scenario_authority_certified": certified,
        "decision_readiness_tournament_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Run decision-readiness tournament across rankings, downside risk, purchase-price stability, route delegation, and scenario sensitivity",
        "status": "PASS_COLLECTOR_V1_FINAL_LONG_HORIZON_SCENARIO_AUTHORITY_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_FINAL_LONG_HORIZON_SCENARIO_AUTHORITY_CERTIFICATION",
    }
    (OUT_DIR / "collector_v1_final_long_horizon_scenario_authority_certification.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
