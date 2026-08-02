"""Certify Collector forecast-experiment readiness from currently available governed data.

Continuity is optional enhancement evidence, not a prerequisite for forecast development.
Production forecasts and purchases remain gated by backtesting, calibration, validation,
and decision-engine approval.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_current_data_forecast_readiness"
BASELINE_SUMMARY = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline/collector_ebay_day_one_supply_baseline_summary.json"

REQUIRED_IMPLEMENTATION = [
    ROOT / "scripts/audit_collector_evidence_readiness.py",
    ROOT / "scripts/normalize_collector_evidence.py",
    ROOT / "scripts/route_collector_forecast_methods.py",
    ROOT / "scripts/select_collector_comparables.py",
    ROOT / "config/mtg/governance/collector_forecast_method_router_v1.json",
]

EVIDENCE_PATTERNS = {
    "pricing_history": ("*price*history*.csv", "*historical*price*.csv", "*tcgcsv*.csv"),
    "forecast_horizons": ("*forecast*horizon*.csv", "*universal_forecast*.csv"),
    "normalized_evidence": ("*collector*evidence*.csv", "*normalized*evidence*.csv"),
    "comparables": ("*collector*comparable*.csv", "*comparable*selection*.csv"),
    "release_authority": ("*release*authority*.csv", "*collector*universe*.csv", "*product*authority*.csv"),
    "ebay_current_snapshot": ("*day_one_product_supply_snapshot.csv",),
    "ebay_historical_reconstruction": ("*historical*reconstruction*.csv", "*historical*evidence*.csv"),
}


def discover(patterns: tuple[str, ...]) -> list[str]:
    found: set[str] = set()
    for pattern in patterns:
        for path in ROOT.rglob(pattern):
            if path.is_file() and ".git" not in path.parts:
                found.add(str(path.relative_to(ROOT)))
    return sorted(found)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)
    baseline = json.loads(BASELINE_SUMMARY.read_text(encoding="utf-8")) if BASELINE_SUMMARY.is_file() else {}
    implementation = {str(p.relative_to(ROOT)): p.is_file() for p in REQUIRED_IMPLEMENTATION}
    evidence = {name: discover(patterns) for name, patterns in EVIDENCE_PATTERNS.items()}

    required_evidence = (
        bool(evidence["pricing_history"])
        and bool(evidence["release_authority"])
        and bool(evidence["ebay_current_snapshot"])
    )
    foundation_ready = all(implementation.values())
    baseline_ready = baseline.get("baseline_promoted") is True and baseline.get("baseline_integrity_passed") is True
    forecast_experiment_authorized = foundation_ready and required_evidence and baseline_ready

    summary = {
        "block_name": "Collector Current-Data Forecast Readiness",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "governance_correction": {
            "continuity_required_for_forecast_experiments": False,
            "continuity_role": "OPTIONAL_FUTURE_ENHANCEMENT_AND_VALIDATION_STREAM",
            "current_certified_ebay_snapshot_role": "CURRENT_MARKET_SUPPLY_FEATURE_VINTAGE",
            "production_authorization_basis": "BACKTESTING_CALIBRATION_VALIDATION_AND_DECISION_GATES",
        },
        "implementation_artifacts": implementation,
        "evidence_artifacts": evidence,
        "forecast_foundation_ready": foundation_ready,
        "required_current_evidence_ready": required_evidence,
        "day_one_baseline_ready": baseline_ready,
        "forecast_experiment_authorized": forecast_experiment_authorized,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "remaining_experiment_gates": [
            "Build current-data feature matrix for all governed Collector products",
            "Generate governed candidate forecasts by routed method",
            "Backtest historical products and comparable cohorts by horizon",
            "Calibrate uncertainty and prediction intervals",
            "Validate product-level and portfolio-level performance",
            "Approve one production forecast version",
            "Run decision-engine eligibility and risk gates",
        ],
        "status": (
            "PASS_CURRENT_DATA_FORECAST_EXPERIMENTS_AUTHORIZED"
            if forecast_experiment_authorized
            else "REVIEW_CURRENT_DATA_FORECAST_READINESS_GAPS"
        ),
    }
    path = OUT / "collector_current_data_forecast_readiness_summary.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if forecast_experiment_authorized else 1


if __name__ == "__main__":
    raise SystemExit(main())
