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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_final_champion_challenge_execution_contract_v1.json"
ROUND2_BASE = ROOT / "scripts/run_precollector_adaptive_tournament_refinement_execution.py"
ROUND1_BASE = ROOT / "scripts/run_precollector_horizon_tournaments_from_certified_bundle.py"
ROUND1_V11 = ROOT / "scripts/run_precollector_horizon_tournaments_from_certified_bundle_v1_1.py"
ROUND1_CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_horizon_tournament_execution_from_certified_bundle_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/final_champion_challenge_execution"


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float:
    try:
        value = float(clean(value))
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


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
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))


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


def load_zip(package: dict, required: list[str], role: str) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    path = Path(tempfile.gettempdir()) / package["package_name"]
    if not path.is_file():
        raise RuntimeError(f"PACKAGE_MISSING:{path}")
    actual = sha256_file(path)
    if actual != package["sha256"]:
        raise RuntimeError(f"PACKAGE_HASH_DRIFT:{path.name}:expected={package['sha256']}:actual={actual}")
    payloads: dict[str, bytes] = {}
    lineage: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        available = {Path(item.filename).name: item for item in archive.infolist() if not item.is_dir()}
        for name in required:
            member = available.get(name)
            if member is None:
                raise RuntimeError(f"PACKAGE_MEMBER_MISSING:{path.name}:{name}")
            payload = archive.read(member)
            payloads[name] = payload
            lineage.append({
                "artifact_role": role,
                "package_name": path.name,
                "package_sha256": actual,
                "member_name": name,
                "member_sha256": sha256_bytes(payload),
                "row_count": len(read_csv_bytes(payload)) if name.endswith(".csv") else "",
            })
    return payloads, lineage


def metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {
            "rows": 0,
            "median_ape": 0.0,
            "mae": 0.0,
            "bias": 0.0,
            "directional_accuracy": 0.0,
            "single_product_error_share": 1.0,
            "worst_product_mape_multiple": 999.0,
        }
    apes = [row["ape"] for row in rows]
    absolute_errors = [abs(row["signed_error"]) for row in rows]
    product_abs: dict[str, float] = defaultdict(float)
    product_apes: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        product_abs[row["product_id"]] += abs(row["signed_error"])
        product_apes[row["product_id"]].append(row["ape"])
    total_abs = sum(absolute_errors)
    med = median(apes)
    worst_product = max((median(values) for values in product_apes.values()), default=0.0)
    return {
        "rows": len(rows),
        "median_ape": med,
        "mae": sum(absolute_errors) / len(rows),
        "bias": sum(row["signed_error"] for row in rows) / len(rows),
        "directional_accuracy": sum(row["direction_ok"] for row in rows) / len(rows),
        "single_product_error_share": max(product_abs.values(), default=0.0) / max(total_abs, 1e-9),
        "worst_product_mape_multiple": worst_product / max(med, 1e-9),
    }


