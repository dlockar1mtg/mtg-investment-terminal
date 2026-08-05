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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_ranking_readiness_architecture_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/ranking_readiness_architecture"


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


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    package = contract["required_forecast_output_execution_package"]
    package_path = Path(tempfile.gettempdir()) / package["package_name"]
    if not package_path.is_file():
        raise RuntimeError(f"PACKAGE_MISSING:{package_path}")
    actual_hash = sha256_file(package_path)
    if actual_hash != package["sha256"]:
        raise RuntimeError(f"PACKAGE_HASH_DRIFT:expected={package['sha256']}:actual={actual_hash}")

    required = [
        "precollector_governed_product_long_horizon_forecast_output.csv",
        "precollector_governed_short_horizon_certification_scope.csv",
        "precollector_governed_product_output_readiness.csv",
        "precollector_forecast_output_execution_summary.json",
    ]
    payloads: dict[str, bytes] = {}
    lineage: list[dict[str, Any]] = []
    with zipfile.ZipFile(package_path) as archive:
        available = {Path(item.filename).name: item for item in archive.infolist() if not item.is_dir()}
        for name in required:
            member = available.get(name)
            if member is None:
                raise RuntimeError(f"PACKAGE_MEMBER_MISSING:{name}")
            payload = archive.read(member)
            payloads[name] = payload
            lineage.append({
                "artifact_role": "CERTIFIED_FORECAST_OUTPUT_EXECUTION",
                "package_name": package_path.name,
                "package_sha256": actual_hash,
                "member_name": name,
                "member_sha256": sha256_bytes(payload),
                "row_count": len(read_csv_bytes(payload)) if name.endswith(".csv") else "",
            })

    long_rows = read_csv_bytes(payloads[required[0]])
    short_rows = read_csv_bytes(payloads[required[1]])
    readiness_rows = read_csv_bytes(payloads[required[2]])
    source_summary = json.loads(payloads[required[3]].decode("utf-8-sig"))

    products = {row.get("tcgplayer_product_id", "").strip() for row in long_rows}
    horizons = {row.get("horizon_code", "").strip() for row in long_rows}
    expected = contract["expected_counts"]
    observed = {
        "governed_products": len(products),
        "long_horizon_output_rows": len(long_rows),
        "long_horizon_horizon_codes": len(horizons),
        "short_horizon_scope_rows": len(short_rows),
    }
    failures = [
        f"COUNT_DRIFT:{key}:expected={value}:actual={observed.get(key)}"
        for key, value in expected.items()
        if observed.get(key) != value
    ]
    if int(source_summary.get("governed_products", -1)) != expected["governed_products"]:
        failures.append("SOURCE_SUMMARY_PRODUCT_COUNT_DRIFT")
    if len(readiness_rows) != expected["governed_products"]:
        failures.append("PRODUCT_READINESS_COUNT_DRIFT")

    components = contract["ranking_policy"]["components"]
    weight_sum = sum(float(item["weight"]) for item in components)
    if abs(weight_sum - 1.0) > 1e-12:
        failures.append(f"RANKING_WEIGHT_SUM_INVALID:{weight_sum}")

    eligibility_rows = [
        {"policy_name": key, "policy_value": value, "architecture_only": True}
        for key, value in contract["eligibility_policy"].items()
    ]
    component_rows = [
        {**item, "normalization": contract["ranking_policy"]["normalization"], "ranking_executed": False}
        for item in components
    ]
    tie_rows = [
        {"priority": index, "tie_breaker": name, "ranking_executed": False}
        for index, name in enumerate(contract["ranking_policy"]["tie_breakers"], start=1)
    ]
    execution_rows = [{
        "eligible_product_count_expected": expected["governed_products"],
        "eligible_horizons": "Y3|Y5",
        "short_horizon_product_values_used": False,
        "ranking_execution_performed": False,
        "purchase_analysis_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["required_outputs"]
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    write_csv(OUTPUT_DIR / outputs["eligibility_policy_csv"], eligibility_rows, list(eligibility_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["component_policy_csv"], component_rows, list(component_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["tie_break_policy_csv"], tie_rows, list(tie_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["execution_plan_csv"], execution_rows, list(execution_rows[0].keys()))

    status = "PASS" if not failures else "FAIL"
    summary = {
        "certification_status": status,
        **observed,
        "ranking_components": len(components),
        "ranking_weight_sum": weight_sum,
        "ranking_execution_performed": False,
        "short_horizon_product_values_used": False,
        "forecast_recomputed": False,
        "monte_carlo_recomputed": False,
        "critical_failures": failures,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_RANKING_READINESS_ARCHITECTURE",
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

    print("PASS_PRECOLLECTOR_RANKING_READINESS_ARCHITECTURE" if not failures else "FAIL_PRECOLLECTOR_RANKING_READINESS_ARCHITECTURE")
    print(f"GOVERNED_PRODUCTS={len(products)}")
    print(f"LONG_HORIZON_OUTPUT_ROWS={len(long_rows)}")
    print(f"RANKING_COMPONENTS={len(components)}")
    print(f"RANKING_WEIGHT_SUM={weight_sum:.6f}")
    print("SHORT_HORIZON_PRODUCT_VALUES_USED=FALSE")
    print("RANKING_EXECUTION_PERFORMED=FALSE")
    print(f"NEXT_STAGE={summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
