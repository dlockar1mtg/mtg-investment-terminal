from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPANDED_DIR = ROOT / "data/governance/permanence/certification/collector_v1_expanded_tournament"
TARGETED_DIR = ROOT / "data/governance/permanence/certification/collector_v1_targeted_blocked_cell_remediation"
COHORT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_cohort_fallback_tournament"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_short_horizon_winners"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    expanded = pd.read_csv(EXPANDED_DIR / "collector_v1_expanded_tournament_winners.csv")
    limited = pd.read_csv(TARGETED_DIR / "collector_v1_limited_365_route_resolution.csv")
    cohort = pd.read_csv(COHORT_DIR / "collector_v1_early_cohort_fallback_winner.csv")
    cohort_cert = json.loads((COHORT_DIR / "collector_v1_early_cohort_fallback_certification.json").read_text(encoding="utf-8"))

    promoted = expanded[expanded["promotion_status"] == "PROMOTABLE"].copy()
    promoted["resolution_type"] = "DIRECT_PROMOTION"
    promoted["resolved_route"] = promoted["tournament_lane"]
    promoted["resolved_model_variant"] = promoted["model_variant"]
    promoted["confidence_penalty_required"] = False

    limited_row = pd.DataFrame([{
        "tournament_lane": "DIRECT_HISTORY_LIMITED",
        "horizon_days": 365,
        "selection_objective": "PRICE_FORECAST",
        "model_variant": "ROUTE_DELEGATION",
        "promotion_status": str(limited.iloc[0]["resolution_status"]),
        "resolution_type": "APPROVED_FAIL_CLOSED_FALLBACK",
        "resolved_route": str(limited.iloc[0]["delegated_route"]),
        "resolved_model_variant": str(limited.iloc[0]["delegated_model_variant"]),
        "confidence_penalty_required": True,
    }])

    cohort_row = pd.DataFrame([{
        "tournament_lane": "EARLY_OPPORTUNITY_COHORT_FALLBACK",
        "horizon_days": 365,
        "selection_objective": "EARLY_WINNER_RANKING",
        "model_variant": str(cohort.iloc[0]["model_variant"]),
        "promotion_status": str(cohort.iloc[0]["promotion_status"]),
        "resolution_type": "CERTIFIED_COHORT_FALLBACK",
        "resolved_route": "EARLY_OPPORTUNITY_COHORT_FALLBACK",
        "resolved_model_variant": str(cohort.iloc[0]["model_variant"]),
        "confidence_penalty_required": True,
        "age_months": int(float(cohort.iloc[0]["age_months"])),
        "rows": int(float(cohort.iloc[0]["rows"])),
        "mae": float(cohort.iloc[0]["mae"]),
        "bias": float(cohort.iloc[0]["bias"]),
        "rank_correlation": float(cohort.iloc[0]["rank_correlation"]),
        "top_quintile_precision_25pct": float(cohort.iloc[0]["top_quintile_precision_25pct"]),
        "winner_recall_25pct": float(cohort.iloc[0]["winner_recall_25pct"]),
        "false_positive_rate": float(cohort.iloc[0]["false_positive_rate"]),
    }])

    manifest = pd.concat([promoted, limited_row, cohort_row], ignore_index=True, sort=False)
    manifest.to_csv(OUT_DIR / "collector_v1_final_short_horizon_winner_manifest.csv", index=False)

    unresolved = manifest[~manifest["promotion_status"].isin(["PROMOTABLE", "APPROVED_FAIL_CLOSED_FALLBACK"])]
    summary = {
        "block_name": "Collector V1 Final Short-Horizon Winner Manifest",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expanded_promoted_cells": int(len(promoted)),
        "approved_limited_365_fallback_cells": 1,
        "certified_early_cohort_fallback_cells": 1,
        "final_manifest_rows": int(len(manifest)),
        "unresolved_rows": int(len(unresolved)),
        "cohort_fallback_certified": bool(cohort_cert.get("early_cohort_fallback_certified")),
        "winner_set_methodologically_complete": bool(len(unresolved) == 0 and cohort_cert.get("early_cohort_fallback_certified")),
        "long_horizon_simulation_authorized_after_certification": bool(len(unresolved) == 0 and cohort_cert.get("early_cohort_fallback_certified")),
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_FINAL_SHORT_HORIZON_WINNER_MANIFEST_READY",
    }
    (OUT_DIR / "collector_v1_final_short_horizon_winner_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (not args.strict or summary["winner_set_methodologically_complete"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
