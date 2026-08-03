from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_long_horizon_simulation_tournament"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_long_horizon_simulation_tournament_summary.json"
    winners_path = OUT_DIR / "collector_v1_long_horizon_method_winners.csv"
    results_path = OUT_DIR / "collector_v1_long_horizon_scenario_results.csv"

    failures: list[dict] = []
    if not summary_path.exists() or not winners_path.exists() or not results_path.exists():
        failures.append({"check": "required outputs exist", "severity": "CRITICAL"})
        summary = {}
        winners = pd.DataFrame()
        results = pd.DataFrame()
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        winners = pd.read_csv(winners_path)
        results = pd.read_csv(results_path)

    checks = [
        ("residual interval authorization consumed", bool(summary), "summary loaded"),
        ("seven simulation methods tested", len(summary.get("methods_tested", [])) == 7, f"methods={len(summary.get('methods_tested', []))}"),
        ("three-year horizon present", 1095 in summary.get("horizons_days", []), f"horizons={summary.get('horizons_days')}"),
        ("five-year horizon present", 1825 in summary.get("horizons_days", []), f"horizons={summary.get('horizons_days')}"),
        ("five scenarios present", len(summary.get("scenarios", [])) == 5, f"scenarios={summary.get('scenarios')}"),
        ("minimum simulation volume met", int(summary.get("simulations_per_route_horizon_scenario", 0)) >= 10000, f"simulations={summary.get('simulations_per_route_horizon_scenario')}"),
        ("all winner routes resolved", int(summary.get("unresolved_winner_routes", 1)) == 0, f"unresolved={summary.get('unresolved_winner_routes')}"),
        ("expected simulation cells produced", int(summary.get("simulation_result_cells", 0)) == int(summary.get("expected_simulation_result_cells", -1)), f"actual={summary.get('simulation_result_cells')} expected={summary.get('expected_simulation_result_cells')}"),
        ("product holdout enforced", summary.get("product_holdout_enforced") is True, f"value={summary.get('product_holdout_enforced')}"),
        ("no direct 3y/5y backtest claim", summary.get("direct_three_five_year_backtest_claimed") is False, f"value={summary.get('direct_three_five_year_backtest_claimed')}"),
        ("winner output exists", not winners.empty, f"rows={len(winners)}"),
        ("scenario output exists", not results.empty, f"rows={len(results)}"),
        ("production remains blocked", summary.get("production_forecasting_authorized") is False, f"value={summary.get('production_forecasting_authorized')}"),
        ("purchase recommendations remain blocked", summary.get("purchase_recommendations_authorized") is False, f"value={summary.get('purchase_recommendations_authorized')}"),
    ]

    for name, passed, details in checks:
        if not passed:
            failures.append({"check": name, "passed": False, "severity": "CRITICAL", "details": details})

    certified = not failures
    result = {
        "block_name": "Collector V1 Long-Horizon Simulation Tournament Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failures),
        "critical_failures": failures,
        "long_horizon_simulation_tournament_certified": certified,
        "decision_readiness_tournament_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Run decision-readiness tournament for ranking and purchase-price stability" if certified else "Remediate unresolved long-horizon method or scenario cells",
        "status": "PASS_COLLECTOR_V1_LONG_HORIZON_SIMULATION_TOURNAMENT_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_LONG_HORIZON_SIMULATION_TOURNAMENT_CERTIFICATION",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "collector_v1_long_horizon_simulation_tournament_certification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
