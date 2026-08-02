from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/governance/collector_v1_model_tournament_contract.json"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_model_tournament_contract"
OUT = OUT_DIR / "collector_v1_model_tournament_contract_certification.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    failures: list[dict] = []
    if not CONTRACT.exists():
        failures.append({"check": "contract exists", "details": str(CONTRACT)})
        contract = {}
    else:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    required_endpoints = {90, 180, 365, 1095, 1825}
    actual_endpoints = set(contract.get("required_endpoints_days", []))
    if actual_endpoints != required_endpoints:
        failures.append({"check": "all required endpoints governed", "details": sorted(actual_endpoints)})

    required_routes = {
        "DIRECT_HISTORY_CALIBRATED",
        "DIRECT_HISTORY_LIMITED",
        "COMPARABLE_PRODUCT_ADJUSTED",
    }
    routing = contract.get("routing_policy", {})
    missing_routes = sorted(required_routes - set(routing))
    if missing_routes:
        failures.append({"check": "all forecast routes governed", "details": missing_routes})

    validation = contract.get("required_validation", {})
    for key in [
        "time_ordered_cutoffs",
        "anti_leakage",
        "rolling_origin",
        "route_specific_evaluation",
        "endpoint_specific_evaluation",
        "product_level_holdout",
    ]:
        if validation.get(key) is not True:
            failures.append({"check": f"validation control {key}", "details": validation.get(key)})

    winner = contract.get("winner_selection", {})
    if winner.get("no_single_global_winner") is not True:
        failures.append({"check": "endpoint-route winner policy", "details": winner})

    long_horizon = contract.get("long_horizon_policy", {})
    for endpoint in ["1095", "1825"]:
        if endpoint not in long_horizon:
            failures.append({"check": f"long-horizon policy {endpoint}", "details": "missing"})

    decision = contract.get("investment_decision_policy", {})
    required_purchase = set(decision.get("purchase_authorization_requires", []))
    for item in [
        "endpoint-route tournament winner",
        "calibrated interval",
        "maximum purchase price",
    ]:
        if item not in required_purchase:
            failures.append({"check": f"purchase gate {item}", "details": sorted(required_purchase)})

    certified = not failures
    result = {
        "block_name": "Collector V1 Model Tournament Contract Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "required_endpoints_days": sorted(actual_endpoints),
        "model_family_count": len(contract.get("required_model_families", [])),
        "feature_variant_count": len(contract.get("required_feature_variants", [])),
        "failures": failures,
        "tournament_contract_certified": certified,
        "large_tournament_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Build endpoint-route tournament engine" if certified else "Resolve tournament governance failures",
        "status": "PASS_COLLECTOR_V1_MODEL_TOURNAMENT_CONTRACT_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_MODEL_TOURNAMENT_CONTRACT",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if args.strict and not certified else 0


if __name__ == "__main__":
    raise SystemExit(main())
