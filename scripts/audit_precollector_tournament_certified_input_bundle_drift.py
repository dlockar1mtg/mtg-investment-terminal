from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_tournament_certified_input_bundle_drift_gate_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/tournament_certified_input_bundle_drift_gate"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_member(name: str, patterns: dict[str, list[str]]) -> list[str]:
    lowered = name.casefold()
    return [role for role, tokens in patterns.items() if any(token.casefold() in lowered for token in tokens)]


def csv_row_count(payload: bytes) -> int:
    text = payload.decode("utf-8-sig", errors="replace")
    return max(sum(1 for _ in csv.reader(io.StringIO(text))) - 1, 0)


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    temp_root = Path(tempfile.gettempdir())
    diagnostics: list[dict[str, str]] = []
    package_rows: list[dict[str, object]] = []
    artifact_rows: list[dict[str, object]] = []
    located_roles: set[str] = set()

    for package in contract["required_certified_packages"]:
        path = temp_root / package["package_name"]
        exists = path.is_file()
        actual_hash = sha256_file(path) if exists else ""
        hash_match = exists and actual_hash == package["sha256"]
        package_rows.append({
            "package_name": package["package_name"],
            "package_path": str(path),
            "exists": exists,
            "expected_sha256": package["sha256"],
            "actual_sha256": actual_hash,
            "sha256_match": hash_match,
        })
        if not exists:
            diagnostics.append({"severity": "BLOCKING", "code": "CERTIFIED_PACKAGE_MISSING", "detail": package["package_name"]})
            continue
        if not hash_match:
            diagnostics.append({"severity": "BLOCKING", "code": "CERTIFIED_PACKAGE_HASH_DRIFT", "detail": package["package_name"]})
            continue
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                roles = classify_member(member.filename, contract["artifact_role_patterns"])
                if not roles:
                    continue
                payload = archive.read(member)
                row_count = csv_row_count(payload) if member.filename.casefold().endswith(".csv") else ""
                for role in roles:
                    located_roles.add(role)
                    artifact_rows.append({
                        "artifact_role": role,
                        "package_name": package["package_name"],
                        "member_name": member.filename,
                        "member_sha256": hashlib.sha256(payload).hexdigest(),
                        "row_count": row_count,
                    })

    # Search other existing certified Pre-Collector packages only for authorities not included in the three fixed packages.
    for path in sorted(temp_root.glob("MTG_PreCollector_*.zip")):
        if any(row["package_path"] == str(path) for row in package_rows):
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    roles = classify_member(member.filename, contract["artifact_role_patterns"])
                    if not roles:
                        continue
                    payload = archive.read(member)
                    row_count = csv_row_count(payload) if member.filename.casefold().endswith(".csv") else ""
                    for role in roles:
                        located_roles.add(role)
                        artifact_rows.append({
                            "artifact_role": role,
                            "package_name": path.name,
                            "member_name": member.filename,
                            "member_sha256": hashlib.sha256(payload).hexdigest(),
                            "row_count": row_count,
                        })
        except zipfile.BadZipFile:
            diagnostics.append({"severity": "WARNING", "code": "UNREADABLE_NONREQUIRED_PACKAGE", "detail": path.name})

    for role in contract["required_artifact_roles"]:
        if role not in located_roles:
            diagnostics.append({"severity": "BLOCKING", "code": "CERTIFIED_ARTIFACT_ROLE_MISSING", "detail": role})

    expected = contract["expected_counts"]
    role_expected_rows = {
        "ACTIVE_PRODUCT_UNIVERSE": expected["active_products"],
        "PRODUCT_HORIZON_MATRIX": expected["product_horizon_rows"],
        "HORIZON_ARCHITECTURE": expected["forecast_horizons"],
        "APPROVED_COMPARABLE_LEDGER": expected["approved_comparable_rows"],
    }
    for role, expected_rows in role_expected_rows.items():
        rows = [int(item["row_count"]) for item in artifact_rows if item["artifact_role"] == role and item["row_count"] != ""]
        if rows and expected_rows not in rows:
            diagnostics.append({"severity": "BLOCKING", "code": "CERTIFIED_ARTIFACT_CARDINALITY_DRIFT", "detail": f"{role}:expected={expected_rows}:observed={sorted(set(rows))}"})

    blocking = sum(1 for row in diagnostics if row["severity"] == "BLOCKING")
    status = "PASS" if blocking == 0 else "REVIEW_REQUIRED"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def write_csv(name: str, rows: list[dict[str, object]], columns: list[str]) -> None:
        with (OUTPUT_DIR / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    write_csv("precollector_tournament_certified_package_inventory.csv", package_rows,
              ["package_name", "package_path", "exists", "expected_sha256", "actual_sha256", "sha256_match"])
    write_csv("precollector_tournament_certified_artifact_inventory.csv", artifact_rows,
              ["artifact_role", "package_name", "member_name", "member_sha256", "row_count"])
    write_csv("precollector_tournament_certified_input_diagnostics.csv", diagnostics,
              ["severity", "code", "detail"])

    summary = {
        "certification_status": status,
        "required_package_rows": len(package_rows),
        "hash_verified_package_rows": sum(1 for row in package_rows if row["sha256_match"]),
        "required_artifact_role_count": len(contract["required_artifact_roles"]),
        "located_artifact_role_count": len(located_roles),
        "blocking_diagnostic_rows": blocking,
        "recursive_upstream_rebuild_performed": False,
        "live_network_collection_performed": False,
        "next_stage": contract["next_stage_if_pass"] if status == "PASS" else "REPAIR_OR_RESTORE_CERTIFIED_INPUT_AUTHORITIES",
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "uip_delivery_authorized": False,
    }
    (OUTPUT_DIR / "precollector_tournament_certified_input_drift_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print("PASS_PRECOLLECTOR_TOURNAMENT_CERTIFIED_INPUT_BUNDLE_DRIFT_GATE" if status == "PASS" else "REVIEW_PRECOLLECTOR_TOURNAMENT_CERTIFIED_INPUT_BUNDLE_DRIFT_GATE")
    print(f"REQUIRED_PACKAGE_ROWS={len(package_rows)}")
    print(f"HASH_VERIFIED_PACKAGE_ROWS={summary['hash_verified_package_rows']}")
    print(f"REQUIRED_ARTIFACT_ROLE_COUNT={summary['required_artifact_role_count']}")
    print(f"LOCATED_ARTIFACT_ROLE_COUNT={summary['located_artifact_role_count']}")
    print(f"BLOCKING_DIAGNOSTIC_ROWS={blocking}")
    print("RECURSIVE_UPSTREAM_REBUILD_PERFORMED=FALSE")
    print("LIVE_NETWORK_COLLECTION_PERFORMED=FALSE")
    print(f"NEXT_STAGE={summary['next_stage']}")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
