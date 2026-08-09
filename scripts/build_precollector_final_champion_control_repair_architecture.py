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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_final_champion_control_repair_architecture_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/final_champion_control_repair_architecture"


def clean(value: Any) -> str:
    return str(value or "").strip()


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
    package = contract["required_final_challenge_package"]
    path = Path(tempfile.gettempdir()) / package["package_name"]
    if not path.is_file():
        raise RuntimeError(f"FINAL_CHALLENGE_PACKAGE_MISSING:{path}")
    actual = sha256_file(path)
    if actual != package["sha256"]:
        raise RuntimeError(
            f"FINAL_CHALLENGE_PACKAGE_HASH_DRIFT:expected={package['sha256']}:actual={actual}"
        )
    required = [
        "precollector_final_champion_candidate_partition_scorecard.csv",
        "precollector_final_champion_group_decisions.csv",
        "precollector_certified_short_horizon_winner_registry.csv",
        "precollector_final_champion_long_horizon_routing.csv",
        "precollector_final_champion_execution_summary.json",
    ]
    payloads: dict[str, bytes] = {}
    lineage: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        available = {Path(item.filename).name: item for item in archive.infolist() if not item.is_dir()}
        for name in required:
            member = available.get(name)
            if member is None:
                raise RuntimeError(f"FINAL_CHALLENGE_MEMBER_MISSING:{name}")
            payload = archive.read(member)
            payloads[name] = payload
            lineage.append({
                "artifact_role": "CERTIFIED_FINAL_CHALLENGE_V1_INPUT",
                "package_name": path.name,
                "package_sha256": actual,
                "member_name": name,
                "member_sha256": sha256_bytes(payload),
                "row_count": len(read_csv_bytes(payload)) if name.endswith(".csv") else "",
            })
    return payloads, lineage


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payloads, lineage = load_package(contract)
    scores = read_csv_bytes(payloads["precollector_final_champion_candidate_partition_scorecard.csv"])
    decisions = read_csv_bytes(payloads["precollector_final_champion_group_decisions.csv"])
    winners = read_csv_bytes(payloads["precollector_certified_short_horizon_winner_registry.csv"])
    long_routes = read_csv_bytes(payloads["precollector_final_champion_long_horizon_routing.csv"])
    summary = json.loads(payloads["precollector_final_champion_execution_summary.json"].decode("utf-8-sig"))

    failures: list[str] = []
    expected = contract["expected_counts"]
    observed = {
        "short_horizon_challenge_groups": int(summary.get("short_horizon_challenge_groups", -1)),
        "candidate_partition_scorecard_rows": len(scores),
        "final_group_decision_rows": len(decisions),
        "long_horizon_monte_carlo_routes": len(long_routes),
    }
    frozen_candidates = {(clean(r.get("challenge_group_id")), clean(r.get("model_name"))) for r in scores}
    observed["frozen_candidate_rows"] = len(frozen_candidates)
    for key, value in expected.items():
        if observed.get(key) != value:
            failures.append(f"COUNT_DRIFT:{key}:expected={value}:actual={observed.get(key)}")
    if winners:
        failures.append("V1_WINNER_REGISTRY_EXPECTED_EMPTY")
    if any(clean(r.get("final_challenge_decision")) != "GOVERNED_NO_PRODUCTION_CHAMPION" for r in decisions):
        failures.append("V1_DECISION_SET_NOT_UNIVERSAL_NO_CHAMPION")

    supersession_rows = []
    for row in decisions:
        supersession_rows.append({
            "challenge_group_id": clean(row.get("challenge_group_id")),
            "horizon_code": clean(row.get("horizon_code")),
            "forecast_method": clean(row.get("forecast_method")),
            "v1_final_challenge_decision": clean(row.get("final_challenge_decision")),
            "v1_selected_model": clean(row.get("selected_model")),
            "supersession_status": contract["superseded_decision_status"],
            "supersession_reason": "BIAS_RATIO_AND_RECURSIVE_STRESS_CONTROL_DESIGN_REQUIRES_REPAIR",
            "v1_package_retained": True,
            "winner_certification_authorized": False,
        })

    policy_rows: list[dict[str, Any]] = []
    design = contract["repaired_control_design"]
    for partition_name in ("outer_all", "latest_time_stress", "product_concentration_stress"):
        policy = design[partition_name]
        for key, value in policy.items():
            policy_rows.append({
                "partition_name": partition_name.upper(),
                "control_name": key,
                "control_value": value,
                "control_class": "PRIMARY_ELIGIBILITY" if partition_name == "outer_all" else "ROBUSTNESS",
                "hard_rejection_authorized": partition_name == "outer_all" or key not in {
                    "hard_bias_rejection_authorized",
                    "recursive_concentration_rejection_authorized",
                    "recursive_worst_product_rejection_authorized",
                },
            })
    for key, value in design["challenger_promotion"].items():
        policy_rows.append({
            "partition_name": "CHALLENGER_PROMOTION",
            "control_name": key,
            "control_value": value,
            "control_class": "PROMOTION",
            "hard_rejection_authorized": True,
        })

    immutability_rows = [
        {"evidence_component": "FROZEN_CANDIDATE_SET", "expected_rows": len(frozen_candidates), "observed_rows": len(frozen_candidates), "immutable": True, "recomputation_authorized": False},
        {"evidence_component": "CANDIDATE_PARTITION_SCORECARD", "expected_rows": len(scores), "observed_rows": len(scores), "immutable": True, "recomputation_authorized": False},
        {"evidence_component": "FINAL_GROUP_DECISIONS_V1", "expected_rows": len(decisions), "observed_rows": len(decisions), "immutable": True, "recomputation_authorized": False},
        {"evidence_component": "LONG_HORIZON_MONTE_CARLO_ROUTES", "expected_rows": len(long_routes), "observed_rows": len(long_routes), "immutable": True, "recomputation_authorized": False},
    ]

    execution_rows = []
    for row in decisions:
        execution_rows.append({
            "challenge_group_id": clean(row.get("challenge_group_id")),
            "source_scorecard": "CERTIFIED_FINAL_CHALLENGE_V1_PARTITION_SCORECARD",
            "recompute_predictions": False,
            "recompute_errors": False,
            "recalculate_controls_only": True,
            "primary_partition": "OUTER_ALL",
            "robustness_partitions": "LATEST_TIME_STRESS|PRODUCT_CONCENTRATION_STRESS",
            "new_tuning_authorized": False,
            "next_execution_stage": contract["next_stage_if_certified"],
        })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["required_outputs"]
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    write_csv(OUTPUT_DIR / outputs["supersession_registry_csv"], supersession_rows, list(supersession_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["repaired_control_policy_csv"], policy_rows, list(policy_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["evidence_immutability_registry_csv"], immutability_rows, list(immutability_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["execution_plan_csv"], execution_rows, list(execution_rows[0].keys()))

    status = "PASS" if not failures else "FAIL"
    architecture_summary = {
        "certification_status": status,
        "short_horizon_challenge_groups": len(decisions),
        "frozen_candidate_rows": len(frozen_candidates),
        "candidate_partition_scorecard_rows": len(scores),
        "superseded_v1_decision_rows": len(supersession_rows),
        "repaired_control_policy_rows": len(policy_rows),
        "evidence_immutability_rows": len(immutability_rows),
        "execution_plan_rows": len(execution_rows),
        "long_horizon_monte_carlo_routes": len(long_routes),
        "prediction_recomputation_authorized": False,
        "error_recomputation_authorized": False,
        "candidate_set_changed": False,
        "fold_membership_changed": False,
        "new_tuning_authorized": False,
        "v1_decisions_superseded_not_deleted": True,
        "critical_failures": failures,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_FINAL_CHAMPION_CONTROL_REPAIR_ARCHITECTURE",
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

    print("PASS_PRECOLLECTOR_FINAL_CHAMPION_CONTROL_REPAIR_ARCHITECTURE" if not failures else "FAIL_PRECOLLECTOR_FINAL_CHAMPION_CONTROL_REPAIR_ARCHITECTURE")
    print(f"SHORT_HORIZON_CHALLENGE_GROUPS={len(decisions)}")
    print(f"FROZEN_CANDIDATE_ROWS={len(frozen_candidates)}")
    print(f"PRESERVED_SCORECARD_ROWS={len(scores)}")
    print(f"SUPERSEDED_V1_DECISION_ROWS={len(supersession_rows)}")
    print(f"LONG_HORIZON_MONTE_CARLO_ROUTES={len(long_routes)}")
    print("PREDICTION_RECOMPUTATION_AUTHORIZED=FALSE")
    print("ERROR_RECOMPUTATION_AUTHORIZED=FALSE")
    print("NEW_TUNING_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={architecture_summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
