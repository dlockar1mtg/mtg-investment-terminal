from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_round3_final_champion_challenge_contract_v1.json"
ROUND1 = ROOT / "data/governance/permanence/certification/collector_v1_horizon_specific_tournament_execution"
ROUND2 = ROOT / "data/governance/permanence/certification/collector_v1_adaptive_refinement_execution"
RESOLUTION = ROOT / "data/governance/permanence/certification/collector_v1_adaptive_refinement_limited_evidence_resolution"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_round3_final_champion_challenge"


def clean(value: Any) -> str:
    return str(value or "").strip()


def num(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return default
    try:
        result = float(text)
    except ValueError:
        return default
    return result if math.isfinite(result) else default


def truth(value: Any) -> bool:
    return clean(value).lower() == "true"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def metric(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {
            "rows": 0,
            "mape": 0.0,
            "mae": 0.0,
            "directional_accuracy": 0.0,
            "bias_ratio": 0.0,
            "single_product_error_share": 1.0,
            "worst_product_mape_multiple": 999.0,
        }
    apes = [num(r.get("absolute_percentage_error")) for r in rows]
    aes = [num(r.get("absolute_error")) for r in rows]
    signed = [num(r.get("signed_error")) for r in rows]
    actual = [max(num(r.get("actual_price"), 0.01), 0.01) for r in rows]
    directions = [truth(r.get("direction_correct")) for r in rows]
    product_error: dict[str, float] = defaultdict(float)
    product_apes: dict[str, list[float]] = defaultdict(list)
    for row, ae, ape in zip(rows, aes, apes):
        cid = clean(row.get("canonical_product_id"))
        product_error[cid] += ae
        product_apes[cid].append(ape)
    total_error = sum(aes)
    concentration = max(product_error.values(), default=0.0) / max(total_error, 1e-9)
    overall_mape = median(apes)
    per_product_mape = [median(values) for values in product_apes.values() if values]
    worst_multiple = max(per_product_mape, default=0.0) / max(overall_mape, 1e-9)
    return {
        "rows": len(rows),
        "mape": overall_mape,
        "mae": median(aes),
        "directional_accuracy": sum(directions) / len(directions),
        "bias_ratio": abs(sum(signed)) / max(sum(actual), 1e-9),
        "single_product_error_share": concentration,
        "worst_product_mape_multiple": worst_multiple,
    }


def latest_subset(rows: list[dict[str, Any]], fraction: float = 0.25) -> list[dict[str, Any]]:
    if not rows:
        return []
    ordered_dates = sorted({clean(r.get("origin_date")) for r in rows if clean(r.get("origin_date"))})
    if not ordered_dates:
        return []
    start = max(0, int(len(ordered_dates) * (1.0 - fraction)))
    keep = set(ordered_dates[start:])
    return [r for r in rows if clean(r.get("origin_date")) in keep]


def candidate_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return clean(row.get("horizon_label")), clean(row.get("route")), clean(row.get("model_name"))


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []

    resolution_summary = json.loads((RESOLUTION / "collector_adaptive_refinement_limited_evidence_resolution_summary.json").read_text(encoding="utf-8"))
    round1_summary = json.loads((ROUND1 / "collector_horizon_specific_tournament_execution_summary.json").read_text(encoding="utf-8"))
    if resolution_summary.get("status") != contract["required_round2_resolution_status"]:
        failures.append("ROUND2_RESOLUTION_NOT_CERTIFIED")
    if round1_summary.get("status") != contract["required_round1_status"]:
        failures.append("ROUND1_NOT_CERTIFIED")

    decisions = read_csv(RESOLUTION / "collector_round2_champion_challenge_registry_resolved.csv")
    round1_predictions = read_csv(ROUND1 / "collector_rolling_origin_predictions.csv")
    round2_predictions = read_csv(ROUND2 / "collector_round2_outer_predictions.csv")
    round1_winners = read_csv(ROUND1 / "collector_horizon_route_winners.csv")

    if len(decisions) != contract["required_group_decisions"]:
        failures.append("ROUND3_ENTRY_COUNT_MISMATCH")

    r1_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in round1_predictions:
        r1_by_key[candidate_key(row)].append(row)
    r2_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in round2_predictions:
        r2_by_candidate[clean(row.get("candidate_id"))].append(row)

    winner_lookup = {(clean(r.get("horizon_label")), clean(r.get("route"))): r for r in round1_winners}
    evidence_rows: list[dict[str, Any]] = []
    final_rows: list[dict[str, Any]] = []

    for decision in decisions:
        horizon = clean(decision.get("horizon_label"))
        route = clean(decision.get("route"))
        r1_model = clean(decision.get("round1_champion"))
        r2_candidate = clean(decision.get("round2_candidate_id"))
        r2_model = clean(decision.get("round2_model_family"))
        entry = clean(decision.get("round3_challenge_entry"))
        baseline_model = contract["baseline_models"][route]

        r1_rows = r1_by_key.get((horizon, route, r1_model), [])
        baseline_rows = r1_by_key.get((horizon, route, baseline_model), [])
        r2_rows = r2_by_candidate.get(r2_candidate, []) if r2_candidate else []

        chosen_source = "ROUND2" if entry == "ROUND2_FINALIST_ADVANCES" and r2_rows else "ROUND1"
        chosen_model = r2_model if chosen_source == "ROUND2" else r1_model
        chosen_candidate = r2_candidate if chosen_source == "ROUND2" else ""
        chosen_rows = r2_rows if chosen_source == "ROUND2" else r1_rows

        partitions = {
            "OUTER_ALL": chosen_rows,
            "LATEST_TIME_STRESS": latest_subset(chosen_rows),
            "PRODUCT_CONCENTRATION_STRESS": chosen_rows,
        }
        chosen_metrics = metric(chosen_rows)
        baseline_metrics = metric(baseline_rows)
        r1_metrics = metric(r1_rows)

        for partition, rows in partitions.items():
            m = metric(rows)
            evidence_rows.append({
                "horizon_label": horizon,
                "route": route,
                "candidate_source": chosen_source,
                "candidate_model": chosen_model,
                "candidate_id": chosen_candidate,
                "challenge_partition": partition,
                "challenge_rows": m["rows"],
                "mape": round(m["mape"], 6),
                "mae": round(m["mae"], 6),
                "directional_accuracy": round(m["directional_accuracy"], 6),
                "bias_ratio": round(m["bias_ratio"], 6),
                "single_product_error_share": round(m["single_product_error_share"], 6),
                "worst_product_mape_multiple": round(m["worst_product_mape_multiple"], 6),
                "current_only_features_used": False,
            })

        baseline_improvement = (baseline_metrics["mape"] - chosen_metrics["mape"]) / max(baseline_metrics["mape"], 1e-9)
        round1_improvement = (r1_metrics["mape"] - chosen_metrics["mape"]) / max(r1_metrics["mape"], 1e-9)
        sufficient = chosen_metrics["rows"] >= contract["minimum_challenge_rows"]
        directional_ok = chosen_metrics["directional_accuracy"] >= contract["minimum_directional_accuracy"]
        bias_ok = chosen_metrics["bias_ratio"] <= contract["maximum_absolute_bias_ratio"]
        concentration_ok = chosen_metrics["single_product_error_share"] <= contract["maximum_single_product_error_share"]
        worst_product_ok = chosen_metrics["worst_product_mape_multiple"] <= contract["maximum_worst_product_mape_multiple"]
        baseline_ok = chosen_model == baseline_model or baseline_improvement >= contract["minimum_relative_mape_improvement_over_baseline"]
        round2_ok = chosen_source != "ROUND2" or round1_improvement >= contract["minimum_round2_improvement_for_round2_promotion"]

        all_pass = all([sufficient, directional_ok, bias_ok, concentration_ok, worst_product_ok, baseline_ok, round2_ok])
        if all_pass and chosen_source == "ROUND2":
            final_decision = "PROMOTE_ROUND2_CHAMPION"
        elif all_pass and chosen_model == baseline_model:
            final_decision = "RETAIN_NAIVE_BASELINE"
        elif all_pass:
            final_decision = "PROMOTE_ROUND1_CHAMPION"
        else:
            final_decision = "GOVERNED_NO_PRODUCTION_CHAMPION"

        final_rows.append({
            "horizon_label": horizon,
            "horizon_days": clean(decision.get("horizon_days")),
            "route": route,
            "round1_champion": r1_model,
            "round2_candidate_id": r2_candidate,
            "round2_model_family": r2_model,
            "round3_candidate_source": chosen_source,
            "round3_candidate_model": chosen_model,
            "round3_candidate_id": chosen_candidate,
            "challenge_rows": chosen_metrics["rows"],
            "candidate_mape": round(chosen_metrics["mape"], 6),
            "baseline_model": baseline_model,
            "baseline_mape": round(baseline_metrics["mape"], 6),
            "relative_mape_improvement_over_baseline": round(baseline_improvement, 6),
            "relative_mape_improvement_over_round1": round(round1_improvement, 6),
            "directional_accuracy": round(chosen_metrics["directional_accuracy"], 6),
            "bias_ratio": round(chosen_metrics["bias_ratio"], 6),
            "single_product_error_share": round(chosen_metrics["single_product_error_share"], 6),
            "worst_product_mape_multiple": round(chosen_metrics["worst_product_mape_multiple"], 6),
            "evidence_sufficient": sufficient,
            "directional_gate_passed": directional_ok,
            "bias_gate_passed": bias_ok,
            "concentration_gate_passed": concentration_ok,
            "worst_product_gate_passed": worst_product_ok,
            "baseline_gate_passed": baseline_ok,
            "round2_incremental_gate_passed": round2_ok,
            "final_decision": final_decision,
            "production_model_certified": final_decision != "GOVERNED_NO_PRODUCTION_CHAMPION",
            "current_only_features_used": False,
            "purchase_recommendation_authorized": False,
        })

    if len(final_rows) != contract["required_group_decisions"]:
        failures.append("FINAL_DECISION_COUNT_MISMATCH")
    if any(r["current_only_features_used"] for r in final_rows):
        failures.append("CURRENT_ONLY_FEATURE_LEAKAGE")
    if any(r["final_decision"] not in contract["allowed_final_decisions"] for r in final_rows):
        failures.append("INVALID_FINAL_DECISION")

    preserved = [
        r for r in round1_winners
        if clean(r.get("selection_status")) == "GOVERNED_NO_WINNER"
    ]
    if len(preserved) != contract["preserved_governed_no_winner_groups"]:
        failures.append("PRESERVED_NO_WINNER_COUNT_MISMATCH")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_round3_challenge_evidence.csv", evidence_rows)
    write_csv(OUTPUT / "collector_round3_final_champions.csv", final_rows)
    write_csv(OUTPUT / "collector_round3_preserved_no_winner_groups.csv", preserved)

    certified = sum(bool(r["production_model_certified"]) for r in final_rows)
    no_champion = len(final_rows) - certified
    summary = {
        "block_name": contract["contract_name"],
        "block_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "round3_group_decisions": len(final_rows),
        "challenge_evidence_rows": len(evidence_rows),
        "production_champions_certified": certified,
        "governed_no_production_champions": no_champion,
        "preserved_governed_no_winner_groups": len(preserved),
        "round2_champions_promoted": sum(r["final_decision"] == "PROMOTE_ROUND2_CHAMPION" for r in final_rows),
        "round1_champions_promoted": sum(r["final_decision"] == "PROMOTE_ROUND1_CHAMPION" for r in final_rows),
        "naive_baselines_retained": sum(r["final_decision"] == "RETAIN_NAIVE_BASELINE" for r in final_rows),
        "candidate_set_frozen": True,
        "new_feature_tuning_performed": False,
        "current_only_features_used": False,
        "production_forecast_generation_authorized": certified > 0 and not failures,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": contract["expected_status"] if not failures else "FAIL_COLLECTOR_ROUND3_FINAL_CHAMPION_CHALLENGE",
    }
    (OUTPUT / "collector_round3_final_champion_challenge_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
