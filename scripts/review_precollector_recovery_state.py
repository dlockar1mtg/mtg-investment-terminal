from __future__ import annotations

import csv
import hashlib
import json
import os
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_recovery_owner_review_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/recovery_owner_review"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_from_zip(archive: zipfile.ZipFile, suffix: str) -> list[dict]:
    matches = [name for name in archive.namelist() if name.endswith(suffix)]
    if len(matches) != 1:
        raise RuntimeError(f"EXPECTED_ONE_ZIP_MEMBER:{suffix}:{len(matches)}")
    with archive.open(matches[0]) as handle:
        text = handle.read().decode("utf-8-sig")
    return list(csv.DictReader(text.splitlines()))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    contract = load_json(CONTRACT_PATH)
    package = Path(os.environ.get("PRECOLLECTOR_RECOVERY_AUDIT_PACKAGE", Path(os.environ.get("TEMP", ".")) / contract["required_recovery_audit_package"]["package_name"]))
    if not package.is_file():
        raise RuntimeError(f"RECOVERY_AUDIT_PACKAGE_MISSING:{package}")
    actual_hash = sha256_file(package)
    expected_hash = contract["required_recovery_audit_package"]["sha256"]
    if actual_hash != expected_hash:
        raise RuntimeError(f"RECOVERY_AUDIT_PACKAGE_HASH_DRIFT:{actual_hash}")

    with zipfile.ZipFile(package) as archive:
        inventory = read_csv_from_zip(archive, "precollector_recovery_artifact_inventory.csv")
        candidates = read_csv_from_zip(archive, "precollector_recovery_control_point_candidates.csv")
        remaining = read_csv_from_zip(archive, "precollector_recovery_remaining_work.csv")

    stage_counts: dict[str, Counter] = defaultdict(Counter)
    for row in inventory:
        stage_counts[row["stage"]][row["classification"]] += 1

    stage_summary = []
    for stage in sorted(stage_counts):
        counts = stage_counts[stage]
        stage_summary.append({
            "stage": stage,
            "artifact_count": sum(counts.values()),
            "binding_governance": counts.get("BINDING_GOVERNANCE", 0),
            "authentic_authority": counts.get("AUTHENTIC_PRECOLLECTOR_AUTHORITY", 0),
            "authentic_implementation": counts.get("AUTHENTIC_PRECOLLECTOR_IMPLEMENTATION", 0),
            "requires_owner_review": counts.get("REQUIRES_OWNER_REVIEW", 0),
            "reusable_requires_rebinding": counts.get("REUSABLE_ARCHITECTURE_REQUIRES_REBINDING", 0),
            "quarantined_cross_lane_output": counts.get("QUARANTINED_CROSS_LANE_OUTPUT", 0),
            "unresolved": counts.get("UNRESOLVED", 0),
        })

    control_points = []
    stage_order = ["GOVERNANCE", "UNIVERSE", "COMPARABLES", "MODEL_SELECTION", "UNCERTAINTY", "FORECAST"]
    last_evidence_stage = "NONE"
    for stage in stage_order:
        source = next((row for row in candidates if row["stage"] == stage), None)
        count = int(source["non_quarantined_artifact_count"]) if source else 0
        if count > 0:
            last_evidence_stage = stage
        control_points.append({
            "stage": stage,
            "non_quarantined_artifact_count": count,
            "evidence_present": str(count > 0).upper(),
            "owner_certification_status": "REQUIRES_OWNER_REVIEW",
            "eligible_as_restart_point": "CANDIDATE" if count > 0 else "NO",
            "downstream_execution_authorized": "FALSE",
        })

    reusable = [row for row in inventory if row["classification"] == "REUSABLE_ARCHITECTURE_REQUIRES_REBINDING"]
    quarantined = [row for row in inventory if row["introduced_in_quarantined_range"] == "TRUE"]

    reviewed_remaining = []
    for row in remaining:
        reviewed_remaining.append({
            **row,
            "owner_review_disposition": "REQUIRED_BEFORE_EXECUTION",
        })
    reviewed_remaining.extend([
        {"sequence": 7, "work_item": "Install executable target-lane and target-identity gate in every downstream pre-Collector stage", "status": "REQUIRED", "blocking": "TRUE", "owner_review_disposition": "MANDATORY_GOVERNANCE_REPAIR"},
        {"sequence": 8, "work_item": "Produce owner-facing product-level universe and comparable evidence review", "status": "REQUIRED", "blocking": "TRUE", "owner_review_disposition": "MANDATORY_OWNER_CHECKPOINT"},
    ])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    names = contract["required_outputs"]
    write_csv(OUTPUT_DIR / names[0], stage_summary, list(stage_summary[0].keys()))
    write_csv(OUTPUT_DIR / names[1], control_points, list(control_points[0].keys()))
    write_csv(OUTPUT_DIR / names[2], reusable, list(inventory[0].keys()))
    write_csv(OUTPUT_DIR / names[3], quarantined, list(inventory[0].keys()))
    write_csv(OUTPUT_DIR / names[4], reviewed_remaining, list(reviewed_remaining[0].keys()))

    summary = {
        "status": "PASS_PRECOLLECTOR_RECOVERY_OWNER_REVIEW",
        "governed_lane": contract["governed_lane"],
        "audit_package_sha256": actual_hash,
        "inventory_artifacts": len(inventory),
        "quarantined_artifacts": len(quarantined),
        "reusable_architecture_artifacts": len(reusable),
        "last_non_quarantined_evidence_stage": last_evidence_stage,
        "authentic_control_point_certified": False,
        "owner_decision_required": True,
        "forecast_execution_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    (OUTPUT_DIR / names[5]).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "input_package_sha256": actual_hash,
        "outputs": {p.name: sha256_file(p) for p in sorted(OUTPUT_DIR.iterdir()) if p.is_file()},
    }
    (OUTPUT_DIR / names[6]).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_RECOVERY_OWNER_REVIEW")
    print(f"INVENTORY_ARTIFACTS={len(inventory)}")
    print(f"QUARANTINED_ARTIFACTS={len(quarantined)}")
    print(f"REUSABLE_ARCHITECTURE_ARTIFACTS={len(reusable)}")
    print(f"LAST_NON_QUARANTINED_EVIDENCE_STAGE={last_evidence_stage}")
    print("AUTHENTIC_CONTROL_POINT_CERTIFIED=FALSE")
    print("OWNER_DECISION_REQUIRED=TRUE")
    print("FORECAST_EXECUTION_AUTHORIZED=FALSE")
    print("RANKING_EXECUTION_AUTHORIZED=FALSE")
    print("PURCHASE_ANALYSIS_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={contract['next_stage_if_certified']}")


if __name__ == "__main__":
    main()
