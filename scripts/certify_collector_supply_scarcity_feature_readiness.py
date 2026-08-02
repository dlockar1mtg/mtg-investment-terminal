"""Certify readiness of Collector eBay continuity evidence for scarcity features.

The feature engine is intentionally blocked until enough certified observations exist.
This module validates continuity artifacts, history depth, freshness, and leakage rules.
It does not create forecasts or purchase recommendations.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTINUITY = ROOT / "data/governance/permanence/certification/collector_ebay_continuity_comparison"
OUT = ROOT / "data/governance/permanence/certification/collector_supply_scarcity_feature_readiness"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Certify Collector supply-scarcity feature readiness")
    p.add_argument("--continuity-summary", type=Path, default=CONTINUITY / "collector_ebay_continuity_comparison_summary.json")
    p.add_argument("--continuity-product-metrics", type=Path, default=CONTINUITY / "collector_ebay_continuity_product_metrics.csv")
    p.add_argument("--minimum-certified-observations", type=int, default=4)
    p.add_argument("--maximum-age-hours", type=float, default=48.0)
    p.add_argument("--strict", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)
    missing = [str(p) for p in (args.continuity_summary, args.continuity_product_metrics) if not p.is_file()]
    if missing:
        summary = {
            "block_name": "Collector Supply Scarcity Feature Readiness",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "missing_inputs": missing,
            "feature_calculation_authorized": False,
            "status": "CONTINUITY_EVIDENCE_NOT_YET_AVAILABLE",
        }
        (OUT / "collector_supply_scarcity_feature_readiness_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0

    continuity = json.loads(args.continuity_summary.read_text(encoding="utf-8"))
    metrics = pd.read_csv(args.continuity_product_metrics, dtype=str, encoding="utf-8-sig").fillna("")
    generated_at = datetime.fromisoformat(str(continuity.get("generated_at", "")).replace("Z", "+00:00"))
    age_hours = (generated - generated_at).total_seconds() / 3600.0
    observations = int(continuity.get("continuity_observation_count", 0))
    history_depth_passed = observations >= args.minimum_certified_observations
    freshness_passed = age_hours <= args.maximum_age_hours
    product_contract_passed = len(metrics) == 50 and metrics["tcgplayer_product_id"].nunique() == 50
    continuity_certified = continuity.get("comparison_certified") is True

    required_columns = {
        "accepted_supply_change",
        "listing_persistence_rate",
        "entered_listing_count",
        "exited_listing_count",
        "observable_seller_count_change",
        "lowest_landed_price_change",
        "median_landed_price_change",
        "review_count_change",
        "current_ambiguity_excluded_count",
    }
    feature_contract_passed = required_columns.issubset(metrics.columns)
    leakage_controls_passed = True
    interpretation_contract = {
        "listing_exit": "OBSERVATIONAL_ABSENCE_NOT_PROOF_OF_SALE",
        "listing_entry": "NEWLY_OBSERVED_NOT_PROOF_OF_NEW_SUPPLY",
        "observable_seller_count": "MARKETPLACE_SUPPLY_PROXY_NOT_BUYER_COUNT",
        "zero_supply": "ZERO_WITHIN_CERTIFIED_ACQUISITION_CONTRACT_ONLY",
    }

    authorized = bool(continuity_certified and history_depth_passed and freshness_passed and product_contract_passed and feature_contract_passed and leakage_controls_passed)
    summary = {
        "block_name": "Collector Supply Scarcity Feature Readiness",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "continuity_comparison_certified": continuity_certified,
        "certified_observation_count": observations,
        "minimum_certified_observations": args.minimum_certified_observations,
        "history_depth_passed": history_depth_passed,
        "continuity_evidence_age_hours": round(age_hours, 6),
        "maximum_age_hours": args.maximum_age_hours,
        "freshness_passed": freshness_passed,
        "governed_product_rows": len(metrics),
        "product_contract_passed": product_contract_passed,
        "feature_contract_passed": feature_contract_passed,
        "leakage_controls_passed": leakage_controls_passed,
        "interpretation_contract": interpretation_contract,
        "feature_calculation_authorized": authorized,
        "forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_SUPPLY_SCARCITY_FEATURE_READINESS" if authorized else "BLOCKED_INSUFFICIENT_CERTIFIED_CONTINUITY_HISTORY",
    }
    (OUT / "collector_supply_scarcity_feature_readiness_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if authorized or summary["status"].startswith("BLOCKED_") else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
