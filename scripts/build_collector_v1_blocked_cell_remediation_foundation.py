from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPANDED_DIR = ROOT / "data/governance/permanence/certification/collector_v1_expanded_tournament"
EARLY_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_foundation"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_blocked_cell_remediation"


def first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(f"None of the governed paths exist: {[str(p) for p in paths]}")


def normalize_id(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.extract(r"(\d+)$", expand=False).fillna(series.astype(str).str.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    winners_path = first_existing([EXPANDED_DIR / "collector_v1_expanded_tournament_winners.csv"])
    cells_path = first_existing([EXPANDED_DIR / "collector_v1_expanded_tournament_cells.csv"])
    early_predictions_path = first_existing([EARLY_DIR / "collector_v1_early_opportunity_predictions.csv"])
    first_year_path = first_existing([EARLY_DIR / "collector_v1_first_year_outcomes.csv"])
    peer_curves_path = first_existing([EARLY_DIR / "collector_v1_peer_maturity_curves.csv"])

    winners = pd.read_csv(winners_path)
    cells = pd.read_csv(cells_path)
    early = pd.read_csv(early_predictions_path)
    outcomes = pd.read_csv(first_year_path)
    peers = pd.read_csv(peer_curves_path)

    id_candidates = ["tcgplayer_product_id", "product_id"]
    id_col = next((c for c in id_candidates if c in early.columns), None)
    outcome_id_col = next((c for c in id_candidates if c in outcomes.columns), None)
    peer_target_col = next((c for c in ["target_product_id", "tcgplayer_product_id", "product_id"] if c in peers.columns), None)
    if not id_col or not outcome_id_col:
        raise ValueError(f"Product identity columns unresolved. early={list(early.columns)} outcomes={list(outcomes.columns)}")

    early[id_col] = normalize_id(early[id_col])
    outcomes[outcome_id_col] = normalize_id(outcomes[outcome_id_col])
    realized_ids = set(outcomes[outcome_id_col].dropna().astype(str))
    evaluated_ids = set(early[id_col].dropna().astype(str))

    if peer_target_col:
        peers[peer_target_col] = normalize_id(peers[peer_target_col])
        peer_target_ids = set(peers[peer_target_col].dropna().astype(str))
    else:
        peer_target_ids = set()

    coverage_rows: list[dict] = []
    for product_id in sorted(realized_ids):
        in_early = product_id in evaluated_ids
        in_peer = product_id in peer_target_ids if peer_target_ids else False
        if in_early:
            reason = "INCLUDED_IN_EARLY_TOURNAMENT"
        elif peer_target_ids and not in_peer:
            reason = "NO_PEER_MATURITY_CURVE_TARGET"
        else:
            reason = "NO_USABLE_EARLY_PREDICTION_ROW"
        coverage_rows.append({
            "tcgplayer_product_id": product_id,
            "realized_first_year_outcome": True,
            "included_in_early_tournament": in_early,
            "has_peer_maturity_curve": in_peer,
            "exclusion_reason": reason,
        })
    coverage = pd.DataFrame(coverage_rows)

    blocked = winners[winners["promotion_status"] != "PROMOTABLE"].copy()
    remediation_rows: list[dict] = []
    for _, row in blocked.iterrows():
        lane = str(row.get("tournament_lane", ""))
        horizon = int(float(row.get("horizon_days", 0)))
        if lane == "DIRECT_HISTORY_LIMITED" and horizon == 365:
            remediation_rows.extend([
                {
                    "blocked_cell": "DIRECT_HISTORY_LIMITED_X_365",
                    "candidate_family": "COMPARABLE_ASSISTED_LIMITED_HISTORY",
                    "required_inputs": "limited-history price path; governed peers; peer 365-day outcomes",
                    "promotion_test": "rows>=30; bias gate; interval coverage; lower MAE than blocked baseline",
                    "status": "AUTHORIZED_TO_BUILD",
                },
                {
                    "blocked_cell": "DIRECT_HISTORY_LIMITED_X_365",
                    "candidate_family": "POOLED_ROUTE_SHRINKAGE",
                    "required_inputs": "limited-history route residuals; calibrated-route prior",
                    "promotion_test": "leave-one-product-out; downside error; interval coverage",
                    "status": "AUTHORIZED_TO_BUILD",
                },
                {
                    "blocked_cell": "DIRECT_HISTORY_LIMITED_X_365",
                    "candidate_family": "CAPPED_180_TO_365_ENSEMBLE",
                    "required_inputs": "promoted 180-day winner; conservative compounding cap",
                    "promotion_test": "no leakage; lower error than direct 365 baseline; conservative downside",
                    "status": "AUTHORIZED_TO_BUILD",
                },
            ])
        elif lane == "EARLY_OPPORTUNITY_COMPARABLE_TRANSFER":
            remediation_rows.extend([
                {
                    "blocked_cell": "EARLY_OPPORTUNITY_X_365",
                    "candidate_family": "COVERAGE_EXPANDED_EQUAL_PEER",
                    "required_inputs": "all realized products with >=3 governed peers",
                    "promotion_test": "independent products>=30; precision>=0.60; recall>=0.50; FPR<=0.40",
                    "status": "AUTHORIZED_TO_BUILD",
                },
                {
                    "blocked_cell": "EARLY_OPPORTUNITY_X_365",
                    "candidate_family": "SIMILARITY_WEIGHTED_PEER_TRANSFER",
                    "required_inputs": "certified comparable pair score",
                    "promotion_test": "product/cohort holdout improvement over equal-peer",
                    "status": "WAITING_ON_REGISTERED_PAIR_SCORE",
                },
                {
                    "blocked_cell": "EARLY_OPPORTUNITY_X_365",
                    "candidate_family": "AGE_COHORT_RANKING_ENSEMBLE",
                    "required_inputs": "peer return; early momentum; release cohort normalization",
                    "promotion_test": "ranking objective and price objective selected separately",
                    "status": "AUTHORIZED_TO_BUILD",
                },
            ])
    remediation = pd.DataFrame(remediation_rows)

    gap_rows = [
        {
            "gap": "comparable_similarity_score",
            "status": "NOT_REGISTERED_IN_ACTIVE_AUTHORITY",
            "required_action": "Register a certified pair-score artifact and map target/peer/score columns.",
            "blocks_winner_certification": True,
        },
        {
            "gap": "early_tournament_product_coverage",
            "status": f"{len(evaluated_ids)}_OF_{len(realized_ids)}_REALIZED_PRODUCTS",
            "required_action": "Use coverage report to recover valid excluded products without lowering peer or leakage standards.",
            "blocks_winner_certification": True,
        },
        {
            "gap": "limited_history_365_candidate_quality",
            "status": "NO_PROMOTABLE_CANDIDATE",
            "required_action": "Run comparable-assisted, pooled-shrinkage, and capped 180-to-365 candidates.",
            "blocks_winner_certification": True,
        },
    ]
    gaps = pd.DataFrame(gap_rows)

    coverage.to_csv(OUT_DIR / "collector_v1_early_coverage_reconciliation.csv", index=False)
    blocked.to_csv(OUT_DIR / "collector_v1_blocked_winner_cells.csv", index=False)
    remediation.to_csv(OUT_DIR / "collector_v1_blocked_cell_candidate_plan.csv", index=False)
    gaps.to_csv(OUT_DIR / "collector_v1_blocked_cell_gap_register.csv", index=False)

    blockers: list[str] = []
    expected_blocked = {
        ("DIRECT_HISTORY_LIMITED", 365),
        ("EARLY_OPPORTUNITY_COMPARABLE_TRANSFER", 365),
    }
    observed_blocked = set((str(r["tournament_lane"]), int(float(r["horizon_days"]))) for _, r in blocked.iterrows())
    if observed_blocked != expected_blocked:
        blockers.append(f"Unexpected blocked cells: observed={sorted(observed_blocked)} expected={sorted(expected_blocked)}")
    if len(realized_ids) < 30:
        blockers.append("Fewer than 30 realized first-year products are available.")
    if remediation.empty:
        blockers.append("No remediation candidates were produced.")

    summary = {
        "block_name": "Collector V1 Blocked Cell Remediation Foundation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expanded_winner_cells": int(len(winners)),
        "promoted_winner_cells": int((winners["promotion_status"] == "PROMOTABLE").sum()),
        "blocked_winner_cells": int(len(blocked)),
        "realized_first_year_products": int(len(realized_ids)),
        "early_tournament_products": int(len(evaluated_ids)),
        "early_coverage_rate": float(len(evaluated_ids) / len(realized_ids)) if realized_ids else 0.0,
        "coverage_exclusion_rows": int((~coverage["included_in_early_tournament"]).sum()),
        "authorized_remediation_candidates": int((remediation["status"] == "AUTHORIZED_TO_BUILD").sum()) if not remediation.empty else 0,
        "pair_score_registered": False,
        "blockers": blockers,
        "remediation_foundation_ready": not blockers,
        "winner_promotion_authorized": False,
        "long_horizon_simulation_authorized": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_BLOCKED_CELL_REMEDIATION_FOUNDATION_READY" if not blockers else "BLOCKED_COLLECTOR_V1_BLOCKED_CELL_REMEDIATION_FOUNDATION",
    }
    (OUT_DIR / "collector_v1_blocked_cell_remediation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
