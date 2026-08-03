from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "config/mtg/governance/collector_long_horizon_model_program_v1.json"
PHASE_2A = ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_long_horizon_evidence_inventory/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(PROGRAM.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    source_path = PHASE_2A / "collector_walk_forward_phase_2a_scored_outcomes.csv"
    failures: list[str] = []
    if not source_path.exists():
        failures.append("missing_phase_2a_scored_outcomes")
        scored = pd.DataFrame()
    else:
        scored = pd.read_csv(source_path, low_memory=False)

    direct_rows: list[dict[str, object]] = []
    if not scored.empty:
        scored["horizon_days"] = pd.to_numeric(scored["horizon_days"], errors="coerce")
        for horizon, group in scored.dropna(subset=["horizon_days"]).groupby("horizon_days"):
            direct_rows.append({
                "horizon_days": int(horizon),
                "case_count": int(len(group)),
                "product_count": int(group["product_key"].nunique()) if "product_key" in group else 0,
                "decision_cutoff_count": int(group["decision_cutoff"].nunique()) if "decision_cutoff" in group else 0,
                "direct_matured_outcomes_available": True,
                "evidence_grade": "A_DIRECT_MATURED" if int(horizon) == 365 else "SUPPORTING_SHORT_HORIZON",
            })
    direct = pd.DataFrame(direct_rows)

    component_rows: list[dict[str, object]] = []
    evidence_map = {
        "product_momentum": True,
        "collector_market_momentum": True,
        "forecast_extremeness_mean_reversion": True,
        "product_age_route": False,
        "volatility_penalty": False,
        "drawdown_penalty": False,
        "liquidity_adjustment": False,
        "asymmetric_uncertainty": False,
        "product_cagr": False,
        "collector_category_cagr": False,
        "comparable_group_cagr": False,
        "product_lifecycle_phase": False,
        "scarcity_score": False,
        "demand_durability_score": False,
        "reprint_substitution_risk": False,
        "bear_base_bull_distribution": False,
        "year_1_calibrated_forecast": True,
        "years_2_3_normalized_cagr": False,
        "years_4_5_terminal_growth": False,
        "growth_decay": False,
        "premium_average_underperformer_probabilities": False,
        "survivorship_obsolescence_risk": False,
        "net_realizable_value": False,
        "proxy_prior": False,
    }
    for horizon_name, spec in cfg["horizons"].items():
        for component in spec["required_components"]:
            available = bool(evidence_map.get(component, False))
            component_rows.append({
                "horizon": horizon_name,
                "model_family": spec["model_family"],
                "component": component,
                "evidence_available": available,
                "status": "AVAILABLE" if available else "GAP_REQUIRES_BUILD",
                "required_before_certification": True,
            })
    components = pd.DataFrame(component_rows)

    output_rows: list[dict[str, object]] = []
    for horizon_name in cfg["horizons"]:
        for field in cfg["required_standard_outputs"]:
            output_rows.append({
                "horizon": horizon_name,
                "required_output": field,
                "contract_defined": True,
                "implemented": False,
                "certified": False,
            })
    standards = pd.DataFrame(output_rows)

    transfer = pd.DataFrame([
        {
            "asset_class": name,
            "transfer_rule": rule,
            "collector_program_must_complete_first": True,
            "class_specific_rebuild_required": True,
            "status": "PLANNED_NOT_STARTED",
        }
        for name, rule in cfg["transfer_program"].items()
    ])

    if components.empty:
        failures.append("component_inventory_empty")
    if standards.empty:
        failures.append("standards_coverage_empty")
    for key in [
        "candidate_methodology_change_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
        "technical_freeze_authorized",
        "uip_acceptance_authorized",
    ]:
        if cfg.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    direct.to_csv(OUT / "collector_long_horizon_direct_evidence.csv", index=False)
    components.to_csv(OUT / "collector_long_horizon_component_inventory.csv", index=False)
    standards.to_csv(OUT / "collector_long_horizon_standards_coverage.csv", index=False)
    transfer.to_csv(OUT / "collector_long_horizon_class_transfer_plan.csv", index=False)

    gap_count = int((components["evidence_available"] == False).sum()) if not components.empty else 0
    result = {
        "audit_name": "Collector Long-Horizon Evidence Inventory",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "direct_evidence_row_count": int(len(direct)),
        "component_count": int(len(components)),
        "component_gap_count": gap_count,
        "required_output_count": int(len(standards)),
        "transfer_class_count": int(len(transfer)),
        "shadow_only": True,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_long_horizon_evidence_inventory_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
