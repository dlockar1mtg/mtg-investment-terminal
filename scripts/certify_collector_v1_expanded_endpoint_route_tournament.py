from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_expanded_tournament"

REQUIRED = [
    "collector_v1_expanded_price_predictions.csv",
    "collector_v1_expanded_early_predictions.csv",
    "collector_v1_expanded_tournament_cells.csv",
    "collector_v1_expanded_tournament_winners.csv",
    "collector_v1_expanded_tournament_gap_register.csv",
    "collector_v1_expanded_tournament_summary.json",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    checks: list[dict] = []
    missing = [name for name in REQUIRED if not (OUT_DIR / name).exists()]
    checks.append({"check": "all expanded tournament artifacts exist", "passed": not missing, "severity": "CRITICAL", "details": f"missing={missing}"})

    if missing:
        failures = [c for c in checks if not c["passed"] and c["severity"] == "CRITICAL"]
    else:
        summary = json.loads((OUT_DIR / "collector_v1_expanded_tournament_summary.json").read_text(encoding="utf-8"))
        price = pd.read_csv(OUT_DIR / "collector_v1_expanded_price_predictions.csv")
        early = pd.read_csv(OUT_DIR / "collector_v1_expanded_early_predictions.csv")
        cells = pd.read_csv(OUT_DIR / "collector_v1_expanded_tournament_cells.csv")
        winners = pd.read_csv(OUT_DIR / "collector_v1_expanded_tournament_winners.csv")

        checks.extend([
            {"check": "expanded tournament summary reports readiness", "passed": bool(summary.get("expanded_tournament_ready")), "severity": "CRITICAL", "details": summary.get("status")},
            {"check": "leave-one-product-out bias correction present", "passed": "holdout_bias_adjustment" in price.columns and "holdout_bias_adjustment" in early.columns, "severity": "CRITICAL", "details": "required in both prediction tables"},
            {"check": "price intervals present", "passed": all(c in price.columns for c in ["interval_80_lower", "interval_80_upper", "interval_90_lower", "interval_90_upper"]), "severity": "CRITICAL", "details": "80% and 90% intervals"},
            {"check": "price candidate cells cover all three governed short horizons", "passed": set(pd.to_numeric(cells.loc[cells["selection_objective"] == "PRICE_FORECAST", "horizon_days"], errors="coerce").dropna().astype(int)) >= {90, 180, 365}, "severity": "CRITICAL", "details": "required={90,180,365}"},
            {"check": "early opportunity objective remains separate", "passed": "EARLY_WINNER_RANKING" in set(cells["selection_objective"].astype(str)), "severity": "CRITICAL", "details": "ranking and price objectives must not be merged"},
            {"check": "winner table covers all modeled route-objective cells", "passed": len(winners) >= 10, "severity": "CRITICAL", "details": f"winner_rows={len(winners)}"},
            {"check": "production remains blocked", "passed": not bool(summary.get("production_forecasting_authorized")) and not bool(summary.get("purchase_recommendations_authorized")) and not bool(summary.get("uip_delivery_authorized")), "severity": "CRITICAL", "details": "must remain false"},
            {"check": "similarity weighting truthfully reported", "passed": summary.get("similarity_weighted_comparables_connected") is False, "severity": "INFORMATIONAL", "details": "known source connection remains outstanding"},
        ])
        failures = [c for c in checks if not c["passed"] and c["severity"] == "CRITICAL"]

    certification = {
        "block_name": "Collector V1 Expanded Endpoint-Route Tournament Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": sum(bool(c["passed"]) for c in checks),
        "critical_failures": failures,
        "expanded_tournament_certified": not failures,
        "winner_promotion_authorized": False,
        "long_horizon_simulation_authorized": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Connect certified comparable similarity scores, resolve blocked winner cells, and certify promoted winners",
        "status": "PASS_COLLECTOR_V1_EXPANDED_TOURNAMENT_CERTIFIED" if not failures else "FAIL_COLLECTOR_V1_EXPANDED_TOURNAMENT_CERTIFICATION",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "collector_v1_expanded_tournament_certification.json").write_text(json.dumps(certification, indent=2), encoding="utf-8")
    pd.DataFrame(checks).to_csv(OUT_DIR / "collector_v1_expanded_tournament_certification_checks.csv", index=False)
    print(json.dumps(certification, indent=2))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
