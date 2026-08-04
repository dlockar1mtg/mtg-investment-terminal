from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import math
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_adaptive_tournament_refinement_execution_contract_v1.json"
ROUND1_CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_horizon_tournament_execution_from_certified_bundle_contract_v1.json"
ROUND1_BASE = ROOT / "scripts/run_precollector_horizon_tournaments_from_certified_bundle.py"
ROUND1_V11 = ROOT / "scripts/run_precollector_horizon_tournaments_from_certified_bundle_v1_1.py"
OUTPUT_DIR = ROOT / "artifacts/precollector/adaptive_tournament_refinement_execution"


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float | None:
    try:
        result = float(clean(value).replace("$", "").replace(",", ""))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def parse_date(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(clean(value)[:10])
    except ValueError:
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_csv_bytes(payload: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig", errors="strict"))))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"MODULE_NOT_LOADABLE:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_zip_binding(binding: dict[str, str], required: list[str]) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    path = Path(tempfile.gettempdir()) / binding["package_name"]
    if not path.is_file():
        raise RuntimeError(f"CERTIFIED_PACKAGE_MISSING:{path.name}")
    actual = sha256_file(path)
    if actual != binding["sha256"]:
        raise RuntimeError(f"CERTIFIED_PACKAGE_HASH_DRIFT:{path.name}:expected={binding['sha256']}:actual={actual}")
    payloads: dict[str, bytes] = {}
    lineage: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        members = {Path(item.filename).name: item for item in archive.infolist() if not item.is_dir()}
        for name in required:
            member = members.get(name)
            if member is None:
                raise RuntimeError(f"CERTIFIED_MEMBER_MISSING:{path.name}:{name}")
            payload = archive.read(member)
            payloads[name] = payload
            lineage.append({
                "package_name": path.name,
                "package_sha256": actual,
                "member_name": name,
                "member_sha256": sha256_bytes(payload),
                "row_count": len(read_csv_bytes(payload)) if name.endswith(".csv") else "",
            })
    return payloads, lineage


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


def robust_slope(values: list[float]) -> float:
    slopes: list[float] = []
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            slopes.append((values[j] - values[i]) / (j - i))
    return median(slopes) if slopes else 0.0


def direct_prediction(model: str, prices: list[float], steps: float, params: dict[str, Any]) -> float:
    last = prices[-1]
    lookback = int(params.get("lookback_observations", len(prices)) or len(prices))
    sample = prices[-max(1, lookback):]
    logs = [math.log(max(value, 0.01)) for value in sample]
    if model == "NAIVE_LAST_VALUE":
        return last
    if model in {"DRIFT", "MEDIAN_LOG_DRIFT"}:
        returns = [logs[i] - logs[i - 1] for i in range(1, len(logs))]
        raw = median(returns) if model == "MEDIAN_LOG_DRIFT" and returns else ((logs[-1] - logs[0]) / max(len(logs) - 1, 1))
        recency = float(params.get("recency_weight", 0.0) or 0.0)
        if returns and recency > 0:
            recent = median(returns[-min(3, len(returns)):])
            raw = (1 - recency) * raw + recency * recent
        shrink = float(params.get("drift_shrinkage", 0.0) or 0.0)
        return last * math.exp(raw * (1 - shrink) * steps)
    if model in {"ROBUST_LOG_LINEAR", "ROBUST_LOG_TREND"}:
        slope = robust_slope(logs)
        damping = float(params.get("trend_damping", 1.0) or 1.0)
        scale = float(params.get("robust_loss_scale", 1.0) or 1.0)
        slope = max(-0.5 * scale, min(0.5 * scale, slope))
        return last * math.exp(slope * damping * steps)
    if model in {"DAMPED_TREND", "DAMPED_LOG_TREND"}:
        slope = robust_slope(logs)
        damping = float(params.get("trend_damping", 0.75) or 0.75)
        recency = float(params.get("recency_weight", 0.5) or 0.5)
        if len(logs) >= 4:
            recent = robust_slope(logs[-4:])
            slope = (1 - recency) * slope + recency * recent
        return last * math.exp(slope * damping * steps)
    if model == "EXPONENTIAL_SMOOTHING":
        alpha = float(params.get("alpha", 0.35) or 0.35)
        damping = float(params.get("trend_damping", 1.0) or 1.0)
        level = sample[0]
        for value in sample[1:]:
            level = alpha * value + (1 - alpha) * level
        local = math.log(max(last, 0.01) / max(level, 0.01))
        return last * math.exp(local * damping * min(steps, 12.0) / 12.0)
    if model == "SHRUNK_DIRECT_COMPARABLE_BLEND":
        direct = direct_prediction("DRIFT", prices, steps, {
            "lookback_observations": lookback,
            "recency_weight": 0.25,
            "drift_shrinkage": params.get("shrinkage_strength", 0.4),
        })
        weight = float(params.get("direct_weight", 0.5) or 0.5)
        return math.exp(weight * math.log(max(direct, 0.01)) + (1 - weight) * math.log(max(last, 0.01)))
    return last


def comparable_prediction(model: str, target_last: float, returns: list[tuple[float, float, int]], params: dict[str, Any]) -> float:
    if not returns:
        return target_last
    count = int(params.get("comparable_count", len(returns)) or len(returns))
    chosen = sorted(returns, key=lambda row: row[2])[:max(1, count)]
    values = [row[0] for row in chosen]
    winsor = float(params.get("growth_winsorization", 0.0) or 0.0)
    if winsor > 0 and len(values) > 2:
        lo, hi = percentile(values, winsor), percentile(values, 1 - winsor)
        values = [max(lo, min(hi, value)) for value in values]
    exponent = float(params.get("rank_decay_exponent", 1.0) or 1.0)
    weights = [(1.0 / max(row[2], 1)) ** exponent for row in chosen]
    weighted = sum(value * weight for value, weight in zip(values, weights)) / max(sum(weights), 1e-9)
    med = median(values)
    if model == "COMPARABLE_MEDIAN_GROWTH":
        growth = med
    elif model == "RANK_DECAY_WEIGHTED_GROWTH":
        growth = weighted
    elif model == "LIFECYCLE_MATCHED_COMPARABLE":
        growth = 0.8 * weighted + 0.2 * med
    elif model == "SHRUNK_COMPARABLE_ENSEMBLE":
        median_weight = float(params.get("median_weight", 0.35) or 0.35)
        shrink = float(params.get("shrinkage_strength", 0.4) or 0.4)
        growth = ((1 - median_weight) * weighted + median_weight * med) * (1 - shrink)
    else:
        growth = weighted
    return target_last * max(0.05, 1 + growth)


def metrics(errors: list[dict[str, float]]) -> dict[str, float]:
    if not errors:
        return {"rows": 0, "median_ape": 0.0, "mae": 0.0, "bias": 0.0, "directional_accuracy": 0.0, "stability": 0.0, "uncertainty_width": 0.0}
    apes = [row["ape"] for row in errors]
    signed = [row["signed_error"] for row in errors]
    return {
        "rows": len(errors),
        "median_ape": median(apes),
        "mae": sum(abs(value) for value in signed) / len(signed),
        "bias": sum(signed) / len(signed),
        "directional_accuracy": sum(row["direction_ok"] for row in errors) / len(errors),
        "stability": percentile(apes, 0.80) - percentile(apes, 0.20),
        "uncertainty_width": percentile(apes, 0.90),
    }


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    round1_required = [
        "precollector_round_one_preliminary_winner_registry.csv",
        "precollector_round_one_model_scorecard.csv",
        "precollector_round_one_execution_summary.json",
    ]
    arch_required = [
        "precollector_round_two_refinement_group_registry.csv",
        "precollector_round_two_contender_registry.csv",
        "precollector_round_two_parameter_candidate_registry.csv",
        "precollector_round_two_fold_preservation_registry.csv",
        "precollector_round_two_boundary_expansion_policy.csv",
        "precollector_adaptive_refinement_architecture_summary.json",
    ]
    round1_payloads, lineage1 = load_zip_binding(contract["required_round_one_package"], round1_required)
    arch_payloads, lineage2 = load_zip_binding(contract["required_architecture_package"], arch_required)
    architecture_summary = json.loads(arch_payloads["precollector_adaptive_refinement_architecture_summary.json"].decode("utf-8-sig"))
    failures: list[str] = []
    expected = contract["expected_counts"]
    observed = {
        "refinement_groups": architecture_summary.get("refinement_group_rows"),
        "competitive_groups": architecture_summary.get("competitive_refinement_groups"),
        "fallback_recovery_groups": architecture_summary.get("fallback_recovery_groups"),
        "parameter_candidates": architecture_summary.get("parameter_candidate_rows"),
        "preserved_folds": architecture_summary.get("preserved_fold_rows"),
    }
    failures.extend(f"ARCHITECTURE_COUNT_DRIFT:{key}:expected={value}:actual={observed.get(key)}" for key, value in expected.items() if observed.get(key) != value)
    if architecture_summary.get("certification_status") != "PASS":
        failures.append("ARCHITECTURE_NOT_CERTIFIED")

    groups = read_csv_bytes(arch_payloads["precollector_round_two_refinement_group_registry.csv"])
    candidates = read_csv_bytes(arch_payloads["precollector_round_two_parameter_candidate_registry.csv"])
    folds = read_csv_bytes(arch_payloads["precollector_round_two_fold_preservation_registry.csv"])
    boundary = read_csv_bytes(arch_payloads["precollector_round_two_boundary_expansion_policy.csv"])
    winners = read_csv_bytes(round1_payloads["precollector_round_one_preliminary_winner_registry.csv"])

    base = load_module(ROUND1_BASE, "precollector_round1_base_for_round2")
    v11 = load_module(ROUND1_V11, "precollector_round1_v11_for_round2")
    round1_contract = json.loads(ROUND1_CONTRACT_PATH.read_text(encoding="utf-8"))
    artifacts, authority_lineage, authority_diagnostics = base.load_certified_inputs(round1_contract)
    history_rows, history_lineage = v11.read_bound_history(round1_contract)
    artifacts["CANONICAL_HISTORICAL_PRICE"] = history_rows
    if any(row.get("severity") == "BLOCKING" for row in authority_diagnostics):
        failures.append("CERTIFIED_AUTHORITY_LOAD_FAILURE")

    series = base.build_series(history_rows)
    comparable_rows = artifacts["APPROVED_COMPARABLE_LEDGER"]
    target_col = base.first_column(comparable_rows, ("target_canonical_product_id", "target_product_id", "canonical_product_id"))
    comp_col = base.first_column(comparable_rows, ("comparable_canonical_product_id", "comparable_product_id"))
    rank_col = base.first_column(comparable_rows, ("comparable_rank", "rank", "selection_rank"))
    comparables: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for row in comparable_rows:
        target = clean(row.get(target_col))
        comp = clean(row.get(comp_col))
        rank = int(number(row.get(rank_col)) or len(comparables[target]) + 1) if rank_col else len(comparables[target]) + 1
        if target and comp:
            comparables[target].append((comp, rank))

    folds_by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    assignment_rows: list[dict[str, Any]] = []
    modulus = int(contract["fold_assignment"]["champion_modulus"])
    remainder = int(contract["fold_assignment"]["champion_remainder"])
    for fold in folds:
        group_id = f"R2-{clean(fold.get('horizon_code'))}-{clean(fold.get('forecast_method'))}"
        key = "|".join([group_id, clean(fold.get("canonical_product_id")), clean(fold.get("origin_date")), clean(fold.get("target_date"))])
        role = "CHAMPION" if int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % modulus == remainder else "DISCOVERY"
        enriched = dict(fold)
        enriched["refinement_group_id"] = group_id
        enriched["fold_role"] = role
        folds_by_group[group_id].append(enriched)
        assignment_rows.append(enriched)

    winner_by_group = {f"R2-{clean(row.get('horizon_code'))}-{clean(row.get('forecast_method'))}": clean(row.get("winner_model")) for row in winners}
    group_mode = {clean(row.get("refinement_group_id")): clean(row.get("refinement_mode")) for row in groups}
    boundary_lookup = {(clean(row.get("refinement_group_id")), clean(row.get("model_name")), clean(row.get("parameter_name"))): row for row in boundary}
    candidates_by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        candidates_by_group[clean(row.get("refinement_group_id"))].append(row)

    score_rows: list[dict[str, Any]] = []
    errors_by_candidate: dict[str, dict[str, list[dict[str, float]]]] = {}
    for group_id, rows in candidates_by_group.items():
        group_folds = folds_by_group.get(group_id, [])
        candidate_count = len(rows)
        for candidate in rows:
            candidate_id = clean(candidate.get("candidate_id"))
            model = clean(candidate.get("model_name"))
            params = json.loads(clean(candidate.get("parameter_json")) or "{}")
            role_errors: dict[str, list[dict[str, float]]] = {"DISCOVERY": [], "CHAMPION": []}
            for fold in group_folds:
                cid = clean(fold.get("canonical_product_id"))
                origin_date = parse_date(fold.get("origin_date"))
                target_date = parse_date(fold.get("target_date"))
                history = series.get(cid, [])
                if not origin_date or not target_date or not history:
                    continue
                hist = [item for item in history if item["date"] <= origin_date]
                target_matches = [item for item in history if item["date"] == target_date]
                if not hist or not target_matches:
                    continue
                origin_price = hist[-1]["price"]
                actual = target_matches[0]["price"]
                steps = max((target_date - origin_date).days / 30.4375, 1.0)
                route = group_id.split("-", 2)[2]
                if route == "COMPARABLE_PRODUCT_ADJUSTED":
                    comp_returns: list[tuple[float, float, int]] = []
                    for comp_id, rank in comparables.get(cid, []):
                        comp_history = series.get(comp_id, [])
                        before = [item for item in comp_history if item["date"] <= origin_date]
                        after = [item for item in comp_history if item["date"] == target_date]
                        if before and after:
                            comp_returns.append((after[0]["price"] / before[-1]["price"] - 1, 1.0 / max(rank, 1), rank))
                    predicted = comparable_prediction(model, origin_price, comp_returns, params)
                else:
                    predicted = direct_prediction(model, [item["price"] for item in hist], steps, params)
                if not math.isfinite(predicted) or predicted <= 0:
                    continue
                signed_error = predicted - actual
                role_errors[clean(fold.get("fold_role"))].append({
                    "ape": abs(signed_error) / max(actual, 0.01),
                    "signed_error": signed_error,
                    "direction_ok": float((predicted - origin_price) * (actual - origin_price) >= 0),
                })
            errors_by_candidate[candidate_id] = role_errors
            discovery = metrics(role_errors["DISCOVERY"])
            champion = metrics(role_errors["CHAMPION"])
            complexity = len(params)
            penalty = contract["selection"]["complexity_penalty_per_parameter"] * complexity
            if discovery["rows"]:
                penalty += contract["selection"]["multiple_testing_penalty_scale"] * math.sqrt(math.log(max(candidate_count, 2)) / discovery["rows"])
            penalized = discovery["median_ape"] + penalty
            score_rows.append({
                "refinement_group_id": group_id,
                "candidate_id": candidate_id,
                "model_name": model,
                "parameter_json": json.dumps(params, sort_keys=True, separators=(",", ":")),
                "discovery_rows": discovery["rows"],
                "discovery_median_ape": discovery["median_ape"],
                "discovery_mae": discovery["mae"],
                "discovery_bias": discovery["bias"],
                "discovery_directional_accuracy": discovery["directional_accuracy"],
                "discovery_stability": discovery["stability"],
                "complexity_penalty": penalty,
                "penalized_discovery_score": penalized,
                "champion_rows": champion["rows"],
                "champion_median_ape": champion["median_ape"],
                "champion_mae": champion["mae"],
                "champion_bias": champion["bias"],
                "champion_directional_accuracy": champion["directional_accuracy"],
                "champion_stability": champion["stability"],
                "champion_uncertainty_width": champion["uncertainty_width"],
            })

    scores_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in score_rows:
        scores_by_group[row["refinement_group_id"]].append(row)
    decision_rows: list[dict[str, Any]] = []
    boundary_rows: list[dict[str, Any]] = []
    uncertainty_rows: list[dict[str, Any]] = []
    minimum_discovery = int(contract["fold_assignment"]["minimum_discovery_folds_for_selection"])
    minimum_champion = int(contract["fold_assignment"]["minimum_champion_folds_for_promotion"])
    for group in groups:
        group_id = clean(group.get("refinement_group_id"))
        eligible = [row for row in scores_by_group.get(group_id, []) if row["discovery_rows"] >= minimum_discovery]
        eligible.sort(key=lambda row: (row["penalized_discovery_score"], row["candidate_id"]))
        selected = eligible[0] if eligible else None
        round1_model = winner_by_group.get(group_id, "")
        benchmark_rows = [row for row in scores_by_group.get(group_id, []) if row["model_name"] == round1_model]
        benchmark = min(benchmark_rows, key=lambda row: (row["penalized_discovery_score"], row["candidate_id"])) if benchmark_rows else None
        baseline_rows = [row for row in scores_by_group.get(group_id, []) if row["model_name"] == "NAIVE_LAST_VALUE"]
        baseline = min(baseline_rows, key=lambda row: (row["penalized_discovery_score"], row["candidate_id"])) if baseline_rows else benchmark
        status = "NO_PROMOTION_INSUFFICIENT_EVIDENCE"
        promoted = False
        boundary_flag = False
        if selected and benchmark and baseline and selected["champion_rows"] >= minimum_champion:
            improve_round1 = (benchmark["champion_median_ape"] - selected["champion_median_ape"]) / max(benchmark["champion_median_ape"], 1e-9)
            improve_baseline = (baseline["champion_median_ape"] - selected["champion_median_ape"]) / max(baseline["champion_median_ape"], 1e-9)
            params = json.loads(selected["parameter_json"])
            for name, value in params.items():
                policy = boundary_lookup.get((group_id, selected["model_name"], name))
                if policy and clean(value) in {clean(policy.get("grid_minimum")), clean(policy.get("grid_maximum"))}:
                    boundary_flag = True
                    boundary_rows.append({
                        "refinement_group_id": group_id,
                        "candidate_id": selected["candidate_id"],
                        "model_name": selected["model_name"],
                        "parameter_name": name,
                        "selected_value": value,
                        "grid_minimum": policy.get("grid_minimum"),
                        "grid_maximum": policy.get("grid_maximum"),
                        "boundary_expansion_required": True,
                    })
            promoted = (
                improve_round1 >= contract["selection"]["minimum_relative_improvement_over_round_one"]
                and improve_baseline >= contract["selection"]["minimum_relative_improvement_over_baseline"]
                and abs(selected["champion_bias"]) <= contract["selection"]["maximum_absolute_bias"] * max(selected["champion_mae"], 1.0)
                and not boundary_flag
            )
            status = "PRELIMINARY_REFINED_LEADER" if promoted else ("BOUNDARY_EXPANSION_REQUIRED" if boundary_flag else "ROUND_ONE_LEADER_RETAINED")
        decision_rows.append({
            "refinement_group_id": group_id,
            "horizon_code": group.get("horizon_code"),
            "forecast_method": group.get("forecast_method"),
            "refinement_mode": group_mode.get(group_id),
            "round_one_model": round1_model,
            "selected_candidate_id": selected["candidate_id"] if selected else "",
            "selected_model": selected["model_name"] if selected else round1_model,
            "selection_status": status,
            "preliminary_promotion_indicator": promoted,
            "boundary_expansion_required": boundary_flag,
            "final_winner_certification_authorized": False,
            "forecast_generation_authorized": False,
        })
        if selected:
            uncertainty_rows.append({
                "refinement_group_id": group_id,
                "selected_candidate_id": selected["candidate_id"],
                "champion_rows": selected["champion_rows"],
                "champion_median_ape": selected["champion_median_ape"],
                "champion_uncertainty_width": selected["champion_uncertainty_width"],
                "uncertainty_recalibration_status": "PRELIMINARY_ONLY",
            })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    lineage = lineage1 + lineage2 + authority_lineage + [history_lineage]
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, ["artifact_role", "package_name", "package_sha256", "member_name", "member_sha256", "row_count"])
    write_csv(OUTPUT_DIR / outputs["fold_assignment_csv"], assignment_rows, list(assignment_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["candidate_scorecard_csv"], score_rows, list(score_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["group_decision_csv"], decision_rows, list(decision_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["boundary_review_csv"], boundary_rows, list(boundary_rows[0].keys()) if boundary_rows else ["refinement_group_id", "candidate_id", "model_name", "parameter_name", "selected_value", "grid_minimum", "grid_maximum", "boundary_expansion_required"])
    write_csv(OUTPUT_DIR / outputs["uncertainty_csv"], uncertainty_rows, list(uncertainty_rows[0].keys()))
    diagnostics = [{"severity": "BLOCKING", "code": failure, "detail": ""} for failure in failures]
    write_csv(OUTPUT_DIR / outputs["diagnostics_csv"], diagnostics, ["severity", "code", "detail"])

    status = "PASS" if not failures else "FAIL"
    summary = {
        "certification_status": status,
        "refinement_group_rows": len(groups),
        "parameter_candidate_rows": len(candidates),
        "candidate_scorecard_rows": len(score_rows),
        "preserved_fold_rows": len(folds),
        "fold_assignment_rows": len(assignment_rows),
        "preliminary_refined_leader_rows": sum(row["selection_status"] == "PRELIMINARY_REFINED_LEADER" for row in decision_rows),
        "round_one_leader_retained_rows": sum(row["selection_status"] == "ROUND_ONE_LEADER_RETAINED" for row in decision_rows),
        "boundary_expansion_required_rows": sum(bool(row["boundary_expansion_required"]) for row in decision_rows),
        "insufficient_evidence_rows": sum(row["selection_status"] == "NO_PROMOTION_INSUFFICIENT_EVIDENCE" for row in decision_rows),
        "blocking_diagnostic_rows": len(failures),
        "preserved_fold_membership_changed": False,
        "recursive_upstream_rebuild_performed": False,
        "live_network_collection_performed": False,
        "current_only_features_used": False,
        "final_winner_certification_authorized": False,
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "uip_delivery_authorized": False,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_EXECUTION",
    }
    summary_path = OUTPUT_DIR / outputs["summary_json"]
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "outputs": [
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUTPUT_DIR.iterdir()) if path.is_file() and path.name != outputs["manifest_json"]
        ],
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PASS_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_EXECUTION" if not failures else "FAIL_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_EXECUTION")
    for key, value in summary.items():
        if isinstance(value, (str, int, bool)):
            print(f"{key.upper()}={str(value).upper() if isinstance(value, bool) else value}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
