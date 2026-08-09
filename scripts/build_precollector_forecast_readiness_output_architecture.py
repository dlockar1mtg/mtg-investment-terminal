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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_forecast_readiness_output_architecture_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/forecast_readiness_output_architecture"


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
    monte_required = [
        "precollector_long_horizon_monte_carlo_product_horizon_distribution.csv",
        "precollector_long_horizon_monte_carlo_return_pool_registry.csv",
        "precollector_long_horizon_monte_carlo_seed_registry.csv",
        "precollector_long_horizon_monte_carlo_execution_summary.json",
    ]
    winner_required = [
        "precollector_certified_short_horizon_winner_uncertainty_registry.csv",
        "precollector_winner_uncertainty_unresolved_group_registry.csv",
        "precollector_winner_uncertainty_execution_summary.json",
    ]
    monte, lineage_m = load_package(contract["required_monte_carlo_execution_package"], monte_required, "CERTIFIED_LONG_HORIZON_MONTE_CARLO_EXECUTION")
    winner, lineage_w = load_package(contract["required_winner_uncertainty_execution_package"], winner_required, "CERTIFIED_WINNER_UNCERTAINTY_EXECUTION")

    distributions = read_csv_bytes(monte["precollector_long_horizon_monte_carlo_product_horizon_distribution.csv"])
    pools = read_csv_bytes(monte["precollector_long_horizon_monte_carlo_return_pool_registry.csv"])
    seeds = read_csv_bytes(monte["precollector_long_horizon_monte_carlo_seed_registry.csv"])
    monte_summary = json.loads(monte["precollector_long_horizon_monte_carlo_execution_summary.json"].decode("utf-8-sig"))
    winners = read_csv_bytes(winner["precollector_certified_short_horizon_winner_uncertainty_registry.csv"])
    unresolved = read_csv_bytes(winner["precollector_winner_uncertainty_unresolved_group_registry.csv"])
    winner_summary = json.loads(winner["precollector_winner_uncertainty_execution_summary.json"].decode("utf-8-sig"))

    failures: list[str] = []
    products = {clean(row.get("tcgplayer_product_id")) for row in distributions}
    horizons = {clean(row.get("horizon_code")) for row in distributions}
    observed = {
        "governed_products": len(products),
        "short_horizon_certified_winners": len(winners),
        "short_horizon_unresolved_groups": len(unresolved),
        "long_horizon_product_horizon_rows": len(distributions),
        "long_horizon_horizon_codes": len(horizons),
    }
    for key, expected in contract["expected_counts"].items():
        if observed.get(key) != expected:
            failures.append(f"COUNT_DRIFT:{key}:expected={expected}:actual={observed.get(key)}")
    if monte_summary.get("certification_status") != "PASS":
        failures.append("MONTE_CARLO_SOURCE_NOT_CERTIFIED")
    if winner_summary.get("certification_status") != "PASS":
        failures.append("WINNER_SOURCE_NOT_CERTIFIED")

    required_long_fields = set(contract["output_governance"]["long_horizon_required_fields"])
    distribution_fields = set(distributions[0].keys()) if distributions else set()
    missing_long_fields = sorted(required_long_fields - distribution_fields)
    if missing_long_fields:
        failures.append(f"LONG_HORIZON_OUTPUT_FIELDS_MISSING:{'|'.join(missing_long_fields)}")

    short_rows: list[dict[str, Any]] = []
    for row in winners:
        short_rows.append({
            "challenge_group_id": clean(row.get("challenge_group_id")),
            "horizon_code": clean(row.get("horizon_code")),
            "certified_model": clean(row.get("certified_model")),
            "output_status": "CERTIFIED",
            "uncertainty_classification": clean(row.get("uncertainty_classification")),
            "forecast_output_value_authorized": False,
            "ranking_input_authorized": False,
        })
    for row in unresolved:
        short_rows.append({
            "challenge_group_id": clean(row.get("challenge_group_id")),
            "horizon_code": clean(row.get("horizon_code")),
            "certified_model": "",
            "output_status": "UNRESOLVED_NO_PRODUCTION_CHAMPION",
            "uncertainty_classification": "UNRESOLVED",
            "forecast_output_value_authorized": False,
            "ranking_input_authorized": False,
        })

    long_rows = [{
        "tcgplayer_product_id": clean(row.get("tcgplayer_product_id")),
        "horizon_code": clean(row.get("horizon_code")),
        "distribution_present": True,
        "quantiles_present": all(clean(row.get(f"terminal_value_q{q}")) for q in ("05", "10", "25", "50", "75", "90", "95")),
        "loss_probability_present": bool(clean(row.get("probability_of_loss"))),
        "positive_return_probability_present": bool(clean(row.get("probability_of_positive_return"))),
        "lineage_present": bool(clean(row.get("return_pool_source"))) and bool(clean(row.get("seed"))),
        "forecast_output_value_authorized": False,
        "ranking_input_authorized": False,
    } for row in distributions]

    readiness_rows = [{
        "readiness_domain": "SHORT_HORIZON_WINNER_CERTIFICATION",
        "observed_rows": len(winners),
        "required_rows": 5,
        "status": "READY_FOR_OUTPUT_EXECUTION" if len(winners) == 5 else "BLOCKED",
    }, {
        "readiness_domain": "SHORT_HORIZON_UNRESOLVED_GOVERNANCE",
        "observed_rows": len(unresolved),
        "required_rows": 4,
        "status": "READY_FOR_OUTPUT_EXECUTION" if len(unresolved) == 4 else "BLOCKED",
    }, {
        "readiness_domain": "LONG_HORIZON_DISTRIBUTIONS",
        "observed_rows": len(distributions),
        "required_rows": 100,
        "status": "READY_FOR_OUTPUT_EXECUTION" if len(distributions) == 100 and not missing_long_fields else "BLOCKED",
    }, {
        "readiness_domain": "DETERMINISTIC_SEED_LINEAGE",
        "observed_rows": len(seeds),
        "required_rows": 100,
        "status": "READY_FOR_OUTPUT_EXECUTION" if len(seeds) == 100 else "BLOCKED",
    }, {
        "readiness_domain": "RETURN_POOL_LINEAGE",
        "observed_rows": len(pools),
        "required_rows": 50,
        "status": "READY_FOR_OUTPUT_EXECUTION" if len(pools) == 50 else "BLOCKED",
    }]

    schema_rows: list[dict[str, Any]] = []
    for horizon in contract["output_governance"]["required_horizons"]:
        schema_rows.append({
            "horizon_code": horizon,
            "output_type": "CERTIFIED_POINT_AND_UNCERTAINTY" if horizon in {"D90", "D180", "D365"} else "CERTIFIED_DISTRIBUTION",
            "uncertainty_disclosure_required": True,
            "lineage_disclosure_required": True,
            "point_forecast_only_prohibited": horizon in {"Y3", "Y5"},
            "unresolved_value_must_be_blank": horizon in {"D90", "D180", "D365"},
        })

    authorization_rows = [
        {"capability": "FORECAST_OUTPUT_EXECUTION", "authorized": not failures, "next_stage_required": contract["next_stage_if_certified"]},
        {"capability": "RANKING_EXECUTION", "authorized": False, "next_stage_required": "SEPARATE_RANKING_ARCHITECTURE_AND_CERTIFICATION"},
        {"capability": "PURCHASE_ANALYSIS", "authorized": False, "next_stage_required": "SEPARATE_PURCHASE_ANALYSIS_ARCHITECTURE_AND_CERTIFICATION"},
        {"capability": "PURCHASE_RECOMMENDATION", "authorized": False, "next_stage_required": "EXPLICIT_FINAL_GOVERNANCE_AUTHORIZATION"},
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["required_outputs"]
    lineage = lineage_m + lineage_w
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    write_csv(OUTPUT_DIR / outputs["readiness_matrix_csv"], readiness_rows, list(readiness_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["output_schema_csv"], schema_rows, list(schema_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["short_horizon_scope_csv"], short_rows, list(short_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["long_horizon_scope_csv"], long_rows, list(long_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["authorization_matrix_csv"], authorization_rows, list(authorization_rows[0].keys()))

    summary = {
        "certification_status": "PASS" if not failures else "FAIL",
        **observed,
        "deterministic_seed_rows": len(seeds),
        "return_pool_rows": len(pools),
        "short_horizon_output_scope_rows": len(short_rows),
        "long_horizon_output_scope_rows": len(long_rows),
        "output_execution_performed": False,
        "new_forecast_generation_performed": False,
        "monte_carlo_recomputed": False,
        "short_horizon_model_selection_reopened": False,
        "short_horizon_certifications_modified": False,
        "critical_failures": failures,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_FORECAST_READINESS_OUTPUT_ARCHITECTURE",
        "forecast_output_execution_authorized": not failures,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
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

    print("PASS_PRECOLLECTOR_FORECAST_READINESS_OUTPUT_ARCHITECTURE" if not failures else "FAIL_PRECOLLECTOR_FORECAST_READINESS_OUTPUT_ARCHITECTURE")
    print(f"GOVERNED_PRODUCTS={observed['governed_products']}")
    print(f"SHORT_HORIZON_CERTIFIED_WINNERS={len(winners)}")
    print(f"SHORT_HORIZON_UNRESOLVED_GROUPS={len(unresolved)}")
    print(f"LONG_HORIZON_PRODUCT_HORIZON_ROWS={len(distributions)}")
    print("OUTPUT_EXECUTION_PERFORMED=FALSE")
    print("RANKING_EXECUTION_AUTHORIZED=FALSE")
    print("PURCHASE_ANALYSIS_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
