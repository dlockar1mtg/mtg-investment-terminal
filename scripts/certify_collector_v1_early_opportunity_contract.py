from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/governance/collector_v1_early_opportunity_contract.json"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_contract"
OUT = OUT_DIR / "collector_v1_early_opportunity_contract_certification.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    if not CONTRACT.exists():
        failures.append(f"Missing contract: {CONTRACT.relative_to(ROOT)}")
        contract = {}
    else:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    required_signal_groups = {
        "price_formation",
        "supply",
        "demand_proxies",
        "product_structure",
        "comparable_transfer",
    }
    signal_groups = set(contract.get("required_signal_groups", {}))
    if not required_signal_groups.issubset(signal_groups):
        failures.append(f"Missing signal groups: {sorted(required_signal_groups - signal_groups)}")

    requirements = contract.get("tournament_requirements", {})
    for key in [
        "must_include_early_winner_classifier",
        "must_include_first_year_return_regression",
        "must_test_product_holdouts",
        "must_test_release_cohort_holdouts",
        "must_compare_equal_weight_and_similarity_weighted_peers",
        "must_compare_no_scarcity_and_ssi_v1a",
        "must_report_precision_at_top_k",
        "must_report_recall_of_historical_first_year_winners",
        "must_report_false_positive_rate",
        "must_report_downside_capture",
        "must_report_rank_correlation",
    ]:
        if requirements.get(key) is not True:
            failures.append(f"Tournament requirement not enabled: {key}")

    additional_inputs = contract.get("additional_inputs_to_integrate", [])
    required_inputs = {
        "release_price_anchor",
        "historical_first_year_peer_outcomes",
        "comparable_similarity_scores",
        "historical_supply_snapshots",
        "print_and_distribution_proxies",
        "demand_and_attention_proxies",
    }
    found_inputs = {str(row.get("name")) for row in additional_inputs}
    if not required_inputs.issubset(found_inputs):
        failures.append(f"Missing additional input definitions: {sorted(required_inputs - found_inputs)}")

    outputs = set(contract.get("required_outputs", []))
    required_outputs = {
        "early_opportunity_probability",
        "probability_first_year_return_ge_25pct",
        "probability_first_year_return_ge_50pct",
        "expected_first_year_return",
        "p10_first_year_return",
        "p50_first_year_return",
        "p90_first_year_return",
        "maximum_purchase_price",
        "authorization_state",
        "source_lineage",
    }
    if not required_outputs.issubset(outputs):
        failures.append(f"Missing outputs: {sorted(required_outputs - outputs)}")

    promotion = contract.get("promotion_rules", {})
    for key in [
        "purchase_signal_requires_calibrated_probability",
        "purchase_signal_requires_lower_bound_positive_expected_return",
        "purchase_signal_requires_comparable_lineage",
        "purchase_signal_requires_current_price_quality",
        "presale_signals_require_wider_uncertainty",
        "zero_history_products_cannot_use_direct_history_label",
        "no_input_may_be_silently_imputed",
    ]:
        if promotion.get(key) is not True:
            failures.append(f"Promotion safeguard not enabled: {key}")

    certified = not failures
    result = {
        "block_name": "Collector V1 Early Opportunity Contract Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "route": contract.get("route"),
        "maximum_history_months": contract.get("eligibility", {}).get("maximum_history_months"),
        "signal_group_count": len(signal_groups),
        "additional_input_count": len(additional_inputs),
        "required_output_count": len(outputs),
        "failures": failures,
        "early_opportunity_contract_certified": certified,
        "short_history_tournament_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Build early-opportunity feature and historical winner dataset" if certified else "Resolve early-opportunity governance failures",
        "status": "PASS_COLLECTOR_V1_EARLY_OPPORTUNITY_CONTRACT_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_EARLY_OPPORTUNITY_CONTRACT_CERTIFICATION",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if args.strict and not certified else 0


if __name__ == "__main__":
    raise SystemExit(main())
