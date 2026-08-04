from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_adaptive_tournament_refinement_architecture_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/adaptive_tournament_refinement_architecture"


def clean(value: Any) -> str:
    return str(value or "").strip()


def truthy(value: Any) -> bool:
    return clean(value).casefold() in {"true", "1", "yes", "pass", "competitive_winner"}


def number(value: Any) -> float | None:
    try:
        return float(clean(value))
    except (TypeError, ValueError):
        return None


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_bytes(payload: bytes) -> list[dict[str, str]]:
    text = payload.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def first_column(rows: list[dict[str, str]], aliases: tuple[str, ...]) -> str | None:
    if not rows:
        return None
    normalized = {clean(column).casefold(): column for column in rows[0].keys()}
    for alias in aliases:
        found = normalized.get(alias.casefold())
        if found:
            return found
    return None


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_round_one(contract: dict) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    package = contract["required_round_one_package"]
    path = Path(tempfile.gettempdir()) / package["package_name"]
    diagnostics: list[dict[str, Any]] = []
    if not path.is_file():
        raise RuntimeError(f"ROUND_ONE_PACKAGE_MISSING:{path}")
    actual_hash = sha256_file(path)
    if actual_hash != package["sha256"]:
        raise RuntimeError(f"ROUND_ONE_PACKAGE_HASH_DRIFT:expected={package['sha256']}:actual={actual_hash}")
    with zipfile.ZipFile(path) as archive:
        available = {Path(member.filename).name: member for member in archive.infolist() if not member.is_dir()}
        payloads: dict[str, bytes] = {}
        for required_name in contract["required_round_one_members"]:
            member = available.get(required_name)
            if member is None:
                raise RuntimeError(f"ROUND_ONE_MEMBER_MISSING:{required_name}")
            payload = archive.read(member)
            payloads[required_name] = payload
            diagnostics.append({
                "artifact_role": "ROUND_ONE_CERTIFIED_INPUT",
                "package_name": path.name,
                "package_sha256": actual_hash,
                "member_name": required_name,
                "member_sha256": sha256_bytes(payload),
                "row_count": len(read_csv_bytes(payload)) if required_name.endswith(".csv") else "",
            })
    return payloads, diagnostics


