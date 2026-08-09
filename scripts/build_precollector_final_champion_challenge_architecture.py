from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_final_champion_challenge_architecture_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/final_champion_challenge_architecture"


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float:
    try:
        return float(clean(value))
    except (TypeError, ValueError):
        return 0.0


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


def load_package(contract: dict) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    package = contract["required_round_two_package"]
    path = Path(tempfile.gettempdir()) / package["package_name"]
    if not path.is_file():
        raise RuntimeError(f"ROUND_TWO_PACKAGE_MISSING:{path}")
    actual_hash = sha256_file(path)
    if actual_hash != package["sha256"]:
        raise RuntimeError(
            f"ROUND_TWO_PACKAGE_HASH_DRIFT:expected={package['sha256']}:actual={actual_hash}"
        )
    required = [
        "precollector_round_two_candidate_scorecard.csv",
        "precollector_round_two_preliminary_group_decisions.csv",
        "precollector_round_two_fold_assignment.csv",
        "precollector_round_two_execution_summary.json",
    ]
    payloads: dict[str, bytes] = {}
    lineage: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        available = {Path(item.filename).name: item for item in archive.infolist() if not item.is_dir()}
        for name in required:
            member = available.get(name)
            if member is None:
                raise RuntimeError(f"ROUND_TWO_MEMBER_MISSING:{name}")
            payload = archive.read(member)
            payloads[name] = payload
            lineage.append({
                "artifact_role": "CERTIFIED_ROUND_TWO_INPUT",
                "package_name": path.name,
                "package_sha256": actual_hash,
                "member_name": name,
                "member_sha256": sha256_bytes(payload),
                "row_count": len(read_csv_bytes(payload)) if name.endswith(".csv") else "",
            })
    return payloads, lineage


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payloads, lineage = load_package(contract)
    summary = json.loads(payloads["precollector_round_two_execution_summary.json"].decode("utf-8-sig"))
    decisions = read_csv_bytes(payloads["precollector_round_two_preliminary_group_decisions.csv"])
    scores = read_csv_bytes(payloads["precollector_round_two_candidate_scorecard.csv"])
    folds = read_csv_bytes(payloads["precollector_round_two_fold_assignment.csv"])

    failures: list[str] = []
    expected = contract["expected_round_two_counts"]
    observed = {
        "groups": len(decisions),
        "candidate_scorecards": len(scores),
        "preserved_folds": len(folds),
        "round_one_leaders_retained": int(summary.get("round_one_leader_retained_rows", -1)),
        "long_horizon_insufficient_evidence": int(summary.get("long_horizon_insufficient_evidence_rows", -1)),
    }
    for key, value in expected.items():
        if key in observed and observed[key] != value:
            failures.append(f"ROUND_TWO_COUNT_DRIFT:{key}:expected={value}:actual={observed[key]}")

    short_horizons = set(contract["short_horizons"])
    long_horizons = set(contract["long_horizons"])
    short_decisions = [row for row in decisions if clean(row.get("horizon_code")) in short_horizons]
    long_decisions = [row for row in decisions if clean(row.get("horizon_code")) in long_horizons]
    if len(short_decisions) != expected["short_horizon_groups"]:
        failures.append("SHORT_HORIZON_GROUP_COUNT_DRIFT")
    if len(long_decisions) != expected["long_horizon_groups"]:
        failures.append("LONG_HORIZON_GROUP_COUNT_DRIFT")

    scores_by_group: dict[str, list[dict[str, str]]] = {}
    for row in scores:
        scores_by_group.setdefault(clean(row.get("refinement_group_id")), []).append(row)

    group_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    partition_rows: list[dict[str, Any]] = []
    long_rows: list[dict[str, Any]] = []
    policy_rows: list[dict[str, Any]] = []

    max_challengers = int(contract["challenge_design"]["maximum_non_incumbent_challengers"])
    for decision in short_decisions:
        group_id = clean(decision.get("refinement_group_id"))
        horizon = clean(decision.get("horizon_code"))
        route = clean(decision.get("forecast_method"))
        incumbent = clean(decision.get("round_one_model"))
        baseline = contract["baseline_models"].get(route, "")
        if not incumbent:
            failures.append(f"SHORT_HORIZON_INCUMBENT_MISSING:{group_id}")
        rows = scores_by_group.get(group_id, [])
        eligible = [row for row in rows if int(number(row.get("champion_rows"))) >= contract["challenge_design"]["minimum_champion_rows"]]
        eligible.sort(key=lambda row: (number(row.get("champion_median_ape")), clean(row.get("candidate_id"))))
        challengers: list[dict[str, str]] = []
        seen_models: set[str] = {incumbent, baseline}
        for row in eligible:
            model = clean(row.get("model_name"))
            if model and model not in seen_models:
                challengers.append(row)
                seen_models.add(model)
            if len(challengers) >= max_challengers:
                break
        frozen_models = [incumbent]
        if baseline and baseline not in frozen_models:
            frozen_models.append(baseline)
        frozen_models.extend(clean(row.get("model_name")) for row in challengers)
        frozen_models = list(dict.fromkeys(model for model in frozen_models if model))
        group_rows.append({
            "challenge_group_id": group_id.replace("R2-", "R3-", 1),
            "source_refinement_group_id": group_id,
            "horizon_code": horizon,
            "forecast_method": route,
            "incumbent_model": incumbent,
            "baseline_model": baseline,
            "non_incumbent_challenger_count": len(challengers),
            "frozen_candidate_count": len(frozen_models),
            "challenge_execution_authorized": True,
            "final_winner_certification_authorized": False,
        })
        for rank, model in enumerate(frozen_models, start=1):
            source = "ROUND_ONE_INCUMBENT" if model == incumbent else ("GOVERNED_BASELINE" if model == baseline else "FROZEN_ROUND_TWO_CHALLENGER")
            matching = [row for row in eligible if clean(row.get("model_name")) == model]
            best = matching[0] if matching else {}
            candidate_rows.append({
                "challenge_group_id": group_id.replace("R2-", "R3-", 1),
                "candidate_rank": rank,
                "model_name": model,
                "candidate_role": source,
                "source_candidate_id": clean(best.get("candidate_id")),
                "champion_rows": clean(best.get("champion_rows")),
                "champion_median_ape": clean(best.get("champion_median_ape")),
                "champion_directional_accuracy": clean(best.get("champion_directional_accuracy")),
                "champion_bias": clean(best.get("champion_bias")),
                "candidate_set_frozen": True,
                "new_tuning_authorized": False,
            })
        for partition in contract["challenge_design"]["stress_partitions"]:
            partition_rows.append({
                "challenge_group_id": group_id.replace("R2-", "R3-", 1),
                "partition_name": partition,
                "source_fold_registry": "CERTIFIED_ROUND_TWO_FOLD_ASSIGNMENT",
                "fold_membership_mutable": False,
                "new_partition_tuning_authorized": False,
            })

    for decision in long_decisions:
        long_rows.append({
            "refinement_group_id": clean(decision.get("refinement_group_id")),
            "horizon_code": clean(decision.get("horizon_code")),
            "horizon_days": 1095 if clean(decision.get("horizon_code")) == "Y3" else 1825,
            "forecast_method": clean(decision.get("forecast_method")),
            "fallback_model": clean(decision.get("round_one_model")),
            "direct_backtest_champion_authorized": False,
            "required_next_process": contract["long_horizon_routing"]["required_next_process"],
            "required_simulations_per_product_horizon": contract["long_horizon_routing"]["required_simulations_per_product_horizon"],
            "scenario_only_when_support_insufficient": True,
            "purchase_authorization": False,
        })

    for decision in contract["allowed_challenge_decisions"]:
        policy_rows.append({
            "allowed_decision": decision,
            "minimum_directional_accuracy": contract["challenge_design"]["minimum_directional_accuracy"],
            "maximum_absolute_bias_ratio": contract["challenge_design"]["maximum_absolute_bias_ratio"],
            "maximum_single_product_error_share": contract["challenge_design"]["maximum_single_product_error_share"],
            "maximum_worst_product_mape_multiple": contract["challenge_design"]["maximum_worst_product_mape_multiple"],
            "minimum_relative_improvement_for_challenger_promotion": contract["challenge_design"]["minimum_relative_improvement_for_challenger_promotion"],
            "no_forced_winner": True,
        })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    write_csv(OUTPUT_DIR / outputs["challenge_group_registry_csv"], group_rows, list(group_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["frozen_candidate_registry_csv"], candidate_rows, list(candidate_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["stress_partition_registry_csv"], partition_rows, list(partition_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["long_horizon_routing_csv"], long_rows, list(long_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["decision_policy_csv"], policy_rows, list(policy_rows[0].keys()))

    status = "PASS" if not failures else "FAIL"
    architecture_summary = {
        "certification_status": status,
        "short_horizon_challenge_groups": len(group_rows),
        "long_horizon_monte_carlo_routes": len(long_rows),
        "frozen_candidate_rows": len(candidate_rows),
        "stress_partition_rows": len(partition_rows),
        "decision_policy_rows": len(policy_rows),
        "round_two_package_sha256": contract["required_round_two_package"]["sha256"],
        "candidate_set_frozen_before_challenge": True,
        "new_parameter_tuning_authorized": False,
        "new_feature_tuning_authorized": False,
        "preserved_fold_membership_changed": False,
        "final_challenge_execution_performed": False,
        "recursive_upstream_rebuild_performed": False,
        "live_network_collection_performed": False,
        "long_horizon_monte_carlo_required": True,
        "required_simulations_per_product_horizon": 10000,
        "critical_failures": failures,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_ARCHITECTURE",
        "final_challenge_execution_authorized": not failures,
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
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "outputs": [
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUTPUT_DIR.iterdir())
            if path.is_file() and path.name != outputs["manifest_json"]
        ],
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_ARCHITECTURE" if not failures else "FAIL_PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_ARCHITECTURE")
    print(f"SHORT_HORIZON_CHALLENGE_GROUPS={len(group_rows)}")
    print(f"LONG_HORIZON_MONTE_CARLO_ROUTES={len(long_rows)}")
    print(f"FROZEN_CANDIDATE_ROWS={len(candidate_rows)}")
    print(f"STRESS_PARTITION_ROWS={len(partition_rows)}")
    print("FINAL_CHALLENGE_EXECUTION_PERFORMED=FALSE")
    print("LONG_HORIZON_MONTE_CARLO_REQUIRED=TRUE")
    print(f"NEXT_STAGE={architecture_summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
