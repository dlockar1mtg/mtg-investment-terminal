from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_final_premodel_user_exclusion_resolution_contract_v1.json"
EXCLUSIONS = ROOT / "data/governance/mtg/standards/collector_user_investment_exclusions_v1.csv"
BASE_SCRIPT = ROOT / "scripts/certify_collector_v1_final_premodel_blocker_resolution.py"
BASE_OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_blocker_resolution"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def clean(value: Any) -> str:
    return str(value or "").strip()


def truth(value: Any) -> bool:
    return clean(value).lower() in {"1", "true", "yes", "y"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []
    exclusions = read_csv(EXCLUSIONS)

    if len(exclusions) != contract["required_user_exclusions"]:
        failures.append("USER_EXCLUSION_COUNT_MISMATCH")

    exclusion_by_id = {clean(row.get("canonical_product_id")): row for row in exclusions}
    excluded_id = contract["required_excluded_canonical_product_id"]
    excluded = exclusion_by_id.get(excluded_id)
    if not excluded:
        failures.append("REQUIRED_USER_EXCLUSION_MISSING")
    else:
        if clean(excluded.get("effective_snapshot_id")) != contract["governing_snapshot_id"]:
            failures.append("USER_EXCLUSION_SNAPSHOT_MISMATCH")
        if clean(excluded.get("required_forecast_route")) != contract["allowed_user_exclusion_route"]:
            failures.append("USER_EXCLUSION_ROUTE_INVALID")
        if clean(excluded.get("exclusion_reason_code")) not in contract["allowed_user_exclusion_reason_codes"]:
            failures.append("USER_EXCLUSION_REASON_INVALID")
        if not truth(excluded.get("permanent_until_changed")):
            failures.append("USER_EXCLUSION_CHANGE_CONTROL_MISSING")
        if truth(excluded.get("purchase_analysis_allowed")) or truth(excluded.get("purchase_recommendation_authorized")):
            failures.append("USER_EXCLUSION_PURCHASE_GATE_OPEN")

    base_run = subprocess.run([sys.executable, str(BASE_SCRIPT)], cwd=ROOT, check=False)
    base_summary_path = BASE_OUTPUT / "collector_final_premodel_data_and_routing_summary.json"
    if not base_summary_path.is_file():
        failures.append("BASE_SUMMARY_MISSING")
        base_summary: dict[str, Any] = {}
    else:
        base_summary = json.loads(base_summary_path.read_text(encoding="utf-8"))

    base_failures = list(base_summary.get("critical_failures", []))
    if base_run.returncode != 1:
        failures.append(f"UNEXPECTED_BASE_EXIT_CODE:{base_run.returncode}")
    if base_failures != [contract["expected_base_failure"]]:
        failures.append("BASE_FAILURE_SET_NOT_EXACTLY_EXPECTED")

    required_base_files = {
        "manifest": BASE_OUTPUT / "collector_final_artifact_manifest.csv",
        "features": BASE_OUTPUT / "collector_final_feature_availability_registry.csv",
        "prices": BASE_OUTPUT / "collector_final_current_price_authority.csv",
        "anomalies": BASE_OUTPUT / "collector_final_anomaly_adjudication.csv",
        "comparables": BASE_OUTPUT / "collector_comparable_pool_certification.csv",
        "routing": BASE_OUTPUT / "collector_final_method_routing.csv",
        "risks": BASE_OUTPUT / "collector_structural_risk_resolution.csv",
        "traceability": BASE_OUTPUT / "collector_final_premodel_traceability.csv",
    }
    missing = [name for name, path in required_base_files.items() if not path.is_file()]
    if missing:
        failures.append("BASE_OUTPUTS_MISSING:" + ";".join(missing))

    if failures:
        summary = {
            "block_name": contract["contract_name"],
            "block_version": contract["contract_version"],
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "critical_failures": failures,
            "status": "FAIL_COLLECTOR_FINAL_PREMODEL_USER_EXCLUSION_RESOLUTION",
        }
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "collector_final_premodel_user_exclusion_resolution_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        return 1

    manifest = read_csv(required_base_files["manifest"])
    features = read_csv(required_base_files["features"])
    prices = read_csv(required_base_files["prices"])
    anomalies = read_csv(required_base_files["anomalies"])
    comparables = read_csv(required_base_files["comparables"])
    routing = read_csv(required_base_files["routing"])
    risks = read_csv(required_base_files["risks"])
    traceability = read_csv(required_base_files["traceability"])

    comparable_rows = [row for row in comparables if clean(row.get("target_canonical_product_id")) != excluded_id]
    excluded_comparables = [row for row in comparables if clean(row.get("target_canonical_product_id")) == excluded_id]
    if len(excluded_comparables) != 2:
        failures.append(f"EXPECTED_TWO_EXCLUDED_COMPARABLE_ROWS:{len(excluded_comparables)}")

    exclusion_certification: list[dict[str, Any]] = []
    for row in exclusions:
        cid = clean(row.get("canonical_product_id"))
        matching_routes = [route for route in routing if clean(route.get("canonical_product_id")) == cid]
        matching_prices = [price for price in prices if clean(price.get("canonical_product_id")) == cid]
        status = "PASS" if len(matching_routes) == 1 and len(matching_prices) == 1 else "FAIL"
        if status != "PASS":
            failures.append(f"USER_EXCLUSION_IDENTITY_RECONCILIATION_FAILED:{cid}")
        exclusion_certification.append({
            **row,
            "governed_registry_retained": True,
            "current_price_authority_retained": True,
            "historical_ledger_retained": True,
            "model_tournament_allowed": False,
            "ranking_allowed": False,
            "allocation_allowed": False,
            "certification_status": status,
        })

    updated_routing: list[dict[str, Any]] = []
    for row in routing:
        cid = clean(row.get("canonical_product_id"))
        updated = dict(row)
        if cid == excluded_id:
            updated.update({
                "final_forecast_method": contract["allowed_user_exclusion_route"],
                "method_reason": "User-excluded ultra-scarce non-purchase target; only two governed comparables exist, below the unchanged three-comparable minimum.",
                "direct_history_method_allowed": False,
                "comparable_method_allowed": False,
                "comparable_group_id": "",
                "comparable_products_used": "",
                "comparable_selection_basis": "",
                "forecast_output_allowed": False,
                "purchase_analysis_allowed": False,
                "purchase_recommendation_authorized": False,
                "routing_status": "GOVERNED_USER_EXCLUSION",
                "investable_universe_status": "USER_EXCLUDED_NON_INVESTABLE",
                "user_exclusion_reason_code": clean(excluded.get("exclusion_reason_code")) if excluded else "",
                "user_exclusion_effective_snapshot_id": contract["governing_snapshot_id"],
            })
        else:
            updated["investable_universe_status"] = (
                "IN_SCOPE_FOR_MODEL_TOURNAMENT"
                if truth(updated.get("forecast_output_allowed"))
                else "GOVERNED_DEFERRAL_NON_USER"
            )
            updated["user_exclusion_reason_code"] = ""
            updated["user_exclusion_effective_snapshot_id"] = ""
        updated_routing.append(updated)

    for row in risks:
        if clean(row.get("risk_id")) == "R09":
            row["final_status"] = "CONTROLLED_WITH_GOVERNED_DEFERRAL"
            row["control"] = "Twenty-three comparable pools meet the unchanged 3-to-5 rule; the ultra-scarce excluded product is explicitly deferred and removed from the investable tournament universe."
            row["residual_limitation"] = "The excluded product remains tracked but receives no forecast, ranking, allocation, or purchase output."

    for row in traceability:
        if clean(row.get("requirement_id")) == "COL-STD-004":
            row["test_or_gate"] = "24 comparable-route products evaluated; 23 certified pools; 1 explicit evidence-based user exclusion"
        if clean(row.get("requirement_id")) == "COL-STD-005":
            row["test_or_gate"] = "50 unique canonical IDs with final route, governed deferral, or governed user exclusion"

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest.append({
        "artifact_path": EXCLUSIONS.relative_to(ROOT).as_posix(),
        "sha256": sha256(EXCLUSIONS),
        "size_bytes": EXCLUSIONS.stat().st_size,
        "modified_at_utc": datetime.fromtimestamp(EXCLUSIONS.stat().st_mtime, timezone.utc).isoformat(),
        "inventory_generated_at_utc": generated_at,
        "inventory_status": "INCLUDED_CURRENT_RUN",
    })

    comparable_groups = {clean(row.get("target_canonical_product_id")) for row in comparable_rows}
    invalid_groups = []
    for target_id in comparable_groups:
        count = sum(clean(row.get("target_canonical_product_id")) == target_id for row in comparable_rows)
        if count < contract["minimum_comparables_per_certified_group"] or count > contract["maximum_comparables_per_certified_group"]:
            invalid_groups.append(f"{target_id}:{count}")
    if invalid_groups:
        failures.append("INVALID_CERTIFIED_COMPARABLE_GROUPS:" + ";".join(invalid_groups))

    direct_calibrated = sum(clean(row.get("final_forecast_method")) == "DIRECT_HISTORY_CALIBRATED" for row in updated_routing)
    direct_limited = sum(clean(row.get("final_forecast_method")) == "DIRECT_HISTORY_LIMITED" for row in updated_routing)
    comparable_adjusted = sum(clean(row.get("final_forecast_method")) == "COMPARABLE_PRODUCT_ADJUSTED" for row in updated_routing)
    forecast_authorized = sum(truth(row.get("forecast_output_allowed")) for row in updated_routing)
    deferred = len(updated_routing) - forecast_authorized
    user_excluded = sum(clean(row.get("routing_status")) == "GOVERNED_USER_EXCLUSION" for row in updated_routing)

    expected_checks = {
        "PRODUCT_COUNT": len(updated_routing) == contract["required_product_count"],
        "CURRENT_PRICE_COUNT": len(prices) == contract["required_product_count"],
        "ANOMALY_COUNT": len(anomalies) == contract["required_anomaly_rows"],
        "CERTIFIED_COMPARABLE_GROUPS": len(comparable_groups) == contract["required_certified_comparable_groups"],
        "DIRECT_CALIBRATED": direct_calibrated == contract["required_direct_history_calibrated_routes"],
        "DIRECT_LIMITED": direct_limited == contract["required_direct_history_limited_routes"],
        "COMPARABLE_ADJUSTED": comparable_adjusted == contract["required_comparable_product_adjusted_routes"],
        "FORECAST_AUTHORIZED": forecast_authorized == contract["required_forecast_authorized_products"],
        "DEFERRED": deferred == contract["required_deferred_products"],
        "USER_EXCLUDED": user_excluded == contract["required_user_exclusions"],
    }
    failures.extend(name for name, passed in expected_checks.items() if not passed)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_final_artifact_manifest.csv", manifest, list(manifest[0].keys()))
    write_csv(OUTPUT / "collector_final_feature_availability_registry.csv", features, list(features[0].keys()))
    write_csv(OUTPUT / "collector_final_current_price_authority.csv", prices, list(prices[0].keys()))
    write_csv(OUTPUT / "collector_final_anomaly_adjudication.csv", anomalies, list(anomalies[0].keys()))
    write_csv(OUTPUT / "collector_comparable_pool_certification.csv", comparable_rows, list(comparable_rows[0].keys()))
    write_csv(OUTPUT / "collector_final_method_routing.csv", updated_routing, list(updated_routing[0].keys()))
    write_csv(OUTPUT / "collector_structural_risk_resolution.csv", risks, list(risks[0].keys()))
    write_csv(OUTPUT / "collector_final_premodel_traceability.csv", traceability, list(traceability[0].keys()))
    write_csv(OUTPUT / "collector_user_investment_exclusion_certification.csv", exclusion_certification, list(exclusion_certification[0].keys()))

    all_controls_complete = not failures
    summary = {
        "block_name": contract["contract_name"],
        "block_version": contract["contract_version"],
        "generated_at_utc": generated_at,
        "governing_snapshot_id": contract["governing_snapshot_id"],
        "product_rows": len(updated_routing),
        "ledger_rows": int(base_summary.get("ledger_rows", 0)),
        "lifecycle_rows": int(base_summary.get("lifecycle_rows", 0)),
        "current_price_certified_products": len(prices),
        "anomaly_rows": len(anomalies),
        "anomaly_rows_resolved": sum(clean(row.get("adjudication_status")) == "RESOLVED_BY_GOVERNED_POLICY" for row in anomalies),
        "comparable_route_products_evaluated": contract["required_comparable_route_products_evaluated"],
        "comparable_groups_certified": len(comparable_groups),
        "comparable_relationship_rows": len(comparable_rows),
        "direct_history_calibrated_routes": direct_calibrated,
        "direct_history_limited_routes": direct_limited,
        "comparable_product_adjusted_routes": comparable_adjusted,
        "forecast_authorized_products": forecast_authorized,
        "deferred_products": deferred,
        "user_excluded_products": user_excluded,
        "structural_risks_controlled": len(risks),
        "traceability_requirements_passed": sum(clean(row.get("status")) == "PASS" for row in traceability),
        "three_comparable_minimum_unchanged": True,
        "dynamic_artifact_manifest_completed": all_controls_complete,
        "feature_leakage_controls_certified": all_controls_complete,
        "current_price_final_authority_certified": len(prices) == contract["required_product_count"] and all_controls_complete,
        "anomaly_adjudication_certified": len(anomalies) == contract["required_anomaly_rows"] and all_controls_complete,
        "comparable_pools_certified": len(comparable_groups) == contract["required_certified_comparable_groups"] and all_controls_complete,
        "user_exclusion_certified": user_excluded == contract["required_user_exclusions"] and all_controls_complete,
        "final_product_method_routing_certified": len(updated_routing) == contract["required_product_count"] and all_controls_complete,
        "model_tournament_build_authorized": forecast_authorized == contract["required_forecast_authorized_products"] and all_controls_complete,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": contract["expected_status"] if all_controls_complete else "FAIL_COLLECTOR_FINAL_PREMODEL_USER_EXCLUSION_RESOLUTION",
    }
    (OUTPUT / "collector_final_premodel_user_exclusion_resolution_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if all_controls_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