def parameter_combinations(grid: dict[str, list[Any]], limit: int) -> list[dict[str, Any]]:
    names = list(grid)
    values = [grid[name] for name in names]
    rows: list[dict[str, Any]] = []
    for combo in itertools.product(*values):
        rows.append(dict(zip(names, combo)))
        if len(rows) >= limit:
            break
    return rows


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payloads, lineage = load_round_one(contract)
    summary = json.loads(payloads["precollector_round_one_execution_summary.json"].decode("utf-8-sig"))
    winners = read_csv_bytes(payloads["precollector_round_one_preliminary_winner_registry.csv"])
    scores = read_csv_bytes(payloads["precollector_round_one_model_scorecard.csv"])
    predictions = read_csv_bytes(payloads["precollector_round_one_rolling_predictions.csv"])
    uncertainty = read_csv_bytes(payloads["precollector_round_one_uncertainty_evidence.csv"])

    expected = contract["expected_round_one_counts"]
    observed = {
        "active_products": summary.get("active_product_rows"),
        "horizons": summary.get("forecast_horizon_count"),
        "routes": summary.get("route_count"),
        "tournament_groups": summary.get("winner_registry_rows"),
        "competitive_winners": summary.get("competitive_winner_rows"),
        "governed_fallbacks": summary.get("fallback_winner_rows"),
        "rolling_predictions": summary.get("rolling_prediction_rows"),
        "model_scorecards": summary.get("model_scorecard_rows"),
        "uncertainty_rows": summary.get("uncertainty_evidence_rows"),
    }
    failures = [f"ROUND_ONE_COUNT_DRIFT:{key}:expected={value}:actual={observed.get(key)}" for key, value in expected.items() if observed.get(key) != value]
    if summary.get("certification_status") != contract["required_round_one_status"]:
        failures.append(f"ROUND_ONE_STATUS_NOT_CERTIFIED:{summary.get('certification_status')}")

    horizon_col = first_column(winners, ("horizon_code", "horizon_label"))
    days_col = first_column(winners, ("horizon_days", "days"))
    route_col = first_column(winners, ("forecast_method", "route"))
    winner_col = first_column(winners, ("winner_model", "model_name", "selected_model"))
    status_col = first_column(winners, ("selection_status", "winner_status", "status"))
    score_horizon_col = first_column(scores, ("horizon_code", "horizon_label"))
    score_route_col = first_column(scores, ("forecast_method", "route"))
    score_model_col = first_column(scores, ("model_name", "candidate_model"))
    score_metric_col = first_column(scores, ("median_absolute_percentage_error", "mape", "score"))
    if not all((horizon_col, route_col, winner_col, status_col, score_horizon_col, score_route_col, score_model_col)):
        failures.append("ROUND_ONE_SCHEMA_UNRESOLVED")

    scores_by_group: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in scores:
        scores_by_group[(clean(row.get(score_horizon_col)), clean(row.get(score_route_col)))].append(row)
    for rows in scores_by_group.values():
        rows.sort(key=lambda row: (number(row.get(score_metric_col)) if score_metric_col and number(row.get(score_metric_col)) is not None else 1e18, clean(row.get(score_model_col))))

    group_rows: list[dict[str, Any]] = []
    contender_rows: list[dict[str, Any]] = []
    parameter_rows: list[dict[str, Any]] = []
    boundary_rows: list[dict[str, Any]] = []
    max_candidates = int(contract["candidate_limits"]["maximum_per_group"])

    for decision in winners:
        horizon = clean(decision.get(horizon_col))
        route = clean(decision.get(route_col))
        days = int(number(decision.get(days_col)) or 0) if days_col else 0
        round_one_winner = clean(decision.get(winner_col))
        round_one_status = clean(decision.get(status_col))
        competitive = "COMPETITIVE" in round_one_status.upper()
        mode = "COMPETITIVE_REFINEMENT" if competitive else contract["advancement"]["fallback_group_mode"]
        group_id = f"R2-{horizon}-{route}"
        ranked_models = [clean(row.get(score_model_col)) for row in scores_by_group.get((horizon, route), []) if clean(row.get(score_model_col))]
        if competitive:
            contenders = ranked_models[: int(contract["advancement"]["competitive_group_scorecard_contenders"])]
        else:
            contenders = ranked_models[:]
        preserved = [round_one_winner]
        if route.startswith("DIRECT_HISTORY"):
            preserved.append("NAIVE_LAST_VALUE")
        else:
            preserved.append(contract.get("fallback_models", {}).get(route, "RANK_DECAY_WEIGHTED_GROWTH"))
        for model in preserved:
            if model and model not in contenders:
                contenders.append(model)
        contenders = list(dict.fromkeys(contenders))

        group_rows.append({
            "refinement_group_id": group_id,
            "horizon_code": horizon,
            "horizon_days": days,
            "forecast_method": route,
            "round_one_status": round_one_status,
            "round_one_winner": round_one_winner,
            "refinement_mode": mode,
            "contender_count": len(contenders),
            "identical_round_one_folds_required": True,
            "untouched_champion_folds_required": True,
            "baseline_challenge_required": True,
            "round_one_champion_challenge_required": True,
            "no_forced_winner": True,
            "refinement_execution_authorized": True,
            "final_winner_certification_authorized": False,
        })

        generated = 0
        for rank, model in enumerate(contenders, start=1):
            contender_rows.append({
                "refinement_group_id": group_id,
                "contender_rank": rank,
                "model_name": model,
                "advancement_reason": "ROUND_ONE_WINNER_PRESERVED" if model == round_one_winner else "ROUND_ONE_SCORECARD_CONTENDER",
                "round_one_winner_indicator": model == round_one_winner,
                "baseline_indicator": model == "NAIVE_LAST_VALUE",
                "fallback_recovery_indicator": not competitive,
            })
            grid = contract["parameter_grids"].get(model, {"governed_default": ["DEFAULT"]})
            remaining = max_candidates - generated
            combos = parameter_combinations(grid, max(remaining, 0))
            for combo_index, params in enumerate(combos, start=1):
                generated += 1
                parameter_rows.append({
                    "refinement_group_id": group_id,
                    "candidate_id": f"{group_id}-{rank:02d}-{combo_index:03d}",
                    "model_name": model,
                    "parameter_json": json.dumps(params, sort_keys=True, separators=(",", ":")),
                    "round_one_winner_indicator": model == round_one_winner,
                    "baseline_indicator": model == "NAIVE_LAST_VALUE",
                    "discovery_fold_role": "INNER_DISCOVERY",
                    "champion_fold_role": "OUTER_UNTOUCHED_CHALLENGE",
                    "multiple_testing_penalty_required": True,
                    "complexity_penalty_required": True,
                    "boundary_review_required": True,
                    "current_only_features_used": False,
                })
                if generated >= max_candidates:
                    break
            for parameter_name, values in grid.items():
                boundary_rows.append({
                    "refinement_group_id": group_id,
                    "model_name": model,
                    "parameter_name": parameter_name,
                    "grid_minimum": min(values) if values and all(isinstance(v, (int, float)) for v in values) else clean(values[0]) if values else "",
                    "grid_maximum": max(values) if values and all(isinstance(v, (int, float)) for v in values) else clean(values[-1]) if values else "",
                    "expand_if_best_at_minimum": True,
                    "expand_if_best_at_maximum": True,
                    "maximum_expansion_rounds": contract["boundary_expansion"]["maximum_expansion_rounds"],
                    "expansion_factor": contract["boundary_expansion"]["continuous_parameter_expansion_factor"],
                    "retain_original_grid": True,
                })
            if generated >= max_candidates:
                break

        minimum = contract["candidate_limits"]["minimum_per_competitive_group"] if competitive else contract["candidate_limits"]["minimum_per_fallback_group"]
        if generated < minimum:
            failures.append(f"INSUFFICIENT_REFINEMENT_CANDIDATES:{group_id}:minimum={minimum}:actual={generated}")

    prediction_horizon_col = first_column(predictions, ("horizon_code", "horizon_label"))
    prediction_route_col = first_column(predictions, ("forecast_method", "route"))
    prediction_product_col = first_column(predictions, ("canonical_product_id", "product_id"))
    origin_col = first_column(predictions, ("origin_date", "forecast_origin_date"))
    target_col = first_column(predictions, ("target_date", "actual_date"))
    fold_rows: list[dict[str, Any]] = []
    seen_folds: set[tuple[str, str, str, str, str]] = set()
    if all((prediction_horizon_col, prediction_route_col, prediction_product_col, origin_col, target_col)):
        for row in predictions:
            key = (
                clean(row.get(prediction_horizon_col)), clean(row.get(prediction_route_col)),
                clean(row.get(prediction_product_col)), clean(row.get(origin_col)), clean(row.get(target_col)),
            )
            if key in seen_folds:
                continue
            seen_folds.add(key)
            fold_rows.append({
                "horizon_code": key[0],
                "forecast_method": key[1],
                "canonical_product_id": key[2],
                "origin_date": key[3],
                "target_date": key[4],
                "fold_membership_source": "CERTIFIED_ROUND_ONE_ROLLING_PREDICTIONS",
                "fold_membership_mutable": False,
                "discovery_or_champion_assignment_deferred_to_execution": True,
            })
    else:
        failures.append("ROUND_ONE_FOLD_SCHEMA_UNRESOLVED")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    write_csv(OUTPUT_DIR / outputs["round_one_lineage_csv"], lineage,
              ["artifact_role", "package_name", "package_sha256", "member_name", "member_sha256", "row_count"])
    write_csv(OUTPUT_DIR / outputs["group_registry_csv"], group_rows, list(group_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["contender_registry_csv"], contender_rows, list(contender_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["parameter_registry_csv"], parameter_rows, list(parameter_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["fold_registry_csv"], fold_rows, list(fold_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["boundary_policy_csv"], boundary_rows, list(boundary_rows[0].keys()))

    architecture_status = "PASS" if not failures else "FAIL"
    architecture_summary = {
        "certification_status": architecture_status,
        "round_one_package_sha256": contract["required_round_one_package"]["sha256"],
        "refinement_group_rows": len(group_rows),
        "competitive_refinement_groups": sum(row["refinement_mode"] == "COMPETITIVE_REFINEMENT" for row in group_rows),
        "fallback_recovery_groups": sum(row["refinement_mode"] == contract["advancement"]["fallback_group_mode"] for row in group_rows),
        "contender_registry_rows": len(contender_rows),
        "parameter_candidate_rows": len(parameter_rows),
        "preserved_fold_rows": len(fold_rows),
        "boundary_policy_rows": len(boundary_rows),
        "identical_round_one_folds_required": True,
        "nested_rolling_origin_required": True,
        "discovery_and_champion_folds_separate": True,
        "product_group_holdout_required": True,
        "multiple_testing_penalty_required": True,
        "round_one_champion_challenge_required": True,
        "uncertainty_recalibration_required": True,
        "recursive_upstream_rebuild_performed": False,
        "live_network_collection_performed": False,
        "refinement_execution_performed": False,
        "critical_failures": failures,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_ADAPTIVE_REFINEMENT_ARCHITECTURE",
        "refinement_execution_authorized": not failures,
        "final_winner_certification_authorized": False,
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "uip_delivery_authorized": False,
    }
    summary_path = OUTPUT_DIR / outputs["summary_json"]
    summary_path.write_text(json.dumps(architecture_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_path": CONTRACT_PATH.relative_to(ROOT).as_posix(),
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "round_one_package": contract["required_round_one_package"],
        "outputs": [
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUTPUT_DIR.iterdir()) if path.is_file()
        ],
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE" if not failures else "FAIL_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE")
    print(f"REFINEMENT_GROUP_ROWS={len(group_rows)}")
    print(f"COMPETITIVE_REFINEMENT_GROUPS={architecture_summary['competitive_refinement_groups']}")
    print(f"FALLBACK_RECOVERY_GROUPS={architecture_summary['fallback_recovery_groups']}")
    print(f"CONTENDER_REGISTRY_ROWS={len(contender_rows)}")
    print(f"PARAMETER_CANDIDATE_ROWS={len(parameter_rows)}")
    print(f"PRESERVED_FOLD_ROWS={len(fold_rows)}")
    print(f"BOUNDARY_POLICY_ROWS={len(boundary_rows)}")
    print("RECURSIVE_UPSTREAM_REBUILD_PERFORMED=FALSE")
    print("LIVE_NETWORK_COLLECTION_PERFORMED=FALSE")
    print("REFINEMENT_EXECUTION_PERFORMED=FALSE")
    print(f"NEXT_STAGE={architecture_summary['next_stage']}")
    print("FINAL_WINNER_CERTIFICATION_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
