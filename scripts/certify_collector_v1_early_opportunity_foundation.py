from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_foundation"
SUMMARY = BASE / "collector_v1_early_opportunity_foundation_summary.json"
REQUIRED = [
    BASE / "collector_v1_first_year_outcomes.csv",
    BASE / "collector_v1_peer_maturity_curves.csv",
    BASE / "collector_v1_release_age_cutoffs.csv",
    BASE / "collector_v1_early_opportunity_predictions.csv",
    BASE / "collector_v1_early_opportunity_tournament_metrics.csv",
    BASE / "collector_v1_early_opportunity_winners_by_age.csv",
    BASE / "collector_v1_early_opportunity_input_gap_register.csv",
]
OUT = BASE / "collector_v1_early_opportunity_foundation_certification.json"
CHECKS = BASE / "collector_v1_early_opportunity_foundation_checks.csv"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    checks: list[dict] = []
    def add(name: str, passed: bool, details: str, severity: str = "CRITICAL") -> None:
        checks.append({"check": name, "passed": bool(passed), "severity": severity, "details": details})

    missing = [str(p.relative_to(ROOT)) for p in [SUMMARY, *REQUIRED] if not p.exists()]
    add("all early opportunity artifacts exist", not missing, f"missing={missing}")

    summary = {}
    outcomes = cutoffs = metrics = winners = gaps = pd.DataFrame()
    if not missing:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        outcomes = pd.read_csv(REQUIRED[0], low_memory=False)
        cutoffs = pd.read_csv(REQUIRED[2], low_memory=False)
        metrics = pd.read_csv(REQUIRED[4], low_memory=False)
        winners = pd.read_csv(REQUIRED[5], low_memory=False)
        gaps = pd.read_csv(REQUIRED[6], low_memory=False)

        realized = int(pd.to_numeric(outcomes.get("return_365d"), errors="coerce").notna().sum())
        add("at least ten realized first-year products exist", realized >= 10, f"realized={realized}")
        add("release-age cutoff rows exist", len(cutoffs) > 0, f"rows={len(cutoffs)}")
        add("cutoffs include early ages", {0, 1, 2, 3}.issubset(set(pd.to_numeric(cutoffs.get("age_months"), errors="coerce").dropna().astype(int))), f"ages={sorted(pd.to_numeric(cutoffs.get('age_months'), errors='coerce').dropna().astype(int).unique().tolist())}")
        add("anti-leakage controls pass", bool(summary.get("anti_leakage_pass")), f"anti_leakage_pass={summary.get('anti_leakage_pass')}")
        add("multiple tournament variants were tested", metrics.get("model_variant", pd.Series(dtype=str)).nunique() >= 3, f"variants={metrics.get('model_variant', pd.Series(dtype=str)).nunique()}")
        add("winners selected by product age", len(winners) >= 4, f"winner_rows={len(winners)}")
        add("ranking metrics are present", {"top_quintile_precision_25pct", "winner_recall_25pct", "false_positive_rate", "rank_correlation"}.issubset(metrics.columns), f"columns={list(metrics.columns)}")
        add("input gap register is present", len(gaps) >= 1, f"gap_rows={len(gaps)}", severity="CONTROL")
        add("builder reported no blockers", not summary.get("blockers"), f"blockers={summary.get('blockers', [])}")
        add("foundation reports readiness", bool(summary.get("early_opportunity_foundation_ready")), f"status={summary.get('status')}")

    critical = [c for c in checks if not c["passed"] and c["severity"] == "CRITICAL"]
    certified = not critical
    result = {
        "block_name": "Collector V1 Early Opportunity Foundation Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks if c["passed"]),
        "critical_failures": critical,
        "early_opportunity_foundation_certified": certified,
        "short_history_model_selection_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Build full endpoint-route tournament with early-opportunity candidates" if certified else "Resolve early-opportunity foundation failures",
        "status": "PASS_COLLECTOR_V1_EARLY_OPPORTUNITY_FOUNDATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_EARLY_OPPORTUNITY_FOUNDATION_CERTIFICATION",
    }
    BASE.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(checks).to_csv(CHECKS, index=False)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if args.strict and not certified else 0


if __name__ == "__main__":
    raise SystemExit(main())
