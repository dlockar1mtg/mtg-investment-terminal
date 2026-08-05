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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_purchase_analysis_readiness_architecture_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/purchase_analysis_readiness_architecture"


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
    package = contract["required_ranking_execution_package"]
    package_path = Path(tempfile.gettempdir()) / package["package_name"]
    if not package_path.is_file():
        raise RuntimeError(f"PACKAGE_MISSING:{package_path}")
    actual_hash = sha256_file(package_path)
    if actual_hash != package["sha256"]:
        raise RuntimeError(f"PACKAGE_HASH_DRIFT:expected={package['sha256']}:actual={actual_hash}")

    required_members = [
        "precollector_governed_long_horizon_product_rankings.csv",
        "precollector_ranking_component_scores.csv",
        "precollector_ranking_execution_summary.json",
    ]
    payloads: dict[str, bytes] = {}
    lineage: list[dict[str, Any]] = []
    with zipfile.ZipFile(package_path) as archive:
        available = {Path(item.filename).name: item for item in archive.infolist() if not item.is_dir()}
        for name in required_members:
            member = available.get(name)
            if member is None:
                raise RuntimeError(f"PACKAGE_MEMBER_MISSING:{name}")
            payload = archive.read(member)
            payloads[name] = payload
            lineage.append({
                "artifact_role": "CERTIFIED_RANKING_EXECUTION_INPUT",
                "package_name": package_path.name,
                "package_sha256": actual_hash,
                "member_name": name,
                "member_sha256": sha256_bytes(payload),
                "row_count": len(read_csv_bytes(payload)) if name.endswith(".csv") else "",
            })

    rankings = read_csv_bytes(payloads["precollector_governed_long_horizon_product_rankings.csv"])
    components = read_csv_bytes(payloads["precollector_ranking_component_scores.csv"])
    source_summary = json.loads(payloads["precollector_ranking_execution_summary.json"].decode("utf-8-sig"))

    failures: list[str] = []
    expected = contract["expected_counts"]
    observed = {
        "governed_products": int(source_summary.get("governed_products", -1)),
        "ranked_product_rows": len(rankings),
        "ranking_components": len({row.get("component", "") for row in components}),
    }
    for key, value in expected.items():
        if observed.get(key) != value:
            failures.append(f"COUNT_DRIFT:{key}:expected={value}:actual={observed.get(key)}")

    dimension_rows = []
    for dimension in contract["required_purchase_analysis_dimensions"]:
        dimension_rows.append({
            "dimension": dimension,
            "required": True,
            "available_from_ranking_package": dimension in {
                "RANK_STRENGTH", "DOWNSIDE_RISK", "LOSS_PROBABILITY"
            },
            "architecture_only": True,
            "purchase_analysis_performed": False,
        })

    required_inputs = [
        ("CERTIFIED_RANKING_REGISTRY", True, True),
        ("CERTIFIED_CURRENT_PRICE", True, True),
        ("CERTIFIED_SUPPLY_AND_LIQUIDITY_EVIDENCE", True, False),
        ("USER_PURCHASE_BUDGET", True, False),
        ("EXISTING_MTG_HOLDINGS", True, False),
        ("MINIMUM_PURCHASE_UNIT", True, False),
        ("TRANSACTION_COST_ASSUMPTIONS", True, False),
        ("TAX_ASSUMPTIONS", True, False),
        ("MAXIMUM_POSITION_CONCENTRATION", True, False),
        ("RISK_TOLERANCE_POLICY", True, False),
    ]
    input_rows = [
        {
            "input_name": name,
            "required": required,
            "certified_or_available": available,
            "blocking_if_missing": required,
        }
        for name, required, available in required_inputs
    ]

    authorization_rows = [
        {"capability": "RANKING_EXECUTION", "authorized": True},
        {"capability": "PURCHASE_ANALYSIS_INPUT_CERTIFICATION", "authorized": not failures},
        {"capability": "PURCHASE_ANALYSIS_EXECUTION", "authorized": False},
        {"capability": "PURCHASE_RECOMMENDATION", "authorized": False},
        {"capability": "AUTOMATIC_PURCHASE_EXECUTION", "authorized": False},
        {"capability": "UIP_DELIVERY", "authorized": False},
    ]
    execution_plan = [{
        "next_stage": contract["next_stage_if_certified"],
        "purpose": "CERTIFY_PURCHASE_ANALYSIS_INPUTS_AND_USER_CONSTRAINTS",
        "ranking_recomputation_required": False,
        "forecast_recomputation_required": False,
        "purchase_analysis_execution_performed": False,
        "purchase_recommendation_authorized": False,
    }]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["required_outputs"]
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    write_csv(OUTPUT_DIR / outputs["dimension_policy_csv"], dimension_rows, list(dimension_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["required_input_registry_csv"], input_rows, list(input_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["authorization_matrix_csv"], authorization_rows, list(authorization_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["execution_plan_csv"], execution_plan, list(execution_plan[0].keys()))

    status = "PASS" if not failures else "FAIL"
    summary = {
        "certification_status": status,
        **observed,
        "required_purchase_analysis_dimensions": len(dimension_rows),
        "required_purchase_analysis_inputs": len(input_rows),
        "currently_available_required_inputs": sum(1 for row in input_rows if row["certified_or_available"]),
        "purchase_analysis_execution_performed": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
        "ranking_recomputed": False,
        "forecast_recomputed": False,
        "critical_failures": failures,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_PURCHASE_ANALYSIS_READINESS_ARCHITECTURE",
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

    print("PASS_PRECOLLECTOR_PURCHASE_ANALYSIS_READINESS_ARCHITECTURE" if not failures else "FAIL_PRECOLLECTOR_PURCHASE_ANALYSIS_READINESS_ARCHITECTURE")
    print(f"GOVERNED_PRODUCTS={observed['governed_products']}")
    print(f"RANKED_PRODUCT_ROWS={observed['ranked_product_rows']}")
    print(f"PURCHASE_ANALYSIS_DIMENSIONS={len(dimension_rows)}")
    print(f"REQUIRED_PURCHASE_ANALYSIS_INPUTS={len(input_rows)}")
    print(f"CURRENTLY_AVAILABLE_REQUIRED_INPUTS={summary['currently_available_required_inputs']}")
    print("PURCHASE_ANALYSIS_EXECUTION_PERFORMED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