def passes_controls(metric: dict[str, float], config: dict) -> bool:
    if metric["rows"] < int(config["minimum_rows_per_partition"]):
        return False
    if metric["directional_accuracy"] < float(config["minimum_directional_accuracy"]):
        return False
    if abs(metric["bias"]) > float(config["maximum_absolute_bias_ratio"]) * max(metric["mae"], 1e-9):
        return False
    if metric["single_product_error_share"] > float(config["maximum_single_product_error_share"]):
        return False
    if metric["worst_product_mape_multiple"] > float(config["maximum_worst_product_mape_multiple"]):
        return False
    return True


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    architecture_members = [
        "precollector_final_champion_challenge_group_registry.csv",
        "precollector_final_champion_frozen_candidate_registry.csv",
        "precollector_final_champion_stress_partition_registry.csv",
        "precollector_final_champion_long_horizon_routing.csv",
        "precollector_final_champion_challenge_architecture_summary.json",
    ]
    round2_members = [
        "precollector_round_two_candidate_scorecard.csv",
        "precollector_round_two_fold_assignment.csv",
        "precollector_round_two_execution_summary.json",
    ]
    arch, lineage1 = load_zip(contract["required_architecture_package"], architecture_members, "CERTIFIED_FINAL_CHALLENGE_ARCHITECTURE")
    round2, lineage2 = load_zip(contract["required_round_two_package"], round2_members, "CERTIFIED_ROUND_TWO_EXECUTION")

    groups = read_csv_bytes(arch["precollector_final_champion_challenge_group_registry.csv"])
    frozen = read_csv_bytes(arch["precollector_final_champion_frozen_candidate_registry.csv"])
    partitions = read_csv_bytes(arch["precollector_final_champion_stress_partition_registry.csv"])
    long_routes = read_csv_bytes(arch["precollector_final_champion_long_horizon_routing.csv"])
    folds = read_csv_bytes(round2["precollector_round_two_fold_assignment.csv"])
    scorecards = read_csv_bytes(round2["precollector_round_two_candidate_scorecard.csv"])

    failures: list[str] = []
    expected = contract["expected_counts"]
    observed = {
        "short_horizon_challenge_groups": len(groups),
        "long_horizon_monte_carlo_routes": len(long_routes),
        "frozen_candidate_rows": len(frozen),
        "stress_partition_rows": len(partitions),
        "preserved_fold_rows": len(folds),
    }
    for key, value in expected.items():
        if observed.get(key) != value:
            failures.append(f"COUNT_DRIFT:{key}:expected={value}:actual={observed.get(key)}")

    round2_base = load_module(ROUND2_BASE, "precollector_round2_for_final_challenge")
    round1_base = load_module(ROUND1_BASE, "precollector_round1_for_final_challenge")
    round1_v11 = load_module(ROUND1_V11, "precollector_round1_v11_for_final_challenge")
    round1_contract = json.loads(ROUND1_CONTRACT_PATH.read_text(encoding="utf-8"))
    artifacts, authority_lineage, authority_diagnostics = round1_base.load_certified_inputs(round1_contract)
    history_rows, history_lineage = round1_v11.read_bound_history(round1_contract)
    artifacts["CANONICAL_HISTORICAL_PRICE"] = history_rows
    if any(row.get("severity") == "BLOCKING" for row in authority_diagnostics):
        failures.append("CERTIFIED_AUTHORITY_LOAD_FAILURE")

    series = round1_base.build_series(history_rows)
    comparable_rows = artifacts["APPROVED_COMPARABLE_LEDGER"]
    target_col = round1_base.first_column(comparable_rows, ("target_canonical_product_id", "target_product_id", "canonical_product_id"))
    comp_col = round1_base.first_column(comparable_rows, ("comparable_canonical_product_id", "comparable_product_id"))
    rank_col = round1_base.first_column(comparable_rows, ("comparable_rank", "rank", "selection_rank"))
    comparables: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for row in comparable_rows:
        target = clean(row.get(target_col))
        comp = clean(row.get(comp_col))
        rank = int(number(row.get(rank_col)) or len(comparables[target]) + 1) if rank_col else len(comparables[target]) + 1
        if target and comp:
            comparables[target].append((comp, rank))

    params_by_candidate = {clean(row.get("candidate_id")): json.loads(clean(row.get("parameter_json")) or "{}") for row in scorecards}
    frozen_by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in frozen:
        frozen_by_group[clean(row.get("challenge_group_id"))].append(row)
    folds_by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in folds:
        if clean(row.get("fold_role")) != contract["stress_evaluation"]["outer_all_role"]:
            continue
        challenge_group = clean(row.get("refinement_group_id")).replace("R2-", "R3-", 1)
        folds_by_group[challenge_group].append(row)

    candidate_error_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for group in groups:
        challenge_group = clean(group.get("challenge_group_id"))
        route = clean(group.get("forecast_method"))
        for candidate in frozen_by_group.get(challenge_group, []):
            model = clean(candidate.get("model_name"))
            candidate_id = clean(candidate.get("source_candidate_id"))
            params = params_by_candidate.get(candidate_id, {})
            for fold in folds_by_group.get(challenge_group, []):
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
                if route == "COMPARABLE_PRODUCT_ADJUSTED":
                    comp_returns: list[tuple[float, float, int]] = []
                    for comp_id, rank in comparables.get(cid, []):
                        comp_history = series.get(comp_id, [])
                        before = [item for item in comp_history if item["date"] <= origin_date]
                        after = [item for item in comp_history if item["date"] == target_date]
                        if before and after:
                            comp_returns.append((after[0]["price"] / before[-1]["price"] - 1, 1.0 / max(rank, 1), rank))
                    predicted = round2_base.comparable_prediction(model, origin_price, comp_returns, params)
                else:
                    predicted = round2_base.direct_prediction(model, [item["price"] for item in hist], steps, params)
                if not math.isfinite(predicted) or predicted <= 0:
                    continue
                signed_error = predicted - actual
                candidate_error_rows[(challenge_group, model)].append({
                    "product_id": cid,
                    "origin_date": origin_date,
                    "target_date": target_date,
                    "ape": abs(signed_error) / max(actual, 0.01),
                    "signed_error": signed_error,
                    "direction_ok": float((predicted - origin_price) * (actual - origin_price) >= 0),
                })

    score_rows: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    winners: list[dict[str, Any]] = []
    stress_config = contract["stress_evaluation"]
    for group in groups:
        challenge_group = clean(group.get("challenge_group_id"))
        incumbent = clean(group.get("incumbent_model"))
        baseline = clean(group.get("baseline_model"))
        candidate_metrics: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
        for candidate in frozen_by_group.get(challenge_group, []):
            model = clean(candidate.get("model_name"))
            rows = candidate_error_rows.get((challenge_group, model), [])
            latest_count = max(int(math.ceil(len(rows) * float(stress_config["latest_time_fraction"]))), 1)
            latest_rows = sorted(rows, key=lambda row: (row["target_date"], row["product_id"]), reverse=True)[:latest_count]
            product_totals: dict[str, float] = defaultdict(float)
            for row in rows:
                product_totals[row["product_id"]] += abs(row["signed_error"])
            stressed_products = {product for product, _ in sorted(product_totals.items(), key=lambda item: (-item[1], item[0]))[: max(1, min(3, len(product_totals)))]}
            concentration_rows = [row for row in rows if row["product_id"] in stressed_products]
            partitions_to_rows = {
                "OUTER_ALL": rows,
                "LATEST_TIME_STRESS": latest_rows,
                "PRODUCT_CONCENTRATION_STRESS": concentration_rows,
            }
            for partition_name, partition_rows in partitions_to_rows.items():
                metric = metrics(partition_rows)
                candidate_metrics[model][partition_name] = metric
                score_rows.append({
                    "challenge_group_id": challenge_group,
                    "horizon_code": group.get("horizon_code"),
                    "forecast_method": group.get("forecast_method"),
                    "model_name": model,
                    "candidate_role": candidate.get("candidate_role"),
                    "source_candidate_id": candidate.get("source_candidate_id"),
                    "partition_name": partition_name,
                    **metric,
                    "partition_controls_passed": passes_controls(metric, stress_config),
                    "candidate_set_frozen": True,
                    "new_tuning_performed": False,
                })
        passes_by_model = {
            model: all(passes_controls(metrics_by_partition.get(name, {}), stress_config) for name in ("OUTER_ALL", "LATEST_TIME_STRESS", "PRODUCT_CONCENTRATION_STRESS"))
            for model, metrics_by_partition in candidate_metrics.items()
        }
        incumbent_outer = candidate_metrics.get(incumbent, {}).get("OUTER_ALL", {})
        baseline_outer = candidate_metrics.get(baseline, {}).get("OUTER_ALL", {})
        challengers = [
            clean(row.get("model_name"))
            for row in frozen_by_group.get(challenge_group, [])
            if clean(row.get("candidate_role")) == "FROZEN_ROUND_TWO_CHALLENGER"
        ]
        eligible_challengers = []
        for model in challengers:
            outer = candidate_metrics.get(model, {}).get("OUTER_ALL", {})
            if not outer or not incumbent_outer or not passes_by_model.get(model, False):
                continue
            improvement = (incumbent_outer["median_ape"] - outer["median_ape"]) / max(incumbent_outer["median_ape"], 1e-9)
            if improvement >= float(stress_config["minimum_relative_improvement_for_challenger_promotion"]):
                eligible_challengers.append((outer["median_ape"], model, improvement))
        if eligible_challengers:
            eligible_challengers.sort()
            _, selected_model, improvement = eligible_challengers[0]
            decision = "PROMOTE_FROZEN_ROUND_TWO_CHALLENGER"
        elif passes_by_model.get(incumbent, False):
            selected_model = incumbent
            improvement = 0.0
            decision = "RETAIN_ROUND_ONE_INCUMBENT"
        elif passes_by_model.get(baseline, False):
            selected_model = baseline
            improvement = 0.0
            decision = "RETAIN_GOVERNED_BASELINE"
        else:
            selected_model = ""
            improvement = 0.0
            decision = "GOVERNED_NO_PRODUCTION_CHAMPION"
        decisions.append({
            "challenge_group_id": challenge_group,
            "horizon_code": group.get("horizon_code"),
            "forecast_method": group.get("forecast_method"),
            "incumbent_model": incumbent,
            "baseline_model": baseline,
            "selected_model": selected_model,
            "final_challenge_decision": decision,
            "relative_improvement_over_incumbent": improvement,
            "all_required_stress_partitions_evaluated": True,
            "candidate_set_frozen": True,
            "new_tuning_performed": False,
            "winner_and_uncertainty_certification_authorized": decision != "GOVERNED_NO_PRODUCTION_CHAMPION",
            "forecast_generation_authorized": False,
        })
        if selected_model:
            outer = candidate_metrics[selected_model]["OUTER_ALL"]
            winners.append({
                "horizon_code": group.get("horizon_code"),
                "forecast_method": group.get("forecast_method"),
                "certified_challenge_model": selected_model,
                "challenge_decision": decision,
                "outer_all_rows": outer["rows"],
                "outer_all_median_ape": outer["median_ape"],
                "outer_all_directional_accuracy": outer["directional_accuracy"],
                "outer_all_bias": outer["bias"],
                "final_winner_certification_authorized": False,
                "forecast_generation_authorized": False,
            })

    no_champion = sum(row["final_challenge_decision"] == "GOVERNED_NO_PRODUCTION_CHAMPION" for row in decisions)
    if len(decisions) != expected["short_horizon_challenge_groups"]:
        failures.append("FINAL_GROUP_DECISION_COUNT_DRIFT")
    if len(long_routes) != expected["long_horizon_monte_carlo_routes"]:
        failures.append("LONG_HORIZON_ROUTE_COUNT_DRIFT")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    lineage = lineage1 + lineage2 + authority_lineage + [history_lineage]
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, ["artifact_role", "package_name", "package_sha256", "member_name", "member_sha256", "row_count"])
    write_csv(OUTPUT_DIR / outputs["candidate_partition_scorecard_csv"], score_rows, list(score_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["final_group_decisions_csv"], decisions, list(decisions[0].keys()))
    write_csv(OUTPUT_DIR / outputs["certified_short_horizon_winners_csv"], winners, list(winners[0].keys()) if winners else ["horizon_code", "forecast_method", "certified_challenge_model", "challenge_decision", "outer_all_rows", "outer_all_median_ape", "outer_all_directional_accuracy", "outer_all_bias", "final_winner_certification_authorized", "forecast_generation_authorized"])
    write_csv(OUTPUT_DIR / outputs["long_horizon_routing_csv"], long_routes, list(long_routes[0].keys()))
    diagnostics = [{"severity": "BLOCKING", "code": failure, "detail": ""} for failure in failures]
    write_csv(OUTPUT_DIR / outputs["diagnostics_csv"], diagnostics, ["severity", "code", "detail"])

    status = "PASS" if not failures else "FAIL"
    summary = {
        "certification_status": status,
        "short_horizon_challenge_groups": len(groups),
        "frozen_candidate_rows": len(frozen),
        "candidate_partition_scorecard_rows": len(score_rows),
        "final_group_decision_rows": len(decisions),
        "short_horizon_challenge_winner_rows": len(winners),
        "retained_round_one_incumbent_rows": sum(row["final_challenge_decision"] == "RETAIN_ROUND_ONE_INCUMBENT" for row in decisions),
        "promoted_frozen_round_two_challenger_rows": sum(row["final_challenge_decision"] == "PROMOTE_FROZEN_ROUND_TWO_CHALLENGER" for row in decisions),
        "retained_governed_baseline_rows": sum(row["final_challenge_decision"] == "RETAIN_GOVERNED_BASELINE" for row in decisions),
        "governed_no_production_champion_rows": no_champion,
        "long_horizon_monte_carlo_routes": len(long_routes),
        "long_horizon_monte_carlo_required": True,
        "required_simulations_per_product_horizon": contract["long_horizon_routing"]["required_simulations_per_product_horizon"],
        "candidate_set_frozen": True,
        "new_tuning_performed": False,
        "preserved_fold_membership_changed": False,
        "recursive_upstream_rebuild_performed": False,
        "live_network_collection_performed": False,
        "blocking_diagnostic_rows": len(failures),
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_EXECUTION",
        "final_winner_certification_authorized": False,
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "uip_delivery_authorized": False,
    }
    summary_path = OUTPUT_DIR / outputs["summary_json"]
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "outputs": [
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUTPUT_DIR.iterdir())
            if path.is_file() and path.name != outputs["manifest_json"]
        ],
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_EXECUTION" if not failures else "FAIL_PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_EXECUTION")
    print(f"SHORT_HORIZON_CHALLENGE_GROUPS={len(groups)}")
    print(f"FROZEN_CANDIDATE_ROWS={len(frozen)}")
    print(f"CANDIDATE_PARTITION_SCORECARD_ROWS={len(score_rows)}")
    print(f"FINAL_GROUP_DECISION_ROWS={len(decisions)}")
    print(f"SHORT_HORIZON_CHALLENGE_WINNER_ROWS={len(winners)}")
    print(f"RETAINED_ROUND_ONE_INCUMBENT_ROWS={summary['retained_round_one_incumbent_rows']}")
    print(f"PROMOTED_FROZEN_ROUND_TWO_CHALLENGER_ROWS={summary['promoted_frozen_round_two_challenger_rows']}")
    print(f"RETAINED_GOVERNED_BASELINE_ROWS={summary['retained_governed_baseline_rows']}")
    print(f"GOVERNED_NO_PRODUCTION_CHAMPION_ROWS={no_champion}")
    print(f"LONG_HORIZON_MONTE_CARLO_ROUTES={len(long_routes)}")
    print("LONG_HORIZON_MONTE_CARLO_REQUIRED=TRUE")
    print("CANDIDATE_SET_FROZEN=TRUE")
    print("NEW_TUNING_PERFORMED=FALSE")
    print("PRESERVED_FOLD_MEMBERSHIP_CHANGED=FALSE")
    print(f"NEXT_STAGE={summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
