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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_winner_uncertainty_certification_execution_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/winner_uncertainty_certification_execution"


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


def load_package(package: dict[str, str], required: list[str], role: str) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
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
        "precollector_winner_uncertainty_certification_scope_registry.csv",
        "precollector_winner_uncertainty_unresolved_group_registry.csv",
        "precollector_winner_uncertainty_long_horizon_routing.csv",
        "precollector_winner_uncertainty_architecture_summary.json",
    ]
    repair_required = [
        "precollector_final_champion_preserved_candidate_partition_scorecard.csv",
        "precollector_final_champion_repaired_group_decisions.csv",
        "precollector_repaired_short_horizon_winner_registry.csv",
        "precollector_final_champion_control_repair_long_horizon_routing.csv",
        "precollector_final_champion_control_repair_execution_summary.json",
    ]
    architecture, lineage_a = load_package(contract["required_architecture_package"], architecture_required, "CERTIFIED_WINNER_UNCERTAINTY_ARCHITECTURE")
    repair, lineage_r = load_package(contract["required_repair_execution_package"], repair_required, "CERTIFIED_CONTROL_REPAIR_EXECUTION")

    scores = read_csv_bytes(repair["precollector_final_champion_preserved_candidate_partition_scorecard.csv"])
    decisions = read_csv_bytes(repair["precollector_final_champion_repaired_group_decisions.csv"])
    winners = read_csv_bytes(repair["precollector_repaired_short_horizon_winner_registry.csv"])
    unresolved = read_csv_bytes(architecture["precollector_winner_uncertainty_unresolved_group_registry.csv"])
    long_routes = read_csv_bytes(repair["precollector_final_champion_control_repair_long_horizon_routing.csv"])

    failures: list[str] = []
    expected = contract["expected_counts"]
    observed = {
        "short_horizon_groups": len(decisions),
        "certifiable_winner_groups": len(winners),
        "unresolved_no_champion_groups": len(unresolved),
        "long_horizon_monte_carlo_routes": len(long_routes),
        "preserved_scorecard_rows": len(scores),
    }
    for key, value in expected.items():
        if observed.get(key) != value:
            failures.append(f"COUNT_DRIFT:{key}:expected={value}:actual={observed.get(key)}")

    score_index = {
        (clean(row.get("challenge_group_id")), clean(row.get("model_name")), clean(row.get("partition_name"))): row
        for row in scores
    }
    required_partitions = contract["required_partitions"]
    moderate = contract["uncertainty_rules"]["moderate_uncertainty"]

    evidence_rows: list[dict[str, Any]] = []
    certified_rows: list[dict[str, Any]] = []
    for winner in winners:
        group = clean(winner.get("challenge_group_id"))
        model = clean(winner.get("repaired_challenge_model"))
        partition_rows = {name: score_index.get((group, model, name)) for name in required_partitions}
        missing = [name for name, row in partition_rows.items() if row is None]
        if missing:
            classification = contract["uncertainty_rules"]["missing_required_partition_classification"]
            failures.append(f"WINNER_PARTITION_EVIDENCE_MISSING:{group}:{model}:{'|'.join(missing)}")
        else:
            outer = partition_rows["OUTER_ALL"] or {}
            latest = partition_rows["LATEST_TIME_STRESS"] or {}
            concentration = partition_rows["PRODUCT_CONCENTRATION_STRESS"] or {}
            outer_mape = number(outer.get("median_ape"))
            outer_dir = number(outer.get("directional_accuracy"))
            latest_multiple = number(latest.get("median_ape")) / max(outer_mape, 1e-9)
            latest_decline = max(0.0, outer_dir - number(latest.get("directional_accuracy")))
            concentration_multiple = number(concentration.get("median_ape")) / max(outer_mape, 1e-9)
            concentration_dir = number(concentration.get("directional_accuracy"))
            moderate_pass = (
                outer_mape <= moderate["maximum_outer_all_median_ape"]
                and outer_dir >= moderate["minimum_outer_all_directional_accuracy"]
                and latest_multiple <= moderate["maximum_latest_time_median_ape_deterioration_multiple"]
                and latest_decline <= moderate["maximum_latest_time_directional_accuracy_decline"]
                and concentration_multiple <= moderate["maximum_product_concentration_median_ape_deterioration_multiple"]
                and concentration_dir >= moderate["minimum_product_concentration_directional_accuracy"]
            )
            classification = "MODERATE_UNCERTAINTY" if moderate_pass else contract["uncertainty_rules"]["otherwise_classification"]
            for partition_name, row in partition_rows.items():
                assert row is not None
                evidence_rows.append({
                    "challenge_group_id": group,
                    "selected_model": model,
                    "partition_name": partition_name,
                    "rows": clean(row.get("rows")),
                    "median_ape": clean(row.get("median_ape")),
                    "directional_accuracy": clean(row.get("directional_accuracy")),
                    "single_product_error_share": clean(row.get("single_product_error_share")),
                    "worst_product_mape_multiple": clean(row.get("worst_product_mape_multiple")),
                    "prediction_recomputed": False,
                    "error_recomputed": False,
                })

        certified_rows.append({
            "challenge_group_id": group,
            "horizon_code": clean(winner.get("horizon_code")),
            "forecast_method": clean(winner.get("forecast_method")),
            "certified_model": model,
            "source_repaired_decision": clean(winner.get("repaired_challenge_decision")),
            "winner_certification_status": "CERTIFIED" if classification != "NOT_CERTIFIABLE" else "NOT_CERTIFIABLE",
            "uncertainty_classification": classification,
            "mean_signed_percentage_error_status": contract["uncertainty_rules"]["mean_signed_percentage_error_status"],
            "lower_uncertainty_authorized": False,
            "model_selection_reopened": False,
            "forecast_generation_authorized": False,
        })

    unresolved_fields = [
        "challenge_group_id", "horizon_code", "forecast_method", "resolution_status",
        "winner_certification_authorized", "forecast_generation_authorized", "forced_resolution_prohibited",
    ]
    diagnostics = [{"severity": "BLOCKING", "code": failure, "detail": ""} for failure in failures]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    lineage = lineage_a + lineage_r
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    certified_fields = [
        "challenge_group_id", "horizon_code", "forecast_method", "certified_model",
        "source_repaired_decision", "winner_certification_status", "uncertainty_classification",
        "mean_signed_percentage_error_status", "lower_uncertainty_authorized",
        "model_selection_reopened", "forecast_generation_authorized",
    ]
    write_csv(OUTPUT_DIR / outputs["certified_winner_registry_csv"], certified_rows, certified_fields)
    evidence_fields = [
        "challenge_group_id", "selected_model", "partition_name", "rows", "median_ape",
        "directional_accuracy", "single_product_error_share", "worst_product_mape_multiple",
        "prediction_recomputed", "error_recomputed",
    ]
    write_csv(OUTPUT_DIR / outputs["winner_partition_evidence_csv"], evidence_rows, evidence_fields)
    write_csv(OUTPUT_DIR / outputs["unresolved_group_registry_csv"], unresolved, unresolved_fields)
    write_csv(OUTPUT_DIR / outputs["long_horizon_routing_csv"], long_routes, list(long_routes[0].keys()))
    write_csv(OUTPUT_DIR / outputs["diagnostics_csv"], diagnostics, ["severity", "code", "detail"])

    status = "PASS" if not failures else "FAIL"
    summary = {
        "certification_status": status,
        "short_horizon_groups": len(decisions),
        "certified_winner_rows": sum(row["winner_certification_status"] == "CERTIFIED" for row in certified_rows),
        "moderate_uncertainty_rows": sum(row["uncertainty_classification"] == "MODERATE_UNCERTAINTY" for row in certified_rows),
        "high_uncertainty_rows": sum(row["uncertainty_classification"] == "HIGH_UNCERTAINTY" for row in certified_rows),
        "not_certifiable_rows": sum(row["uncertainty_classification"] == "NOT_CERTIFIABLE" for row in certified_rows),
        "unresolved_no_champion_groups": len(unresolved),
        "long_horizon_monte_carlo_routes": len(long_routes),
        "preserved_scorecard_rows": len(scores),
        "model_selection_reopened": False,
        "prediction_recomputed": False,
        "error_recomputed": False,
        "new_tuning_performed": False,
        "lower_uncertainty_authorized": False,
        "mean_signed_percentage_error_status": contract["uncertainty_rules"]["mean_signed_percentage_error_status"],
        "blocking_diagnostic_rows": len(failures),
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_WINNER_UNCERTAINTY_CERTIFICATION_EXECUTION",
        "short_horizon_forecast_architecture_eligible": status == "PASS" and len(certified_rows) > 0,
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

    print("PASS_PRECOLLECTOR_WINNER_UNCERTAINTY_CERTIFICATION_EXECUTION" if not failures else "FAIL_PRECOLLECTOR_WINNER_UNCERTAINTY_CERTIFICATION_EXECUTION")
    print(f"CERTIFIED_WINNER_ROWS={summary['certified_winner_rows']}")
    print(f"MODERATE_UNCERTAINTY_ROWS={summary['moderate_uncertainty_rows']}")
    print(f"HIGH_UNCERTAINTY_ROWS={summary['high_uncertainty_rows']}")
    print(f"NOT_CERTIFIABLE_ROWS={summary['not_certifiable_rows']}")
    print(f"UNRESOLVED_NO_CHAMPION_GROUPS={len(unresolved)}")
    print(f"LONG_HORIZON_MONTE_CARLO_ROUTES={len(long_routes)}")
    print("MODEL_SELECTION_REOPENED=FALSE")
    print("PREDICTION_RECOMPUTED=FALSE")
    print("ERROR_RECOMPUTED=FALSE")
    print("LOWER_UNCERTAINTY_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
