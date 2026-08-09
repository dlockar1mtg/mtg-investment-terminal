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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_forecast_readiness_output_execution_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/forecast_readiness_output_execution"


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
    architecture, lineage_a = load_package(
        contract["required_architecture_package"],
        ["precollector_forecast_readiness_matrix.csv", "precollector_forecast_output_schema.csv", "precollector_forecast_readiness_output_architecture_summary.json"],
        "CERTIFIED_FORECAST_OUTPUT_ARCHITECTURE",
    )
    monte_carlo, lineage_m = load_package(
        contract["required_monte_carlo_execution_package"],
        ["precollector_long_horizon_monte_carlo_product_horizon_distribution.csv", "precollector_long_horizon_monte_carlo_execution_summary.json"],
        "CERTIFIED_LONG_HORIZON_MONTE_CARLO_EXECUTION",
    )
    winner, lineage_w = load_package(
        contract["required_winner_uncertainty_execution_package"],
        ["precollector_certified_short_horizon_winner_uncertainty_registry.csv", "precollector_winner_uncertainty_unresolved_group_registry.csv"],
        "CERTIFIED_SHORT_HORIZON_WINNER_UNCERTAINTY_EXECUTION",
    )

    readiness = read_csv_bytes(architecture["precollector_forecast_readiness_matrix.csv"])
    long_rows = read_csv_bytes(monte_carlo["precollector_long_horizon_monte_carlo_product_horizon_distribution.csv"])
    winners = read_csv_bytes(winner["precollector_certified_short_horizon_winner_uncertainty_registry.csv"])
    unresolved = read_csv_bytes(winner["precollector_winner_uncertainty_unresolved_group_registry.csv"])

    failures: list[str] = []
    required_fields = contract["output_rules"]["required_long_horizon_fields"]
    for field in required_fields:
        if long_rows and field not in long_rows[0]:
            failures.append(f"LONG_HORIZON_FIELD_MISSING:{field}")
    ids = {str(row.get("tcgplayer_product_id", "")).strip() for row in long_rows}
    observed = {
        "governed_products": len(ids),
        "long_horizon_output_rows": len(long_rows),
        "short_horizon_certified_winners": len(winners),
        "short_horizon_unresolved_groups": len(unresolved),
        "short_horizon_scope_rows": len(winners) + len(unresolved),
    }
    for key, expected in contract["expected_counts"].items():
        if observed.get(key) != expected:
            failures.append(f"COUNT_DRIFT:{key}:expected={expected}:actual={observed.get(key)}")

    scope_rows: list[dict[str, Any]] = []
    for row in winners:
        scope_rows.append({
            "challenge_group_id": row.get("challenge_group_id", ""),
            "horizon_code": row.get("horizon_code", ""),
            "forecast_method": row.get("forecast_method", ""),
            "certification_status": row.get("winner_certification_status", "CERTIFIED"),
            "certified_model": row.get("certified_model", ""),
            "uncertainty_classification": row.get("uncertainty_classification", ""),
            "product_level_forecast_value": "",
            "product_level_value_status": contract["output_rules"]["short_horizon_product_value_status"],
        })
    for row in unresolved:
        scope_rows.append({
            "challenge_group_id": row.get("challenge_group_id", ""),
            "horizon_code": row.get("horizon_code", ""),
            "forecast_method": row.get("forecast_method", ""),
            "certification_status": "UNRESOLVED_NO_PRODUCTION_CHAMPION",
            "certified_model": "",
            "uncertainty_classification": "UNRESOLVED",
            "product_level_forecast_value": "",
            "product_level_value_status": contract["output_rules"]["short_horizon_product_value_status"],
        })

    product_readiness: list[dict[str, Any]] = []
    by_product: dict[str, list[dict[str, str]]] = {}
    for row in long_rows:
        by_product.setdefault(str(row.get("tcgplayer_product_id", "")).strip(), []).append(row)
    for product_id, rows in sorted(by_product.items()):
        horizons = {str(row.get("horizon_code", "")) for row in rows}
        product_readiness.append({
            "tcgplayer_product_id": product_id,
            "product_name": rows[0].get("product_name", ""),
            "forecast_route": rows[0].get("forecast_route", ""),
            "y3_distribution_present": "Y3" in horizons,
            "y5_distribution_present": "Y5" in horizons,
            "long_horizon_output_ready": horizons == {"Y3", "Y5"},
            "short_horizon_product_values_available": False,
            "ranking_execution_authorized": False,
            "purchase_analysis_authorized": False,
        })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["required_outputs"]
    lineage = lineage_a + lineage_m + lineage_w
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    write_csv(OUTPUT_DIR / outputs["product_long_horizon_output_csv"], long_rows, list(long_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["short_horizon_certification_scope_csv"], scope_rows, list(scope_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["product_output_readiness_csv"], product_readiness, list(product_readiness[0].keys()))
    diagnostics = [{"severity": "BLOCKING", "code": item, "detail": ""} for item in failures]
    write_csv(OUTPUT_DIR / outputs["diagnostics_csv"], diagnostics, ["severity", "code", "detail"])

    summary = {
        "certification_status": "PASS" if not failures else "FAIL",
        **observed,
        "architecture_readiness_rows": len(readiness),
        "short_horizon_product_values_materialized": False,
        "monte_carlo_recomputed": False,
        "model_selection_reopened": False,
        "critical_failures": failures,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_FORECAST_READINESS_AND_OUTPUT_EXECUTION",
        "forecast_output_materialization_authorized": not failures,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
    }
    (OUTPUT_DIR / outputs["summary_json"]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "outputs": [
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUTPUT_DIR.iterdir()) if path.is_file() and path.name != outputs["manifest_json"]
        ],
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_FORECAST_READINESS_OUTPUT_EXECUTION" if not failures else "FAIL_PRECOLLECTOR_FORECAST_READINESS_OUTPUT_EXECUTION")
    for key, value in observed.items():
        print(f"{key.upper()}={value}")
    print("SHORT_HORIZON_PRODUCT_VALUES_MATERIALIZED=FALSE")
    print("MONTE_CARLO_RECOMPUTED=FALSE")
    print("RANKING_EXECUTION_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
