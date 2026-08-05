from __future__ import annotations

import csv
import hashlib
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_forecast_control_point_owner_review_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/forecast_control_point_owner_review"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(archive: zipfile.ZipFile, suffix: str) -> list[dict]:
    names = [name for name in archive.namelist() if name.endswith(suffix)]
    if len(names) != 1:
        raise RuntimeError(f"EXPECTED_ONE_MEMBER:{suffix}:{len(names)}")
    return list(csv.DictReader(archive.read(names[0]).decode("utf-8-sig").splitlines()))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    contract = load_json(CONTRACT_PATH)
    default = Path(os.environ.get("TEMP", ".")) / contract["required_validation_package"]["package_name"]
    package = Path(os.environ.get("PRECOLLECTOR_FORECAST_CONTROL_POINT_VALIDATION_PACKAGE", default))
    if not package.is_file():
        raise RuntimeError(f"VALIDATION_PACKAGE_MISSING:{package}")
    actual_hash = sha256_file(package)
    expected_hash = contract["required_validation_package"]["sha256"]
    if actual_hash != expected_hash:
        raise RuntimeError(f"VALIDATION_PACKAGE_HASH_DRIFT:{actual_hash}")

    with zipfile.ZipFile(package) as archive:
        blockers = read_csv(archive, "precollector_forecast_control_point_blockers.csv")
        artifact_rows = read_csv(archive, "precollector_forecast_control_point_artifact_validation.csv")
        authority_rows = read_csv(archive, "precollector_forecast_control_point_authority_validation.csv")

    critical = [row for row in blockers if str(row.get("severity", "")).upper() == "CRITICAL"]
    if len(critical) != 1:
        raise RuntimeError(f"EXPECTED_ONE_CRITICAL_BLOCKER:{len(critical)}")

    blocker = critical[0]
    combined = " ".join(str(v) for v in blocker.values()).casefold()
    if "collector" in combined and "target" in combined:
        category = "INVALID_COLLECTOR_TARGET_BINDING"
        repair = "Replace the target authority with the certified pre-Collector universe and retain Collector rows only as explicitly typed comparables."
    elif "authority" in combined or "identity" in combined or "universe" in combined:
        category = "MISSING_PRECOLLECTOR_AUTHORITY_PROOF"
        repair = "Bind the forecast control point to the certified pre-Collector universe identity, count, and hash."
    else:
        category = "UNRESOLVED_FORECAST_CONTROL_POINT_BLOCKER"
        repair = "Inspect the named artifact and repair its target-lane, identity, and lineage declarations before reuse."

    affected_paths = []
    for row in artifact_rows + authority_rows:
        text = " ".join(str(v) for v in row.values()).casefold()
        if any(token in text for token in ("block", "fail", "invalid", "missing", "unresolved")):
            affected_paths.append(row.get("path") or row.get("authority_path") or row.get("artifact") or "")
    affected_paths = sorted({path for path in affected_paths if path})

    reviewed_blocker = [{
        **blocker,
        "owner_review_category": category,
        "repair_instruction": repair,
        "affected_path_count": len(affected_paths),
        "affected_paths": "|".join(affected_paths),
    }]
    disposition = [{
        "decision": "REPAIR_REQUIRED",
        "blocker_category": category,
        "control_point_validated": "FALSE",
        "forecast_execution_authorized": "FALSE",
        "ranking_execution_authorized": "FALSE",
        "purchase_analysis_authorized": "FALSE",
        "next_stage": contract["next_stage_if_certified"],
    }]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    names = contract["required_outputs"]
    write_csv(OUTPUT_DIR / names[0], reviewed_blocker, list(reviewed_blocker[0].keys()))
    write_csv(OUTPUT_DIR / names[1], disposition, list(disposition[0].keys()))

    summary = {
        "status": "PASS_PRECOLLECTOR_FORECAST_CONTROL_POINT_OWNER_REVIEW",
        "validation_package_sha256": actual_hash,
        "critical_blockers": len(critical),
        "blocker_category": category,
        "control_point_validated": False,
        "repair_required": True,
        "forecast_execution_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    (OUTPUT_DIR / names[2]).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "input_package_sha256": actual_hash,
        "outputs": {p.name: sha256_file(p) for p in sorted(OUTPUT_DIR.iterdir()) if p.is_file()},
    }
    (OUTPUT_DIR / names[3]).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_FORECAST_CONTROL_POINT_OWNER_REVIEW")
    print(f"CRITICAL_BLOCKERS={len(critical)}")
    print(f"BLOCKER_CATEGORY={category}")
    print(f"AFFECTED_PATHS={len(affected_paths)}")
    print("CONTROL_POINT_VALIDATED=FALSE")
    print("REPAIR_REQUIRED=TRUE")
    print("FORECAST_EXECUTION_AUTHORIZED=FALSE")
    print("RANKING_EXECUTION_AUTHORIZED=FALSE")
    print("PURCHASE_ANALYSIS_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={contract['next_stage_if_certified']}")


if __name__ == "__main__":
    main()
