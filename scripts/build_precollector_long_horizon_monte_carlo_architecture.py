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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_long_horizon_monte_carlo_architecture_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/long_horizon_monte_carlo_architecture"

CERTIFIED_WINNER_REGISTRY = "precollector_certified_short_horizon_winner_uncertainty_registry.csv"
UNRESOLVED_GROUP_REGISTRY = "precollector_winner_uncertainty_unresolved_group_registry.csv"
LONG_HORIZON_ROUTING = "precollector_winner_uncertainty_long_horizon_routing.csv"
WINNER_UNCERTAINTY_SUMMARY = "precollector_winner_uncertainty_execution_summary.json"


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


def required_package_members() -> list[str]:
    return [
        CERTIFIED_WINNER_REGISTRY,
        UNRESOLVED_GROUP_REGISTRY,
        LONG_HORIZON_ROUTING,
        WINNER_UNCERTAINTY_SUMMARY,
    ]


def load_package(contract: dict[str, Any]) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    package = contract["required_winner_uncertainty_execution_package"]
    path = Path(tempfile.gettempdir()) / package["package_name"]
    if not path.is_file():
        raise RuntimeError(f"PACKAGE_MISSING:{path}")
    actual = sha256_file(path)
    if actual != package["sha256"]:
        raise RuntimeError(f"PACKAGE_HASH_DRIFT:expected={package['sha256']}:actual={actual}")
    payloads: dict[str, bytes] = {}
    lineage: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        available = {Path(item.filename).name: item for item in archive.infolist() if not item.is_dir()}
        for name in required_package_members():
            member = available.get(name)
            if member is None:
                raise RuntimeError(f"PACKAGE_MEMBER_MISSING:{name}")
            payload = archive.read(member)
            payloads[name] = payload
            lineage.append({
                "artifact_role": "CERTIFIED_WINNER_UNCERTAINTY_EXECUTION_INPUT",
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
    winners = read_csv_bytes(payloads[CERTIFIED_WINNER_REGISTRY])
    unresolved = read_csv_bytes(payloads[UNRESOLVED_GROUP_REGISTRY])
    routes = read_csv_bytes(payloads[LONG_HORIZON_ROUTING])
    summary = json.loads(payloads[WINNER_UNCERTAINTY_SUMMARY].decode("utf-8-sig"))

    failures: list[str] = []
    expected = contract["expected_counts"]
    observed = {
        "certified_short_horizon_winners": len(winners),
        "unresolved_short_horizon_groups": len(unresolved),
        "long_horizon_routes": len(routes),
        "long_horizon_horizon_codes": len({clean(r.get("horizon_code")) for r in routes}),
    }
    for key, value in expected.items():
        if observed.get(key) != value:
            failures.append(f"COUNT_DRIFT:{key}:expected={value}:actual={observed.get(key)}")
    if int(summary.get("certified_winner_rows", -1)) != expected["certified_short_horizon_winners"]:
        failures.append("SOURCE_SUMMARY_WINNER_COUNT_DRIFT")
    if int(summary.get("long_horizon_monte_carlo_routes", -1)) != expected["long_horizon_routes"]:
        failures.append("SOURCE_SUMMARY_LONG_ROUTE_COUNT_DRIFT")

    design = contract["simulation_design"]
    allowed_horizons = set(design["horizon_codes"])
    route_registry: list[dict[str, Any]] = []
    execution_plan: list[dict[str, Any]] = []
    for index, row in enumerate(routes, start=1):
        horizon = clean(row.get("horizon_code"))
        if horizon not in allowed_horizons:
            failures.append(f"UNEXPECTED_HORIZON:{horizon}")
        horizon_days = int(design["horizon_days"].get(horizon, 0))
        if horizon_days <= 0:
            failures.append(f"MISSING_HORIZON_DAYS:{horizon}")
        route_id = clean(row.get("challenge_group_id")) or f"LONG_ROUTE_{index:02d}"
        route_registry.append({
            **row,
            "monte_carlo_route_id": route_id,
            "required_simulations_per_product_horizon": design["required_simulations_per_product_horizon"],
            "horizon_days": horizon_days,
            "distribution_family": design["distribution_family"],
            "tail_stress_required": True,
            "parameter_uncertainty_required": True,
            "path_uncertainty_required": True,
            "scenario_uncertainty_required": True,
            "direct_winner_certification_authorized": False,
        })
        execution_plan.append({
            "monte_carlo_route_id": route_id,
            "horizon_code": horizon,
            "horizon_days": horizon_days,
            "required_simulations_per_product_horizon": design["required_simulations_per_product_horizon"],
            "deterministic_seed_required": True,
            "common_random_numbers_required_within_product": True,
            "simulation_execution_performed": False,
            "forecast_generation_authorized": False,
            "next_stage": contract["next_stage_if_certified"],
        })

    policy_rows: list[dict[str, Any]] = []
    for key, value in design.items():
        policy_rows.append({
            "policy_name": key,
            "policy_value": json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value,
            "architecture_only": True,
            "execution_performed": False,
        })

    seed_rows = [{
        "seed_registry_required": design["deterministic_seed_registry_required"],
        "minimum_seed": design["minimum_random_seed"],
        "maximum_seed": design["maximum_random_seed"],
        "common_random_numbers_required_within_product": design["common_random_numbers_required_within_product"],
        "seed_assignment_method": "STABLE_SHA256_ROUTE_PRODUCT_HORIZON",
        "seed_assignment_execution_performed": False,
    }]

    output_schema_rows = []
    for output_name in design["required_outputs"]:
        output_schema_rows.append({
            "output_name": output_name,
            "required": True,
            "distributional": output_name.endswith("distribution") or "probability" in output_name or "tail" in output_name,
            "point_forecast_only_prohibited": contract["uncertainty_governance"]["point_forecast_only_output_prohibited"],
        })
    for quantile in design["required_quantiles"]:
        output_schema_rows.append({
            "output_name": f"quantile_{quantile:.2f}",
            "required": True,
            "distributional": True,
            "point_forecast_only_prohibited": True,
        })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["required_outputs"]
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    write_csv(OUTPUT_DIR / outputs["route_registry_csv"], route_registry, list(route_registry[0].keys()))
    write_csv(OUTPUT_DIR / outputs["simulation_policy_csv"], policy_rows, list(policy_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["seed_policy_csv"], seed_rows, list(seed_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["output_schema_csv"], output_schema_rows, list(output_schema_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["execution_plan_csv"], execution_plan, list(execution_plan[0].keys()))

    status = "PASS" if not failures else "FAIL"
    architecture_summary = {
        "certification_status": status,
        "certified_short_horizon_winners": len(winners),
        "unresolved_short_horizon_groups": len(unresolved),
        "long_horizon_routes": len(routes),
        "long_horizon_horizon_codes": len({clean(r.get("horizon_code")) for r in routes}),
        "required_simulations_per_product_horizon": design["required_simulations_per_product_horizon"],
        "required_horizon_days": sorted(design["horizon_days"].values()),
        "required_quantiles": design["required_quantiles"],
        "deterministic_seed_registry_required": design["deterministic_seed_registry_required"],
        "common_random_numbers_required_within_product": design["common_random_numbers_required_within_product"],
        "monte_carlo_execution_performed": False,
        "short_horizon_model_selection_reopened": False,
        "new_live_collection_authorized": False,
        "model_tuning_authorized": False,
        "critical_failures": failures,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_ARCHITECTURE",
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

    print("PASS_PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_ARCHITECTURE" if not failures else "FAIL_PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_ARCHITECTURE")
    print(f"LONG_HORIZON_ROUTES={len(routes)}")
    print(f"LONG_HORIZON_HORIZON_CODES={len({clean(r.get('horizon_code')) for r in routes})}")
    print(f"REQUIRED_SIMULATIONS_PER_PRODUCT_HORIZON={design['required_simulations_per_product_horizon']}")
    print("DETERMINISTIC_SEED_REGISTRY_REQUIRED=TRUE")
    print("COMMON_RANDOM_NUMBERS_REQUIRED_WITHIN_PRODUCT=TRUE")
    print("MONTE_CARLO_EXECUTION_PERFORMED=FALSE")
    print(f"NEXT_STAGE={architecture_summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
