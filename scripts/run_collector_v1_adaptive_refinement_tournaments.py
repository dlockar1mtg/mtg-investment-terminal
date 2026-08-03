from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_adaptive_refinement_execution_contract_v1.json"
ARCH = ROOT / "data/governance/permanence/certification/collector_v1_adaptive_tournament_refinement_architecture"
ROUND1 = ROOT / "data/governance/permanence/certification/collector_v1_horizon_specific_tournament_execution"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_adaptive_refinement_execution"


def clean(value: Any) -> str:
    return str(value or "").strip()


def num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(clean(value))
    except ValueError:
        return default
    return result if math.isfinite(result) else default


def truth(value: Any) -> bool:
    return clean(value).lower() in {"1", "true", "yes", "y"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = fields or (list(rows[0].keys()) if rows else ["status"])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def stable_bucket(text: str, modulus: int) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulus


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return ordered[lo]
    weight = position - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def candidate_prediction(candidate: dict[str, str], base: dict[str, str], route_center: float) -> float:
    origin_price = max(num(base.get("origin_price"), 0.01), 0.01)
    base_return = num(base.get("predicted_return"))
    age_days = num(base.get("origin_age_days"), 9999)
    observations = num(base.get("training_observations"), 1)
    damping = num(candidate.get("trend_damping"), 1.0)
    shrinkage = num(candidate.get("shrinkage_strength"), 0.0)
    recency = num(candidate.get("recency_weight"), 0.0)
    lookback = max(num(candidate.get("lookback_months"), 12), 1)
    feature_subset = clean(candidate.get("feature_subset"))
    family = clean(candidate.get("model_family"))

    adjusted = base_return * damping
    adjusted = adjusted * (1 - shrinkage) + route_center * shrinkage

    maturity = min(observations / max(lookback, 1), 2.0)
    adjusted *= 1.0 + recency * (maturity - 1.0) * 0.08

    if "LIFECYCLE" in feature_subset:
        if age_days <= 180:
            adjusted *= 1.08
        elif age_days <= 540:
            adjusted *= 1.03
        else:
            adjusted *= 0.98
    if "VOLATILITY" in feature_subset:
        adjusted *= 0.94
    if "DRAWDOWN" in feature_subset and adjusted < 0:
        adjusted *= 0.85
    if feature_subset == "PRICE_ONLY":
        adjusted *= 0.90

    if family.endswith("ENSEMBLE"):
        adjusted = 0.70 * adjusted + 0.30 * route_center
    elif family == "EXPONENTIAL_SMOOTHING":
        adjusted *= 0.88
    elif family == "COMPARABLE_MEDIAN_GROWTH":
        adjusted = 0.75 * adjusted + 0.25 * route_center
    elif family == "COMPARABLE_LIFECYCLE_MATCHED" and age_days <= 540:
        adjusted *= 1.05

    adjusted = max(-0.90, min(adjusted, 4.0))
    return max(0.01, origin_price * (1.0 + adjusted))


def metrics(rows: list[dict[str, Any]], major_threshold: float) -> dict[str, float]:
    if not rows:
        return {
            "row_count": 0,
            "mape": 999.0,
            "mae": 999.0,
            "directional_accuracy": 0.0,
            "bias_ratio": 999.0,
            "major_grower_precision": 0.0,
            "major_grower_recall": 0.0,
            "early_detection_rate": 0.0,
        }
    apes = [float(r["absolute_percentage_error"]) for r in rows]
    aes = [float(r["absolute_error"]) for r in rows]
    signed = [float(r["signed_error"]) for r in rows]
    actuals = [max(float(r["actual_price"]), 0.01) for r in rows]
    directional = [bool(r["direction_correct"]) for r in rows]
    actual_major = [float(r["actual_return"]) >= major_threshold for r in rows]
    signals = [float(r["predicted_return"]) >= major_threshold for r in rows]
    tp = sum(a and s for a, s in zip(actual_major, signals))
    fp = sum((not a) and s for a, s in zip(actual_major, signals))
    fn = sum(a and (not s) for a, s in zip(actual_major, signals))
    early_tp = sum(
        a and s and num(r.get("origin_age_days"), 9999) <= 180
        for a, s, r in zip(actual_major, signals, rows)
    )
    return {
        "row_count": len(rows),
        "mape": median(apes),
        "mae": sum(aes) / len(aes),
        "directional_accuracy": sum(directional) / len(directional),
        "bias_ratio": abs(sum(signed) / len(signed)) / max(sum(actuals) / len(actuals), 0.01),
        "major_grower_precision": tp / max(tp + fp, 1),
        "major_grower_recall": tp / max(tp + fn, 1),
        "early_detection_rate": early_tp / max(sum(actual_major), 1),
    }


def objective(metric: dict[str, float], horizon_days: int, complexity: int, candidate_count: int, contract: dict[str, Any]) -> float:
    if horizon_days == 365:
        weights = contract["365_day_objective_weights"]
        score = (
            weights["mape"] * metric["mape"]
            + weights["directional_accuracy"] * (1 - metric["directional_accuracy"])
            + weights["major_grower_recall"] * (1 - metric["major_grower_recall"])
            + weights["major_grower_precision"] * (1 - metric["major_grower_precision"])
            + weights["early_detection_rate"] * (1 - metric["early_detection_rate"])
        )
    else:
        weights = contract["standard_objective_weights"]
        score = (
            weights["mape"] * metric["mape"]
            + weights["directional_accuracy"] * (1 - metric["directional_accuracy"])
            + weights["bias"] * metric["bias_ratio"]
        )
    score += contract["multiple_testing_penalty"] * math.sqrt(math.log(max(candidate_count, 2)))
    score += contract["complexity_penalty_per_active_component"] * complexity
    return score


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    arch_summary = json.loads((ARCH / "collector_adaptive_tournament_refinement_architecture_summary.json").read_text(encoding="utf-8"))
    round1_summary = json.loads((ROUND1 / "collector_horizon_specific_tournament_execution_summary.json").read_text(encoding="utf-8"))
    failures: list[str] = []

    if arch_summary.get("status") != contract["required_architecture_status"]:
        failures.append("REFINEMENT_ARCHITECTURE_NOT_CERTIFIED")
    if round1_summary.get("status") != contract["required_round1_status"]:
        failures.append("ROUND1_NOT_CERTIFIED")

    candidates = read_csv(ARCH / "collector_refinement_candidate_registry.csv")
    groups = read_csv(ARCH / "collector_refinement_group_registry.csv")
    predictions = read_csv(ROUND1 / "collector_rolling_origin_predictions.csv")
    winners = read_csv(ROUND1 / "collector_horizon_route_winners.csv")

    if len(candidates) != contract["required_candidate_rows"]:
        failures.append("CANDIDATE_COUNT_MISMATCH")
    eligible_groups = [g for g in groups if truth(g.get("refinement_eligible"))]
    if len(eligible_groups) != contract["required_refinement_groups"]:
        failures.append("ELIGIBLE_GROUP_COUNT_MISMATCH")
    if any(truth(c.get("uses_current_only_feature")) for c in candidates):
        failures.append("CURRENT_ONLY_FEATURE_IN_REFINEMENT")

    major_threshold = num(round1_summary.get("major_365_growth_threshold"), 0.50)
    winner_by_group = {
        (clean(w["horizon_label"]), clean(w["route"])): clean(w.get("winner_model"))
        for w in winners
    }
    candidates_by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        candidates_by_group[clean(row["refinement_group_id"])].append(row)

    predictions_by_key: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in predictions:
        key = (clean(row["horizon_label"]), clean(row["route"]), clean(row["model_name"]))
        predictions_by_key[key].append(row)

    score_rows: list[dict[str, Any]] = []
    finalist_rows: list[dict[str, Any]] = []
    champion_rows: list[dict[str, Any]] = []
    finalist_predictions: list[dict[str, Any]] = []

    for group in eligible_groups:
        group_id = clean(group["refinement_group_id"])
        horizon_label = clean(group["horizon_label"])
        horizon_days = int(num(group["horizon_days"]))
        route = clean(group["route"])
        round1_winner = clean(group["round_1_winner"])
        group_candidates = candidates_by_group[group_id]
        model_names = sorted({clean(c["model_family"]) for c in group_candidates})
        base_rows = []
        for model in model_names:
            base_rows.extend(predictions_by_key.get((horizon_label, route, model), []))
        if not base_rows:
            base_rows = predictions_by_key.get((horizon_label, route, round1_winner), [])
        if not base_rows:
            failures.append("NO_BASE_PREDICTIONS:" + group_id)
            continue

        dates = sorted({clean(r["origin_date"]) for r in base_rows})
        cutoff_index = max(0, int(len(dates) * (1 - contract["outer_latest_date_fraction"])) - 1)
        champion_date_cutoff = dates[cutoff_index]

        route_centers: dict[str, float] = {}
        for model in model_names:
            values = [num(r.get("predicted_return")) for r in predictions_by_key.get((horizon_label, route, model), [])]
            route_centers[model] = median(values) if values else 0.0

        for candidate in group_candidates:
            model = clean(candidate["model_family"])
            source = predictions_by_key.get((horizon_label, route, model), [])
            if not source:
                source = predictions_by_key.get((horizon_label, route, round1_winner), [])
            discovery_eval: list[dict[str, Any]] = []
            champion_eval: list[dict[str, Any]] = []
            for base in source:
                cid = clean(base["canonical_product_id"])
                is_product_holdout = stable_bucket(cid, contract["outer_product_holdout_modulus"]) == contract["outer_product_holdout_remainder"]
                is_latest_holdout = clean(base["origin_date"]) >= champion_date_cutoff
                predicted_price = candidate_prediction(candidate, base, route_centers.get(model, 0.0))
                actual_price = max(num(base["actual_price"], 0.01), 0.01)
                origin_price = max(num(base["origin_price"], 0.01), 0.01)
                predicted_return = predicted_price / origin_price - 1
                actual_return = num(base["actual_return"])
                record = {
                    "refinement_group_id": group_id,
                    "candidate_id": clean(candidate["candidate_id"]),
                    "horizon_label": horizon_label,
                    "horizon_days": horizon_days,
                    "route": route,
                    "canonical_product_id": cid,
                    "product_name": clean(base.get("product_name")),
                    "origin_date": clean(base["origin_date"]),
                    "origin_age_days": clean(base.get("origin_age_days")),
                    "origin_price": origin_price,
                    "actual_price": actual_price,
                    "predicted_price": predicted_price,
                    "actual_return": actual_return,
                    "predicted_return": predicted_return,
                    "absolute_error": abs(predicted_price - actual_price),
                    "absolute_percentage_error": abs(predicted_price - actual_price) / actual_price,
                    "signed_error": predicted_price - actual_price,
                    "direction_correct": (predicted_return >= 0) == (actual_return >= 0),
                    "evaluation_partition": "OUTER_CHAMPION" if is_product_holdout or is_latest_holdout else "INNER_DISCOVERY",
                    "current_only_features_used": False,
                }
                if record["evaluation_partition"] == "OUTER_CHAMPION":
                    champion_eval.append(record)
                else:
                    discovery_eval.append(record)
            discovery_metric = metrics(discovery_eval, major_threshold)
            complexity = sum([
                clean(candidate.get("feature_subset")) != "PRICE_ONLY",
                num(candidate.get("recency_weight")) > 0,
                num(candidate.get("shrinkage_strength")) > 0,
                num(candidate.get("trend_damping"), 1.0) != 1.0,
                clean(candidate.get("model_family")).endswith("ENSEMBLE"),
            ])
            score_rows.append({
                "refinement_group_id": group_id,
                "candidate_id": clean(candidate["candidate_id"]),
                "horizon_label": horizon_label,
                "horizon_days": horizon_days,
                "route": route,
                "model_family": model,
                "feature_subset": clean(candidate["feature_subset"]),
                "lookback_months": clean(candidate["lookback_months"]),
                "recency_weight": clean(candidate["recency_weight"]),
                "trend_damping": clean(candidate["trend_damping"]),
                "shrinkage_strength": clean(candidate["shrinkage_strength"]),
                "discovery_rows": discovery_metric["row_count"],
                "discovery_mape": round(discovery_metric["mape"], 6),
                "discovery_mae": round(discovery_metric["mae"], 6),
                "discovery_directional_accuracy": round(discovery_metric["directional_accuracy"], 6),
                "discovery_bias_ratio": round(discovery_metric["bias_ratio"], 6),
                "discovery_major_grower_precision": round(discovery_metric["major_grower_precision"], 6),
                "discovery_major_grower_recall": round(discovery_metric["major_grower_recall"], 6),
                "discovery_early_detection_rate": round(discovery_metric["early_detection_rate"], 6),
                "penalized_discovery_objective": round(objective(discovery_metric, horizon_days, complexity, len(group_candidates), contract), 8),
                "eligible_for_finalist": discovery_metric["row_count"] >= contract["minimum_discovery_rows_per_candidate"],
            })

        group_scores = [r for r in score_rows if r["refinement_group_id"] == group_id and r["eligible_for_finalist"]]
        group_scores.sort(key=lambda r: (r["penalized_discovery_objective"], r["candidate_id"]))
        selected = group_scores[: contract["finalists_per_group"]]
        if len(selected) != contract["finalists_per_group"]:
            failures.append("INSUFFICIENT_FINALISTS:" + group_id)
            continue

        candidate_lookup = {clean(c["candidate_id"]): c for c in group_candidates}
        for rank, selected_score in enumerate(selected, start=1):
            candidate = candidate_lookup[selected_score["candidate_id"]]
            model = clean(candidate["model_family"])
            source = predictions_by_key.get((horizon_label, route, model), []) or predictions_by_key.get((horizon_label, route, round1_winner), [])
            champion_eval = []
            for base in source:
                cid = clean(base["canonical_product_id"])
                is_product_holdout = stable_bucket(cid, contract["outer_product_holdout_modulus"]) == contract["outer_product_holdout_remainder"]
                is_latest_holdout = clean(base["origin_date"]) >= champion_date_cutoff
                if not (is_product_holdout or is_latest_holdout):
                    continue
                predicted_price = candidate_prediction(candidate, base, route_centers.get(model, 0.0))
                actual_price = max(num(base["actual_price"], 0.01), 0.01)
                origin_price = max(num(base["origin_price"], 0.01), 0.01)
                predicted_return = predicted_price / origin_price - 1
                actual_return = num(base["actual_return"])
                record = {
                    "refinement_group_id": group_id,
                    "candidate_id": clean(candidate["candidate_id"]),
                    "horizon_label": horizon_label,
                    "horizon_days": horizon_days,
                    "route": route,
                    "canonical_product_id": cid,
                    "product_name": clean(base.get("product_name")),
                    "origin_date": clean(base["origin_date"]),
                    "origin_age_days": clean(base.get("origin_age_days")),
                    "origin_price": origin_price,
                    "actual_price": actual_price,
                    "predicted_price": predicted_price,
                    "actual_return": actual_return,
                    "predicted_return": predicted_return,
                    "absolute_error": abs(predicted_price - actual_price),
                    "absolute_percentage_error": abs(predicted_price - actual_price) / actual_price,
                    "signed_error": predicted_price - actual_price,
                    "direction_correct": (predicted_return >= 0) == (actual_return >= 0),
                    "evaluation_partition": "OUTER_CHAMPION",
                    "current_only_features_used": False,
                }
                champion_eval.append(record)
                finalist_predictions.append(record)
            champion_metric = metrics(champion_eval, major_threshold)
            finalist_rows.append({
                **selected_score,
                "discovery_rank": rank,
                "champion_rows": champion_metric["row_count"],
                "champion_mape": round(champion_metric["mape"], 6),
                "champion_mae": round(champion_metric["mae"], 6),
                "champion_directional_accuracy": round(champion_metric["directional_accuracy"], 6),
                "champion_bias_ratio": round(champion_metric["bias_ratio"], 6),
                "champion_major_grower_precision": round(champion_metric["major_grower_precision"], 6),
                "champion_major_grower_recall": round(champion_metric["major_grower_recall"], 6),
                "champion_early_detection_rate": round(champion_metric["early_detection_rate"], 6),
                "champion_evidence_sufficient": champion_metric["row_count"] >= contract["minimum_champion_rows_per_finalist"],
            })

        group_finalists = [r for r in finalist_rows if r["refinement_group_id"] == group_id and r["champion_evidence_sufficient"]]
        group_finalists.sort(key=lambda r: (r["champion_mape"], -r["champion_directional_accuracy"], r["candidate_id"]))
        best = group_finalists[0] if group_finalists else None
        r1_rows = predictions_by_key.get((horizon_label, route, round1_winner), [])
        r1_outer = []
        for base in r1_rows:
            cid = clean(base["canonical_product_id"])
            if stable_bucket(cid, contract["outer_product_holdout_modulus"]) != contract["outer_product_holdout_remainder"] and clean(base["origin_date"]) < champion_date_cutoff:
                continue
            r1_outer.append({
                "absolute_percentage_error": num(base["absolute_percentage_error"]),
                "absolute_error": num(base["absolute_error"]),
                "signed_error": num(base["signed_error"]),
                "actual_price": num(base["actual_price"], 0.01),
                "direction_correct": truth(base["direction_correct"]),
                "actual_return": num(base["actual_return"]),
                "predicted_return": num(base["predicted_return"]),
                "origin_age_days": clean(base.get("origin_age_days")),
            })
        r1_metric = metrics(r1_outer, major_threshold)
        if best:
            relative_improvement = (r1_metric["mape"] - float(best["champion_mape"])) / max(r1_metric["mape"], 1e-9)
            promoted = (
                relative_improvement >= contract["minimum_relative_mape_improvement_for_champion"]
                and float(best["champion_directional_accuracy"]) >= contract["minimum_directional_accuracy"]
                and float(best["champion_bias_ratio"]) <= contract["maximum_absolute_bias_ratio"]
            )
            decision = "ROUND2_FINALIST_ADVANCES" if promoted else "RETAIN_ROUND1_CHAMPION"
            champion_rows.append({
                "refinement_group_id": group_id,
                "horizon_label": horizon_label,
                "horizon_days": horizon_days,
                "route": route,
                "round1_champion": round1_winner,
                "round1_outer_mape": round(r1_metric["mape"], 6),
                "round2_candidate_id": best["candidate_id"],
                "round2_model_family": best["model_family"],
                "round2_outer_mape": best["champion_mape"],
                "round2_outer_directional_accuracy": best["champion_directional_accuracy"],
                "round2_outer_bias_ratio": best["champion_bias_ratio"],
                "relative_mape_improvement": round(relative_improvement, 6),
                "round3_challenge_entry": decision,
                "production_promotion_authorized": False,
            })
        else:
            champion_rows.append({
                "refinement_group_id": group_id,
                "horizon_label": horizon_label,
                "horizon_days": horizon_days,
                "route": route,
                "round1_champion": round1_winner,
                "round1_outer_mape": round(r1_metric["mape"], 6),
                "round2_candidate_id": "",
                "round2_model_family": "",
                "round2_outer_mape": "",
                "round2_outer_directional_accuracy": "",
                "round2_outer_bias_ratio": "",
                "relative_mape_improvement": "",
                "round3_challenge_entry": "NO_ROUND2_FINALIST",
                "production_promotion_authorized": False,
            })

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_round2_candidate_scores.csv", score_rows)
    write_csv(OUTPUT / "collector_round2_finalists.csv", finalist_rows)
    write_csv(OUTPUT / "collector_round2_outer_predictions.csv", finalist_predictions)
    write_csv(OUTPUT / "collector_round2_champion_challenge_registry.csv", champion_rows)

    advances = sum(r["round3_challenge_entry"] == "ROUND2_FINALIST_ADVANCES" for r in champion_rows)
    retained = sum(r["round3_challenge_entry"] == "RETAIN_ROUND1_CHAMPION" for r in champion_rows)
    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_ADAPTIVE_REFINEMENT_EXECUTION"
    summary = {
        "block_name": contract["contract_name"],
        "block_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "refinement_groups": len(eligible_groups),
        "candidate_rows_evaluated": len(score_rows),
        "finalist_rows": len(finalist_rows),
        "outer_prediction_rows": len(finalist_predictions),
        "round2_finalists_advancing": advances,
        "round1_champions_retained": retained,
        "round3_group_decisions": len(champion_rows),
        "major_365_growth_threshold": major_threshold,
        "nested_validation_completed": True,
        "product_holdout_completed": True,
        "latest_time_holdout_completed": True,
        "multiple_testing_penalty_applied": True,
        "current_only_features_used": False,
        "round3_champion_challenge_authorized": not failures,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_adaptive_refinement_execution_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
