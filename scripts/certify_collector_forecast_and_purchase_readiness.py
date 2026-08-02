"""Certify Collector forecast and purchase-readiness without bypassing upstream gates."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCARCITY = ROOT / "data/governance/permanence/certification/collector_supply_scarcity_feature_readiness/collector_supply_scarcity_feature_readiness_summary.json"
OUT = ROOT / "data/governance/permanence/certification/collector_forecast_and_purchase_readiness"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Certify Collector forecast and purchase readiness")
    p.add_argument("--scarcity-readiness", type=Path, default=SCARCITY)
    p.add_argument("--strict", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)
    if not args.scarcity_readiness.is_file():
        summary = {
            "block_name": "Collector Forecast and Purchase Readiness",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "scarcity_features_authorized": False,
            "forecast_experiment_authorized": False,
            "production_forecasting_authorized": False,
            "purchase_recommendations_authorized": False,
            "uip_delivery_authorized": False,
            "status": "BLOCKED_SCARCITY_READINESS_NOT_AVAILABLE",
        }
        (OUT / "collector_forecast_and_purchase_readiness_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0

    scarcity = json.loads(args.scarcity_readiness.read_text(encoding="utf-8"))
    feature_authorized = scarcity.get("feature_calculation_authorized") is True
    history_depth = int(scarcity.get("certified_observation_count", 0))
    feature_contract = scarcity.get("feature_contract_passed") is True
    freshness = scarcity.get("freshness_passed") is True
    leakage = scarcity.get("leakage_controls_passed") is True

    forecast_experiment_authorized = bool(feature_authorized and feature_contract and freshness and leakage)
    production_forecasting_authorized = False
    purchase_authorized = False
    summary = {
        "block_name": "Collector Forecast and Purchase Readiness",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "scarcity_features_authorized": feature_authorized,
        "certified_observation_count": history_depth,
        "feature_contract_passed": feature_contract,
        "freshness_passed": freshness,
        "leakage_controls_passed": leakage,
        "forecast_experiment_authorized": forecast_experiment_authorized,
        "production_forecasting_authorized": production_forecasting_authorized,
        "purchase_recommendations_authorized": purchase_authorized,
        "uip_delivery_authorized": False,
        "remaining_production_gates": [
            "Run governed forecast experiments against certified feature vintages",
            "Backtest by forecast horizon without future leakage",
            "Calibrate uncertainty and prediction intervals",
            "Pass product-level and portfolio-level forecast validation",
            "Approve production forecast version",
            "Run decision-engine eligibility and risk gates",
        ],
        "status": (
            "PASS_FORECAST_EXPERIMENT_READINESS_PRODUCTION_STILL_BLOCKED"
            if forecast_experiment_authorized
            else "BLOCKED_UPSTREAM_SCARCITY_FEATURE_GATES"
        ),
    }
    (OUT / "collector_forecast_and_purchase_readiness_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
