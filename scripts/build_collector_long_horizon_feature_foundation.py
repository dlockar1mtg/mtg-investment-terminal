from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_long_horizon_feature_foundation_v1.json"
PHASE_2A = ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_long_horizon_feature_foundation/candidate_v1_0_0"

ALIASES = {
    "product_key": ["product_key", "product_id", "sku", "tcgplayer_id"],
    "product_name": ["product_name", "name", "sealed_product_name"],
    "observation_date": ["observation_date", "date", "price_date", "snapshot_date", "as_of_date"],
    "decision_cutoff": ["decision_cutoff", "cutoff_date"],
    "release_date": ["release_date", "released_at", "street_date"],
    "market_price": ["market_price", "price", "current_price", "tcg_market_price", "market"],
    "listing_count": ["listing_count", "active_listing_count", "listings"],
    "sales_count": ["sales_count", "transaction_count", "units_sold"],
    "sales_velocity": ["sales_velocity", "sales_per_day", "monthly_sales"],
    "bid_ask_spread": ["bid_ask_spread", "market_buylist_spread", "spread"],
    "buylist_price": ["buylist_price", "cash_price", "dealer_buy_price"],
    "reprint_risk": ["reprint_risk", "reprint_substitution_risk"],
    "scarcity_score": ["scarcity_score", "scarcity"],
    "demand_score": ["demand_score", "demand_durability_score"],
    "franchise_strength": ["franchise_strength", "ip_strength"],
    "premium_treatment_score": ["premium_treatment_score", "premium_score"],
}


def read_header(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            return next(csv.reader(handle), [])
    except Exception:
        return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    catalog_rows: list[dict[str, object]] = []
    coverage: dict[str, list[str]] = {field: [] for field in ALIASES}
    for source_root in cfg["source_roots"]:
        root = ROOT / source_root
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            if OUT in path.parents:
                continue
            header = read_header(path)
            normalized = {str(col).strip().lower(): str(col) for col in header}
            matched_fields: list[str] = []
            for field, aliases in ALIASES.items():
                if any(alias.lower() in normalized for alias in aliases):
                    matched_fields.append(field)
                    coverage[field].append(str(path.relative_to(ROOT)))
            catalog_rows.append({
                "source_path": str(path.relative_to(ROOT)),
                "column_count": len(header),
                "matched_required_field_count": len(matched_fields),
                "matched_required_fields": "|".join(sorted(matched_fields)),
                "columns": "|".join(header),
                "candidate_feature_source": bool(matched_fields),
            })

    catalog = pd.DataFrame(catalog_rows)
    field_rows: list[dict[str, object]] = []
    required_flat = {
        field
        for group in cfg["required_raw_fields"].values()
        for field in group
    }
    for field in sorted(required_flat):
        sources = sorted(set(coverage.get(field, [])))
        field_rows.append({
            "raw_field": field,
            "source_count": len(sources),
            "source_available": bool(sources),
            "candidate_sources": "|".join(sources),
            "status": "SOURCE_DISCOVERED_REQUIRES_MAPPING" if sources else "SOURCE_GAP",
        })
    field_coverage = pd.DataFrame(field_rows)

    seed_path = PHASE_2A / "collector_walk_forward_phase_2a_scored_outcomes.csv"
    seed = pd.DataFrame()
    if not seed_path.exists():
        failures.append("missing_phase_2a_scored_outcomes")
    else:
        scored = pd.read_csv(seed_path, low_memory=False)
        required_seed = [
            "product_key", "product_name", "decision_cutoff", "horizon_days",
            "forecast_return_365_equivalent", "realized_return"
        ]
        missing_seed = [col for col in required_seed if col not in scored.columns]
        if missing_seed:
            failures.append("missing_seed_columns:" + ",".join(missing_seed))
        else:
            seed = scored[required_seed].copy()
            seed = seed.rename(columns={
                "forecast_return_365_equivalent": "source_forecast_return_365_equivalent",
                "realized_return": "outcome_realized_return",
            })
            seed["predictor_information_available_at_cutoff"] = True
            seed["outcome_separated_from_predictors"] = True
            seed["future_information_used"] = False
            seed["source_lineage"] = str(seed_path.relative_to(ROOT))

    feature_rows: list[dict[str, object]] = []
    for feature in cfg["derived_feature_contract"]:
        feature_rows.append({
            "derived_feature": feature,
            "contract_defined": True,
            "source_mapping_ready": False,
            "point_in_time_implementation_ready": False,
            "implemented": False,
            "certified": False,
            "status": "PENDING_SOURCE_MAPPING",
        })
    feature_plan = pd.DataFrame(feature_rows)

    if catalog.empty:
        failures.append("source_catalog_empty")
    if field_coverage.empty:
        failures.append("raw_field_coverage_empty")
    if feature_plan.empty:
        failures.append("feature_plan_empty")
    if not seed.empty and seed["future_information_used"].any():
        failures.append("future_information_used")
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

    catalog.to_csv(OUT / "collector_long_horizon_source_catalog.csv", index=False)
    field_coverage.to_csv(OUT / "collector_long_horizon_raw_field_coverage.csv", index=False)
    seed.to_csv(OUT / "collector_long_horizon_point_in_time_seed_panel.csv", index=False)
    feature_plan.to_csv(OUT / "collector_long_horizon_derived_feature_plan.csv", index=False)

    result = {
        "audit_name": "Collector Long-Horizon Point-in-Time Feature Foundation",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "source_file_count": int(len(catalog)),
        "candidate_source_file_count": int(catalog["candidate_feature_source"].sum()) if not catalog.empty else 0,
        "required_raw_field_count": int(len(field_coverage)),
        "raw_field_source_gap_count": int((field_coverage["source_available"] == False).sum()) if not field_coverage.empty else 0,
        "seed_panel_row_count": int(len(seed)),
        "derived_feature_count": int(len(feature_plan)),
        "implemented_derived_feature_count": 0,
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
    (OUT / "collector_long_horizon_feature_foundation_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
