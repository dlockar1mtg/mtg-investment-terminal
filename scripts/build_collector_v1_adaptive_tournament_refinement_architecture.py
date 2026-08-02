from __future__ import annotations

import csv
import json
from itertools import product
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_adaptive_tournament_refinement_contract_v1.json"
ROUND1 = ROOT / "data/governance/permanence/certification/collector_v1_horizon_specific_tournament_execution"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_adaptive_tournament_refinement_architecture"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    summary_path = ROUND1 / "collector_horizon_specific_tournament_execution_summary.json"
    winners_path = ROUND1 / "collector_horizon_route_winners.csv"
    scores_path = ROUND1 / "collector_model_tournament_scores.csv"
    failures: list[str] = []

    if not summary_path.is_file() or not winners_path.is_file() or not scores_path.is_file():
        raise SystemExit("MISSING_FIRST_ROUND_ARTIFACTS")

    first_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    winners = read_csv(winners_path)
    scores = read_csv(scores_path)

    if first_summary.get("status") != contract["required_first_round_status"]:
        failures.append("FIRST_ROUND_NOT_CERTIFIED")
    if len(winners) != 18:
        failures.append("FIRST_ROUND_DECISION_COUNT_MISMATCH")

    feature_sets = [
        "PRICE_ONLY",
        "PRICE_RETURN",
        "PRICE_RETURN_VOLATILITY",
        "PRICE_RETURN_DRAWDOWN",
        "PRICE_RETURN_LIFECYCLE",
        "FULL_HISTORICAL_SAFE",
    ]
    lookbacks = [3, 6, 9, 12, 18, 24]
    recency_weights = [0.0, 0.25, 0.5, 0.75]
    dampings = [0.25, 0.5, 0.75, 1.0]
    shrinkages = [0.0, 0.25, 0.5, 0.75]

    group_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    for decision in winners:
        horizon = int(decision["horizon_days"])
        route = decision["route"]
        status = decision["selection_status"]
        eligible = status == "WINNER_SELECTED"
        group_id = f"REFINE-{horizon}-{route}"
        group_rows.append({
            "refinement_group_id": group_id,
            "horizon_label": decision["horizon_label"],
            "horizon_days": horizon,
            "route": route,
            "round_1_winner": decision.get("winner_model", ""),
            "round_1_status": status,
            "refinement_eligible": eligible,
            "nested_rolling_origin_required": True,
            "product_group_holdout_required": True,
            "independent_champion_fold_required": True,
            "production_promotion_authorized": False,
        })
        if not eligible:
            continue
        model_families = [
            "ROBUST_LOG_TREND",
            "DAMPED_LOG_TREND",
            "EXPONENTIAL_SMOOTHING",
            "SHRUNK_TREND_ENSEMBLE",
        ] if route != "COMPARABLE_PRODUCT_ADJUSTED" else [
            "COMPARABLE_MEDIAN_GROWTH",
            "COMPARABLE_WEIGHTED_GROWTH",
            "COMPARABLE_LIFECYCLE_MATCHED",
            "COMPARABLE_SHRUNK_ENSEMBLE",
        ]
        combos = product(model_families, feature_sets, lookbacks, recency_weights, dampings, shrinkages)
        limit = contract["maximum_refinement_candidates_per_eligible_group"]
        for rank, combo in enumerate(combos, start=1):
            if rank > limit:
                break
            model, features, lookback, recency, damping, shrinkage = combo
            candidate_rows.append({
                "refinement_group_id": group_id,
                "candidate_id": f"{group_id}-C{rank:03d}",
                "model_family": model,
                "feature_subset": features,
                "lookback_months": lookback,
                "recency_weight": recency,
                "trend_damping": damping,
                "shrinkage_strength": shrinkage,
                "uses_current_only_feature": False,
                "discovery_fold_role": "INNER_DISCOVERY",
                "champion_fold_role": "OUTER_UNTOUCHED_CHALLENGE",
                "multiple_testing_penalty_required": True,
                "round_1_champion_challenge_required": True,
            })

    eligible_groups = sum(bool(r["refinement_eligible"]) for r in group_rows)
    candidate_counts: dict[str, int] = {}
    for row in candidate_rows:
        candidate_counts[row["refinement_group_id"]] = candidate_counts.get(row["refinement_group_id"], 0) + 1
    for group in group_rows:
        if group["refinement_eligible"] and candidate_counts.get(group["refinement_group_id"], 0) < contract["minimum_refinement_candidates_per_eligible_group"]:
            failures.append("INSUFFICIENT_REFINEMENT_CANDIDATES:" + group["refinement_group_id"])

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_refinement_group_registry.csv", group_rows)
    write_csv(OUTPUT / "collector_refinement_candidate_registry.csv", candidate_rows)
    write_csv(OUTPUT / "collector_round1_metric_discovery_registry.csv", scores)

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE"
    summary = {
        "block_name": contract["contract_name"],
        "block_version": contract["contract_version"],
        "route_horizon_groups": len(group_rows),
        "refinement_eligible_groups": eligible_groups,
        "governed_no_winner_groups_preserved": len(group_rows) - eligible_groups,
        "refinement_candidate_rows": len(candidate_rows),
        "minimum_candidates_per_eligible_group": contract["minimum_refinement_candidates_per_eligible_group"],
        "maximum_candidates_per_eligible_group": contract["maximum_refinement_candidates_per_eligible_group"],
        "nested_rolling_origin_required": True,
        "discovery_and_champion_folds_separate": True,
        "product_group_holdout_required": True,
        "multiple_testing_penalty_required": True,
        "round_1_champion_challenge_required": True,
        "current_only_features_prohibited": True,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_adaptive_tournament_refinement_architecture_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
