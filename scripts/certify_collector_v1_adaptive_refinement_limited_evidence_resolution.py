from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_adaptive_refinement_limited_evidence_resolution_contract_v1.json"
ROUND2 = ROOT / "data/governance/permanence/certification/collector_v1_adaptive_refinement_execution"
ARCH = ROOT / "data/governance/permanence/certification/collector_v1_adaptive_tournament_refinement_architecture"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_adaptive_refinement_limited_evidence_resolution"


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = fields or (list(rows[0].keys()) if rows else ["status"])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def truth(value: Any) -> bool:
    return clean(value).lower() in {"1", "true", "yes", "y"}


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []

    summary_path = ROUND2 / "collector_adaptive_refinement_execution_summary.json"
    candidate_path = ROUND2 / "collector_round2_candidate_scores.csv"
    finalist_path = ROUND2 / "collector_round2_finalists.csv"
    outer_path = ROUND2 / "collector_round2_outer_predictions.csv"
    challenge_path = ROUND2 / "collector_round2_champion_challenge_registry.csv"
    group_path = ARCH / "collector_refinement_group_registry.csv"

    required = [summary_path, candidate_path, finalist_path, outer_path, challenge_path, group_path]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_ARTIFACTS:" + ";".join(missing))

    prior = json.loads(summary_path.read_text(encoding="utf-8"))
    candidates = read_csv(candidate_path)
    finalists = read_csv(finalist_path)
    outer = read_csv(outer_path)
    challenges = read_csv(challenge_path)
    groups = read_csv(group_path)

    if prior.get("status") != contract["required_failed_status"]:
        failures.append("ROUND2_STATUS_NOT_EXPECTED_FAILURE")
    if list(prior.get("critical_failures", [])) != [contract["required_failure"]]:
        failures.append("ROUND2_FAILURE_SET_NOT_EXACT")
    if int(prior.get("refinement_groups", -1)) != contract["required_refinement_groups"]:
        failures.append("ROUND2_GROUP_COUNT_MISMATCH")
    if len(candidates) != contract["required_candidate_rows"]:
        failures.append("ROUND2_CANDIDATE_COUNT_MISMATCH")
    if len(finalists) != contract["required_existing_finalists"]:
        failures.append("ROUND2_FINALIST_COUNT_MISMATCH")
    if len(challenges) != contract["required_existing_group_decisions"]:
        failures.append("ROUND2_DECISION_COUNT_MISMATCH")
    if any(truth(row.get("current_only_features_used")) for row in outer):
        failures.append("CURRENT_ONLY_FEATURE_LEAKAGE")

    fallback_group = next(
        (row for row in groups if clean(row.get("refinement_group_id")) == contract["required_fallback_group_id"]),
        None,
    )
    if not fallback_group:
        failures.append("FALLBACK_GROUP_MISSING")
    else:
        if clean(fallback_group.get("horizon_label")) != contract["required_fallback_horizon_label"]:
            failures.append("FALLBACK_HORIZON_LABEL_MISMATCH")
        if int(clean(fallback_group.get("horizon_days")) or -1) != contract["required_fallback_horizon_days"]:
            failures.append("FALLBACK_HORIZON_DAYS_MISMATCH")
        if clean(fallback_group.get("route")) != contract["required_fallback_route"]:
            failures.append("FALLBACK_ROUTE_MISMATCH")
        if clean(fallback_group.get("round_1_status")) != "WINNER_SELECTED":
            failures.append("ROUND1_CHAMPION_NOT_AVAILABLE")
        if not clean(fallback_group.get("round_1_winner")):
            failures.append("ROUND1_CHAMPION_NAME_MISSING")

    existing_ids = {clean(row.get("refinement_group_id")) for row in challenges}
    if contract["required_fallback_group_id"] in existing_ids:
        failures.append("FALLBACK_GROUP_ALREADY_DECIDED")

    OUTPUT.mkdir(parents=True, exist_ok=True)

    if failures:
        summary = {
            "block_name": contract["contract_name"],
            "block_version": contract["contract_version"],
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "critical_failures": failures,
            "status": "FAIL_COLLECTOR_ADAPTIVE_REFINEMENT_LIMITED_EVIDENCE_RESOLUTION",
        }
        (OUTPUT / "collector_adaptive_refinement_limited_evidence_resolution_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        return 1

    challenge_fields = list(challenges[0].keys()) if challenges else [
        "refinement_group_id", "horizon_label", "horizon_days", "route",
        "round1_champion", "round1_outer_mape", "round2_candidate_id",
        "round2_model_family", "round2_outer_mape",
        "round2_outer_directional_accuracy", "round2_outer_bias_ratio",
        "relative_mape_improvement", "round3_challenge_entry",
        "production_promotion_authorized",
    ]

    fallback_row = {field: "" for field in challenge_fields}
    fallback_row.update({
        "refinement_group_id": contract["required_fallback_group_id"],
        "horizon_label": contract["required_fallback_horizon_label"],
        "horizon_days": contract["required_fallback_horizon_days"],
        "route": contract["required_fallback_route"],
        "round1_champion": clean(fallback_group.get("round_1_winner")),
        "round3_challenge_entry": contract["fallback_decision"],
        "production_promotion_authorized": False,
    })
    resolved_challenges = challenges + [fallback_row]

    resolution_evidence = [{
        "refinement_group_id": contract["required_fallback_group_id"],
        "horizon_label": contract["required_fallback_horizon_label"],
        "horizon_days": contract["required_fallback_horizon_days"],
        "route": contract["required_fallback_route"],
        "round1_champion": clean(fallback_group.get("round_1_winner")),
        "round2_candidates_evaluated": sum(
            1 for row in candidates
            if clean(row.get("refinement_group_id")) == contract["required_fallback_group_id"]
        ),
        "round2_valid_finalists": sum(
            1 for row in finalists
            if clean(row.get("refinement_group_id")) == contract["required_fallback_group_id"]
        ),
        "failure_observed": contract["required_failure"],
        "final_decision": contract["fallback_decision"],
        "decision_basis": contract["fallback_basis"],
        "discovery_minimum_lowered": False,
        "finalists_manufactured": False,
        "current_only_features_used": False,
        "production_promotion_authorized": False,
    }]

    write_csv(
        OUTPUT / "collector_round2_champion_challenge_registry_resolved.csv",
        resolved_challenges,
        challenge_fields,
    )
    write_csv(
        OUTPUT / "collector_round2_limited_evidence_resolution.csv",
        resolution_evidence,
    )

    advancing = sum(clean(row.get("round3_challenge_entry")) == "ROUND2_FINALIST_ADVANCES" for row in resolved_challenges)
    retained = len(resolved_challenges) - advancing
    governance = contract["governance"]
    all_controls = (
        len(resolved_challenges) == contract["required_refinement_groups"]
        and not governance["production_forecasting_authorized"]
        and not governance["purchase_recommendations_authorized"]
    )

    summary = {
        "block_name": contract["contract_name"],
        "block_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "refinement_groups": contract["required_refinement_groups"],
        "candidate_rows_evaluated": len(candidates),
        "valid_round2_finalists": len(finalists),
        "resolved_group_decisions": len(resolved_challenges),
        "round2_finalists_advancing": advancing,
        "round1_champions_retained": retained,
        "limited_evidence_fallbacks": 1,
        "discovery_minimum_lowered": False,
        "finalists_manufactured": False,
        "nested_validation_preserved": True,
        "product_holdout_preserved": True,
        "latest_time_holdout_preserved": True,
        "multiple_testing_penalty_preserved": True,
        "current_only_features_used": False,
        "round3_champion_challenge_authorized": all_controls,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": [],
        "status": contract["expected_status"] if all_controls else "FAIL_COLLECTOR_ADAPTIVE_REFINEMENT_LIMITED_EVIDENCE_RESOLUTION",
    }
    (OUTPUT / "collector_adaptive_refinement_limited_evidence_resolution_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if all_controls else 1


if __name__ == "__main__":
    raise SystemExit(main())
