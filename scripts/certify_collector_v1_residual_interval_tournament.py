from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_residual_interval_tournament"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_residual_interval_tournament_summary.json"
    winners_path = OUT_DIR / "collector_v1_residual_interval_winners.csv"
    predictions_path = OUT_DIR / "collector_v1_residual_interval_predictions.csv"
    failures: list[dict] = []

    if not summary_path.exists() or not winners_path.exists() or not predictions_path.exists():
        summary = {}
        winners = pd.DataFrame()
        predictions = pd.DataFrame()
        failures.append({"check": "required outputs exist", "severity": "CRITICAL"})
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        winners = pd.read_csv(winners_path)
        predictions = pd.read_csv(predictions_path)

    checks = [
        ("historical evidence populated", int(summary.get("historical_evidence_rows", 0)) >= 100, f"rows={summary.get('historical_evidence_rows')}"),
        ("multiple routes evaluated", len(summary.get("routes", [])) >= 3, f"routes={summary.get('routes')}"),
        ("all six methods tested", len(summary.get("methods_tested", [])) == 6, f"methods={summary.get('methods_tested')}"),
        ("both interval levels tested", sorted(summary.get("interval_levels", [])) == [0.8, 0.9], f"levels={summary.get('interval_levels')}"),
        ("winner cells populated", not winners.empty, f"rows={len(winners)}"),
        ("all winner cells promoted", bool(not winners.empty and (winners["promotion_status"] == "PROMOTABLE").all()), f"blocked={0 if winners.empty else int((winners['promotion_status'] != 'PROMOTABLE').sum())}"),
        ("product holdout enforced", summary.get("product_holdout_enforced") is True and bool(not predictions.empty and predictions["product_holdout_enforced"].astype(str).str.lower().eq("true").all()), "holdout must be true for all rows"),
        ("interval ordering valid", bool(not predictions.empty and (predictions["upper"] >= predictions["lower"]).all()), "upper must be >= lower"),
        ("long horizon authorized after certification", summary.get("long_horizon_simulation_tournament_authorized_after_certification") is True, f"value={summary.get('long_horizon_simulation_tournament_authorized_after_certification')}"),
        ("production remains blocked", summary.get("production_forecasting_authorized") is False, f"value={summary.get('production_forecasting_authorized')}"),
        ("purchase remains blocked", summary.get("purchase_recommendations_authorized") is False, f"value={summary.get('purchase_recommendations_authorized')}"),
    ]
    for name, passed, details in checks:
        if not passed:
            failures.append({"check": name, "passed": False, "severity": "CRITICAL", "details": details})

    certified = not failures
    result = {
        "block_name": "Collector V1 Residual and Prediction Interval Tournament Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failures),
        "critical_failures": failures,
        "residual_interval_tournament_certified": certified,
        "long_horizon_simulation_tournament_authorized": certified,
        "decision_readiness_tournament_required": True,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Run governed 3-year and 5-year simulation tournament" if certified else "Resolve blocked residual interval winner cells without lowering gates",
        "status": "PASS_COLLECTOR_V1_RESIDUAL_INTERVAL_TOURNAMENT_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_RESIDUAL_INTERVAL_TOURNAMENT_CERTIFICATION",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "collector_v1_residual_interval_tournament_certification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
