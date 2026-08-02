from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_short_horizon_winners"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_final_short_horizon_winner_summary.json"
    manifest_path = OUT_DIR / "collector_v1_final_short_horizon_winner_manifest.csv"
    failures: list[dict] = []

    if not summary_path.exists() or not manifest_path.exists():
        failures.append({"check": "required outputs exist", "severity": "CRITICAL"})
        summary = {}
        manifest = pd.DataFrame()
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        manifest = pd.read_csv(manifest_path)

    checks = [
        ("manifest contains 13 resolved cells", len(manifest) == 13, f"rows={len(manifest)}"),
        ("expanded promotions retained", int(summary.get("expanded_promoted_cells", 0)) == 11, f"value={summary.get('expanded_promoted_cells')}"),
        ("limited 365 fallback present", int(summary.get("approved_limited_365_fallback_cells", 0)) == 1, f"value={summary.get('approved_limited_365_fallback_cells')}"),
        ("early cohort fallback present", int(summary.get("certified_early_cohort_fallback_cells", 0)) == 1, f"value={summary.get('certified_early_cohort_fallback_cells')}"),
        ("no unresolved rows", int(summary.get("unresolved_rows", -1)) == 0, f"value={summary.get('unresolved_rows')}"),
        ("cohort fallback certified", summary.get("cohort_fallback_certified") is True, f"value={summary.get('cohort_fallback_certified')}"),
        ("winner set complete", summary.get("winner_set_methodologically_complete") is True, f"value={summary.get('winner_set_methodologically_complete')}"),
        ("production remains blocked", summary.get("production_forecasting_authorized") is False, f"value={summary.get('production_forecasting_authorized')}"),
        ("purchase recommendations remain blocked", summary.get("purchase_recommendations_authorized") is False, f"value={summary.get('purchase_recommendations_authorized')}"),
    ]
    for name, passed, details in checks:
        if not passed:
            failures.append({"check": name, "passed": False, "severity": "CRITICAL", "details": details})

    certified = not failures
    result = {
        "block_name": "Collector V1 Final Short-Horizon Winner Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failures),
        "critical_failures": failures,
        "final_short_horizon_winners_certified": certified,
        "long_horizon_simulation_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Build governed 3-year and 5-year simulation engine from certified winners and calibrated residuals" if certified else "Resolve final winner manifest certification failures",
        "status": "PASS_COLLECTOR_V1_FINAL_SHORT_HORIZON_WINNERS_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_FINAL_SHORT_HORIZON_WINNER_CERTIFICATION",
    }
    (OUT_DIR / "collector_v1_final_short_horizon_winner_certification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
