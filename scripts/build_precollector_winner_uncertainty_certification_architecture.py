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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_winner_uncertainty_certification_architecture_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/winner_uncertainty_certification_architecture"


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
    package = contract["required_control_repair_execution_package"]
    path = Path(tempfile.gettempdir()) / package["package_name"]
    if not path.is_file():
        raise RuntimeError(f"PACKAGE_MISSING:{path}")
    actual = sha256_file(path)
    if actual != package["sha256"]:
        raise RuntimeError(f"PACKAGE_HASH_DRIFT:expected={package['sha256']}:actual={actual}")
    required = [
        "precollector_final_champion_preserved_candidate_partition_scorecard.csv",
        "precollector_final_champion_repaired_group_decisions.csv",
        "precollector_repaired_short_horizon_winner_registry.csv",
        "precollector_final_champion_control_repair_long_horizon_routing.csv",
        "precollector_final_champion_control_repair_execution_summary.json",
    ]
    payloads: dict[str, bytes] = {}
    lineage: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        available = {Path(item.filename).name: item for item in archive.infolist() if not item.is_dir()}
        for name in required:
            member = available.get(name)
            if member is None:
                raise RuntimeError(f"PACKAGE_MEMBER_MISSING:{name}")
            payload = archive.read(member)
            payloads[name] = payload
            lineage.append({
                "artifact_role": "CERTIFIED_CONTROL_REPAIR_EXECUTION_INPUT",
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
    scores = read_csv_bytes(payloads["precollector_final_champion_preserved_candidate_partition_scorecard.csv"])
    decisions = read_csv_bytes(payloads["precollector_final_champion_repaired_group_decisions.csv"])
    winners = read_csv_bytes(payloads["precollector_repaired_short_horizon_winner_registry.csv"])
    long_routes = read_csv_bytes(payloads["precollector_final_champion_control_repair_long_horizon_routing.csv"])
    summary = json.loads(payloads["precollector_final_champion_control_repair_execution_summary.json"].decode("utf-8-sig"))

    failures: list[str] = []
    expected = contract["expected_counts"]
    observed = {
        "short_horizon_groups": len(decisions),
        "certifiable_winner_groups": len(winners),
        "unresolved_no_champion_groups": sum(clean(r.get("repaired_final_decision")) == "GOVERNED_NO_PRODUCTION_CHAMPION" for r in decisions),
        "long_horizon_monte_carlo_routes": len(long_routes),
        "preserved_scorecard_rows": len(scores),
    }
    for key, value in expected.items():
        if observed.get(key) != value:
            failures.append(f"COUNT_DRIFT:{key}:expected={value}:actual={observed.get(key)}")

    winner_keys = {(clean(r.get("challenge_group_id")), clean(r.get("selected_model"))) for r in winners}
    if any(not group or not model for group, model in winner_keys):
        failures.append("WINNER_IDENTITY_INCOMPLETE")

    scope_rows: list[dict[str, Any]] = []
    for row in decisions:
        group = clean(row.get("challenge_group_id"))
        model = clean(row.get("selected_model"))
        certifiable = (group, model) in winner_keys
        scope_rows.append({
            "challenge_group_id": group,
            "horizon_code": clean(row.get("horizon_code")),
            "forecast_method": clean(row.get("forecast_method")),
            "selected_model": model,
            "repaired_final_decision": clean(row.get("repaired_final_decision")),
            "winner_certification_in_scope": certifiable,
            "uncertainty_certification_in_scope": certifiable,
            "model_selection_reopened": False,
            "forecast_generation_authorized": False,
        })

    policy_rows: list[dict[str, Any]] = []
    uncertainty = contract["uncertainty_design"]
    for classification in uncertainty["classifications"]:
        policy_rows.append({
            "uncertainty_classification": classification,
            "required_partitions": "|".join(uncertainty["required_partitions"]),
            "classification_inputs": "|".join(uncertainty["classification_inputs"]),
            "mean_signed_percentage_error_status": uncertainty["unavailable_metric_disposition"]["status"],
            "lower_uncertainty_allowed": classification != "LOWER_UNCERTAINTY" or False,
            "conservative_rule": uncertainty["conservative_rule"],
        })

    unresolved_rows = []
    for row in decisions:
        if clean(row.get("repaired_final_decision")) == "GOVERNED_NO_PRODUCTION_CHAMPION":
            unresolved_rows.append({
                "challenge_group_id": clean(row.get("challenge_group_id")),
                "horizon_code": clean(row.get("horizon_code")),
                "forecast_method": clean(row.get("forecast_method")),
                "resolution_status": "UNRESOLVED_NO_PRODUCTION_CHAMPION",
                "winner_certification_authorized": False,
                "forecast_generation_authorized": False,
                "forced_resolution_prohibited": True,
            })

    execution_rows = []
    scores_by_key = {(clean(r.get("challenge_group_id")), clean(r.get("model_name")), clean(r.get("partition_name"))): r for r in scores}
    for row in winners:
        group = clean(row.get("challenge_group_id"))
        model = clean(row.get("selected_model"))
        missing = [p for p in uncertainty["required_partitions"] if (group, model, p) not in scores_by_key]
        if missing:
            failures.append(f"WINNER_PARTITION_EVIDENCE_MISSING:{group}:{model}:{'|'.join(missing)}")
        execution_rows.append({
            "challenge_group_id": group,
            "horizon_code": clean(row.get("horizon_code")),
            "forecast_method": clean(row.get("forecast_method")),
            "selected_model": model,
            "source_decision": clean(row.get("repaired_final_decision")),
            "required_partition_count": len(uncertainty["required_partitions"]),
            "preserved_partition_evidence_only": True,
            "prediction_recomputation_authorized": False,
            "error_recomputation_authorized": False,
            "model_selection_reopened": False,
            "next_execution_stage": contract["next_stage_if_certified"],
        })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    write_csv(OUTPUT_DIR / outputs["certification_scope_registry_csv"], scope_rows, list(scope_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["uncertainty_policy_csv"], policy_rows, list(policy_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["unresolved_group_registry_csv"], unresolved_rows, list(unresolved_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["long_horizon_routing_csv"], long_routes, list(long_routes[0].keys()))
    write_csv(OUTPUT_DIR / outputs["execution_plan_csv"], execution_rows, list(execution_rows[0].keys()))

    status = "PASS" if not failures else "FAIL"
    architecture_summary = {
        "certification_status": status,
        "short_horizon_groups": len(decisions),
        "certifiable_winner_groups": len(winners),
        "unresolved_no_champion_groups": len(unresolved_rows),
        "long_horizon_monte_carlo_routes": len(long_routes),
        "preserved_scorecard_rows": len(scores),
        "winner_certification_execution_performed": False,
        "uncertainty_certification_execution_performed": False,
        "prediction_recomputation_authorized": False,
        "error_recomputation_authorized": False,
        "model_selection_reopened": False,
        "new_tuning_authorized": False,
        "lower_uncertainty_authorized": False,
        "mean_signed_percentage_error_status": uncertainty["unavailable_metric_disposition"]["status"],
        "critical_failures": failures,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_WINNER_UNCERTAINTY_ARCHITECTURE",
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

    print("PASS_PRECOLLECTOR_WINNER_UNCERTAINTY_CERTIFICATION_ARCHITECTURE" if not failures else "FAIL_PRECOLLECTOR_WINNER_UNCERTAINTY_CERTIFICATION_ARCHITECTURE")
    print(f"CERTIFIABLE_WINNER_GROUPS={len(winners)}")
    print(f"UNRESOLVED_NO_CHAMPION_GROUPS={len(unresolved_rows)}")
    print(f"LONG_HORIZON_MONTE_CARLO_ROUTES={len(long_routes)}")
    print("WINNER_CERTIFICATION_EXECUTION_PERFORMED=FALSE")
    print("UNCERTAINTY_CERTIFICATION_EXECUTION_PERFORMED=FALSE")
    print("LOWER_UNCERTAINTY_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={architecture_summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
