from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_final_champion_control_repair_execution_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/final_champion_control_repair_execution"


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


def load_zip(package: dict[str, str], required: list[str], role: str) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
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


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    architecture_required = [
        "precollector_final_champion_control_repair_supersession_registry.csv",
        "precollector_final_champion_repaired_control_policy.csv",
        "precollector_final_champion_evidence_immutability_registry.csv",
        "precollector_final_champion_control_repair_execution_plan.csv",
        "precollector_final_champion_control_repair_architecture_summary.json",
    ]
    final_required = [
        "precollector_final_champion_candidate_partition_scorecard.csv",
        "precollector_final_champion_group_decisions.csv",
        "precollector_final_champion_long_horizon_routing.csv",
        "precollector_final_champion_execution_summary.json",
    ]
    architecture, lineage_a = load_zip(contract["required_repair_architecture_package"], architecture_required, "CERTIFIED_CONTROL_REPAIR_ARCHITECTURE")
    final, lineage_f = load_zip(contract["required_final_challenge_package"], final_required, "CERTIFIED_FINAL_CHALLENGE_V1")

    scores = read_csv_bytes(final["precollector_final_champion_candidate_partition_scorecard.csv"])
    v1_decisions = read_csv_bytes(final["precollector_final_champion_group_decisions.csv"])
    long_routes = read_csv_bytes(final["precollector_final_champion_long_horizon_routing.csv"])
    supersession = read_csv_bytes(architecture["precollector_final_champion_control_repair_supersession_registry.csv"])

    failures: list[str] = []
    expected = contract["expected_counts"]
    frozen_candidates = {(clean(r.get("challenge_group_id")), clean(r.get("model_name"))) for r in scores}
    observed = {
        "short_horizon_challenge_groups": len(v1_decisions),
        "frozen_candidate_rows": len(frozen_candidates),
        "preserved_candidate_partition_scorecard_rows": len(scores),
        "superseded_v1_decision_rows": len(supersession),
        "long_horizon_monte_carlo_routes": len(long_routes),
    }
    for key, value in expected.items():
        if observed.get(key) != value:
            failures.append(f"COUNT_DRIFT:{key}:expected={value}:actual={observed.get(key)}")

    scores_by_candidate: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    role_by_candidate: dict[tuple[str, str], str] = {}
    for row in scores:
        key = (clean(row.get("challenge_group_id")), clean(row.get("model_name")))
        scores_by_candidate[key][clean(row.get("partition_name"))] = row
        role_by_candidate[key] = clean(row.get("candidate_role"))

    controls = contract["repaired_controls"]
    assessments: list[dict[str, Any]] = []
    candidate_pass: dict[tuple[str, str], bool] = {}
    outer_mape: dict[tuple[str, str], float] = {}

    for key, partitions in sorted(scores_by_candidate.items()):
        group, model = key
        outer = partitions.get("OUTER_ALL", {})
        latest = partitions.get("LATEST_TIME_STRESS", {})
        concentration = partitions.get("PRODUCT_CONCENTRATION_STRESS", {})
        outer_rows = int(number(outer.get("rows")))
        outer_dir = number(outer.get("directional_accuracy"))
        outer_share = number(outer.get("single_product_error_share"))
        outer_worst = number(outer.get("worst_product_mape_multiple"))
        outer_median = number(outer.get("median_ape"))
        latest_rows = int(number(latest.get("rows")))
        latest_median = number(latest.get("median_ape"))
        latest_dir = number(latest.get("directional_accuracy"))
        concentration_rows = int(number(concentration.get("rows")))
        concentration_median = number(concentration.get("median_ape"))
        concentration_dir = number(concentration.get("directional_accuracy"))

        outer_pass = (
            outer_rows >= controls["outer_all"]["minimum_rows"]
            and outer_dir >= controls["outer_all"]["minimum_directional_accuracy"]
            and outer_share <= controls["outer_all"]["maximum_single_product_error_share"]
            and outer_worst <= controls["outer_all"]["maximum_worst_product_mape_multiple"]
        )
        latest_pass = (
            latest_rows >= controls["latest_time_stress"]["minimum_rows"]
            and latest_median <= outer_median * controls["latest_time_stress"]["maximum_median_ape_deterioration_multiple"]
            and (outer_dir - latest_dir) <= controls["latest_time_stress"]["maximum_directional_accuracy_decline"]
        )
        concentration_pass = (
            concentration_rows >= controls["product_concentration_stress"]["minimum_rows"]
            and concentration_median <= outer_median * controls["product_concentration_stress"]["maximum_median_ape_deterioration_multiple"]
            and concentration_dir >= controls["product_concentration_stress"]["minimum_directional_accuracy"]
        )
        all_pass = outer_pass and latest_pass and concentration_pass
        candidate_pass[key] = all_pass
        outer_mape[key] = outer_median
        assessments.append({
            "challenge_group_id": group,
            "model_name": model,
            "candidate_role": role_by_candidate[key],
            "outer_all_rows": outer_rows,
            "outer_all_median_ape": outer_median,
            "outer_all_directional_accuracy": outer_dir,
            "outer_all_single_product_error_share": outer_share,
            "outer_all_worst_product_mape_multiple": outer_worst,
            "outer_all_controls_passed": outer_pass,
            "latest_time_rows": latest_rows,
            "latest_time_median_ape": latest_median,
            "latest_time_directional_accuracy": latest_dir,
            "latest_time_controls_passed": latest_pass,
            "product_concentration_rows": concentration_rows,
            "product_concentration_median_ape": concentration_median,
            "product_concentration_directional_accuracy": concentration_dir,
            "product_concentration_controls_passed": concentration_pass,
            "mean_signed_percentage_error_status": contract["evidence_limitation"]["required_disposition"],
            "all_repaired_controls_passed": all_pass,
            "prediction_recomputed": False,
            "error_recomputed": False,
            "new_tuning_performed": False,
        })

    decisions: list[dict[str, Any]] = []
    winners: list[dict[str, Any]] = []
    minimum_improvement = controls["challenger_promotion"]["minimum_relative_outer_all_median_ape_improvement"]
    for row in v1_decisions:
        group = clean(row.get("challenge_group_id"))
        incumbent = clean(row.get("incumbent_model"))
        baseline = clean(row.get("baseline_model"))
        incumbent_key = (group, incumbent)
        incumbent_mape = outer_mape.get(incumbent_key, 0.0)
        challengers: list[tuple[float, str, float]] = []
        for (candidate_group, model), passed in candidate_pass.items():
            if candidate_group != group or not passed or role_by_candidate[(candidate_group, model)] != "FROZEN_ROUND_TWO_CHALLENGER":
                continue
            improvement = (incumbent_mape - outer_mape[(candidate_group, model)]) / max(incumbent_mape, 1e-9)
            if improvement >= minimum_improvement:
                challengers.append((outer_mape[(candidate_group, model)], model, improvement))
        if challengers:
            challengers.sort()
            _, selected, improvement = challengers[0]
            decision = "PROMOTE_FROZEN_ROUND_TWO_CHALLENGER"
        elif candidate_pass.get(incumbent_key, False):
            selected, improvement, decision = incumbent, 0.0, "RETAIN_ROUND_ONE_INCUMBENT"
        elif candidate_pass.get((group, baseline), False):
            selected, improvement, decision = baseline, 0.0, "RETAIN_GOVERNED_BASELINE"
        else:
            selected, improvement, decision = "", 0.0, "GOVERNED_NO_PRODUCTION_CHAMPION"
        decisions.append({
            "challenge_group_id": group,
            "horizon_code": clean(row.get("horizon_code")),
            "forecast_method": clean(row.get("forecast_method")),
            "incumbent_model": incumbent,
            "baseline_model": baseline,
            "selected_model": selected,
            "repaired_final_challenge_decision": decision,
            "relative_outer_all_median_ape_improvement": improvement,
            "v1_decision_superseded": True,
            "mean_signed_percentage_error_status": contract["evidence_limitation"]["required_disposition"],
            "winner_and_uncertainty_certification_authorized": bool(selected),
            "forecast_generation_authorized": False,
        })
        if selected:
            winners.append({
                "challenge_group_id": group,
                "horizon_code": clean(row.get("horizon_code")),
                "forecast_method": clean(row.get("forecast_method")),
                "repaired_challenge_model": selected,
                "repaired_challenge_decision": decision,
                "outer_all_median_ape": outer_mape[(group, selected)],
                "winner_and_uncertainty_certification_authorized": True,
                "forecast_generation_authorized": False,
            })

    limitation_rows = [{
        "metric": contract["evidence_limitation"]["missing_metric"],
        "status": contract["evidence_limitation"]["required_disposition"],
        "reason": contract["evidence_limitation"]["reason"],
        "hard_rejection_authorized": False,
        "prediction_recomputation_authorized": False,
        "error_recomputation_authorized": False,
    }]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    lineage = lineage_a + lineage_f
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    write_csv(OUTPUT_DIR / outputs["preserved_scorecard_csv"], scores, list(scores[0].keys()))
    write_csv(OUTPUT_DIR / outputs["repaired_candidate_assessment_csv"], assessments, list(assessments[0].keys()))
    write_csv(OUTPUT_DIR / outputs["repaired_group_decisions_csv"], decisions, list(decisions[0].keys()))
    winner_fields = ["challenge_group_id", "horizon_code", "forecast_method", "repaired_challenge_model", "repaired_challenge_decision", "outer_all_median_ape", "winner_and_uncertainty_certification_authorized", "forecast_generation_authorized"]
    write_csv(OUTPUT_DIR / outputs["repaired_short_horizon_winners_csv"], winners, winner_fields)
    write_csv(OUTPUT_DIR / outputs["long_horizon_routing_csv"], long_routes, list(long_routes[0].keys()))
    write_csv(OUTPUT_DIR / outputs["evidence_limitations_csv"], limitation_rows, list(limitation_rows[0].keys()))
    diagnostics = [{"severity": "BLOCKING", "code": failure, "detail": ""} for failure in failures]
    write_csv(OUTPUT_DIR / outputs["diagnostics_csv"], diagnostics, ["severity", "code", "detail"])

    no_champion = sum(r["repaired_final_challenge_decision"] == "GOVERNED_NO_PRODUCTION_CHAMPION" for r in decisions)
    summary = {
        "certification_status": "PASS" if not failures else "FAIL",
        "short_horizon_challenge_groups": len(decisions),
        "frozen_candidate_rows": len(frozen_candidates),
        "preserved_candidate_partition_scorecard_rows": len(scores),
        "repaired_candidate_assessment_rows": len(assessments),
        "repaired_group_decision_rows": len(decisions),
        "repaired_short_horizon_winner_rows": len(winners),
        "governed_no_production_champion_rows": no_champion,
        "long_horizon_monte_carlo_routes": len(long_routes),
        "mean_signed_percentage_error_status": contract["evidence_limitation"]["required_disposition"],
        "candidate_set_changed": False,
        "fold_membership_changed": False,
        "prediction_recomputed": False,
        "error_recomputed": False,
        "new_tuning_performed": False,
        "v1_decisions_superseded_not_deleted": True,
        "blocking_diagnostic_rows": len(failures),
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_FINAL_CHAMPION_CONTROL_REPAIR_EXECUTION",
        "final_winner_certification_authorized": False,
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "uip_delivery_authorized": False,
    }
    (OUTPUT_DIR / outputs["summary_json"]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "outputs": [
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUTPUT_DIR.iterdir())
            if path.is_file() and path.name != outputs["manifest_json"]
        ],
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_FINAL_CHAMPION_CONTROL_REPAIR_EXECUTION" if not failures else "FAIL_PRECOLLECTOR_FINAL_CHAMPION_CONTROL_REPAIR_EXECUTION")
    print(f"SHORT_HORIZON_CHALLENGE_GROUPS={len(decisions)}")
    print(f"FROZEN_CANDIDATE_ROWS={len(frozen_candidates)}")
    print(f"PRESERVED_SCORECARD_ROWS={len(scores)}")
    print(f"REPAIRED_SHORT_HORIZON_WINNER_ROWS={len(winners)}")
    print(f"GOVERNED_NO_PRODUCTION_CHAMPION_ROWS={no_champion}")
    print("PREDICTION_RECOMPUTED=FALSE")
    print("ERROR_RECOMPUTED=FALSE")
    print("NEW_TUNING_PERFORMED=FALSE")
    print("MEAN_SIGNED_PERCENTAGE_ERROR_STATUS=NOT_EVALUABLE_FROM_PRESERVED_SCORECARD")
    print(f"NEXT_STAGE={summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
