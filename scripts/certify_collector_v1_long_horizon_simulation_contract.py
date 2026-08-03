from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/governance/collector_v1_long_horizon_simulation_contract.json"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_long_horizon_simulation_contract"
OUT = OUT_DIR / "collector_v1_long_horizon_simulation_contract_certification.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []

    if contract.get("required_horizons_days") != [1095, 1825]:
        failures.append("Required long-horizon endpoints must be exactly 1095 and 1825 days.")
    if int(contract.get("minimum_simulations_per_product_horizon", 0)) < 10000:
        failures.append("Minimum simulations must be at least 10,000 per product-horizon.")
    required_methods = {
        "BOOTSTRAPPED_MONTHLY_RETURN_PATHS",
        "BLOCK_BOOTSTRAP_RETURN_PATHS",
        "REGIME_CONDITIONED_MONTE_CARLO",
        "COMPARABLE_MATURITY_CURVE_SIMULATION",
        "ENSEMBLED_LONG_HORIZON_SIMULATION",
    }
    if not required_methods.issubset(set(contract.get("simulation_methods", []))):
        failures.append("Required robust simulation families are missing.")
    required_outputs = {
        "p10_price", "p25_price", "median_price", "p75_price", "p90_price",
        "probability_of_loss", "maximum_drawdown_distribution",
        "projection_classification", "model_and_comparable_lineage",
    }
    if not required_outputs.issubset(set(contract.get("required_outputs", []))):
        failures.append("Required distributional outputs are missing.")
    rules = contract.get("anti_overconfidence_rules", {})
    for key in [
        "uncertainty_must_widen_with_horizon",
        "no_single_path_output",
        "no_purchase_authorization_from_mean_only",
        "scenario_only_outputs_cannot_be_labeled_backtested",
    ]:
        if rules.get(key) is not True:
            failures.append(f"Anti-overconfidence rule is not enforced: {key}")
    auth = contract.get("authorization", {})
    if auth.get("production_forecasting_authorized") is not False:
        failures.append("Contract must not authorize production forecasting.")
    if auth.get("purchase_recommendations_authorized") is not False:
        failures.append("Contract must not authorize purchases.")

    certified = not failures
    result = {
        "block_name": "Collector V1 Long-Horizon Simulation Contract Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "required_horizons_days": contract.get("required_horizons_days", []),
        "minimum_simulations_per_product_horizon": contract.get("minimum_simulations_per_product_horizon"),
        "simulation_method_count": len(contract.get("simulation_methods", [])),
        "required_output_count": len(contract.get("required_outputs", [])),
        "failures": failures,
        "long_horizon_contract_certified": certified,
        "long_horizon_engine_authorized_after_prerequisites": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Build endpoint-route tournament engine, then long-horizon simulation engine",
        "status": "PASS_COLLECTOR_V1_LONG_HORIZON_SIMULATION_CONTRACT_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_LONG_HORIZON_SIMULATION_CONTRACT_CERTIFICATION",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if args.strict and not certified else 0


if __name__ == "__main__":
    raise SystemExit(main())
