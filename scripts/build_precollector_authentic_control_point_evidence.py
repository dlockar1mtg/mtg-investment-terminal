from __future__ import annotations

import csv
import hashlib
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_authentic_control_point_evidence_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/authentic_control_point_evidence"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(archive: zipfile.ZipFile, suffix: str) -> list[dict]:
    names = [n for n in archive.namelist() if n.endswith(suffix)]
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
    default = Path(os.environ.get("TEMP", ".")) / contract["required_owner_review_package"]["package_name"]
    package = Path(os.environ.get("PRECOLLECTOR_OWNER_REVIEW_PACKAGE", default))
    if not package.is_file():
        raise RuntimeError(f"OWNER_REVIEW_PACKAGE_MISSING:{package}")
    actual = sha256_file(package)
    expected = contract["required_owner_review_package"]["sha256"]
    if actual != expected:
        raise RuntimeError(f"OWNER_REVIEW_PACKAGE_HASH_DRIFT:{actual}")

    with zipfile.ZipFile(package) as archive:
        stage_summary = read_csv(archive, "precollector_recovery_owner_review_stage_summary.csv")
        control_points = read_csv(archive, "precollector_recovery_owner_review_control_point_candidates.csv")
        reusable = read_csv(archive, "precollector_recovery_owner_review_reusable_architecture.csv")
        quarantined = read_csv(archive, "precollector_recovery_owner_review_quarantined_outputs.csv")

    forecast_stage = next((r for r in control_points if r.get("stage") == "FORECAST"), None)
    if not forecast_stage or forecast_stage.get("evidence_present") != "TRUE":
        raise RuntimeError("NON_QUARANTINED_FORECAST_EVIDENCE_NOT_FOUND")

    forecast_artifacts = []
    for row in reusable + quarantined:
        if row.get("stage") == "FORECAST":
            forecast_artifacts.append({
                "path": row.get("path", ""),
                "classification": row.get("classification", ""),
                "introduced_in_quarantined_range": row.get("introduced_in_quarantined_range", ""),
                "contains_collector_v1": row.get("contains_collector_v1", ""),
                "introducing_commit": row.get("introducing_commit", ""),
                "sha256": row.get("sha256", ""),
                "control_point_role": "QUARANTINED_REUSABLE_ONLY" if row.get("introduced_in_quarantined_range") == "TRUE" else "NON_QUARANTINED_EVIDENCE",
            })

    stage_row = next((r for r in stage_summary if r.get("stage") == "FORECAST"), {})
    dependencies = [
        {"dependency": "OWNER_APPROVED_PRECOLLECTOR_SCOPE", "required": "TRUE", "status": "PRESENT", "evidence": "precollector_booster_product_scope_owner_decision_v1.json"},
        {"dependency": "CERTIFIED_PRECOLLECTOR_UNIVERSE", "required": "TRUE", "status": "REQUIRES_EXACT_IDENTITY_CONFIRMATION", "evidence": "candidate universe and reconciliation authorities exist"},
        {"dependency": "TYPED_COLLECTOR_COMPARABLE_REFERENCES", "required": "TRUE", "status": "REQUIRES_ROW_LEVEL_CONFIRMATION", "evidence": "comparable/model/uncertainty evidence exists outside quarantine"},
        {"dependency": "FORECAST_TARGET_LANE_BINDING", "required": "TRUE", "status": "REQUIRES_EXACT_ARTIFACT_REVIEW", "evidence": f"non-quarantined forecast evidence count={forecast_stage.get('non_quarantined_artifact_count', '0')}; stage artifacts={stage_row.get('artifact_count', '0')}"},
        {"dependency": "QUARANTINED_OUTPUT_EXCLUSION", "required": "TRUE", "status": "ENFORCED", "evidence": "26 quarantined artifacts remain unauthorized"},
    ]

    risks = [
        {"risk": "FORECAST_STAGE_CLASSIFICATION_IS_ARTIFACT_LEVEL_NOT_PRODUCT_LEVEL", "severity": "HIGH", "disposition": "DO_NOT_AUTO_CERTIFY"},
        {"risk": "NON_QUARANTINED_FORECAST_ARTIFACTS_MAY_INCLUDE_ARCHITECTURE_WITHOUT_VALID_OUTPUT", "severity": "HIGH", "disposition": "VERIFY_EXACT_PATHS_AND_INPUT_AUTHORITIES"},
        {"risk": "COLLECTOR_V1_REFERENCE_MAY_BE_VALID_COMPARABLE_OR_INVALID_TARGET", "severity": "HIGH", "disposition": "REQUIRE_EXPLICIT_TARGET_VS_COMPARABLE_ROLE_REVIEW"},
        {"risk": "UNIVERSE_IDENTITY_HASH_NOT_YET_OWNER_CERTIFIED", "severity": "HIGH", "disposition": "BLOCK_EXECUTION"},
    ]

    recommendation = {
        "recommended_restart_stage": "FORECAST_CONTROL_POINT_VALIDATION",
        "reason": "Non-quarantined evidence exists through FORECAST, but the audit does not yet prove that a complete product-level forecast output is correctly bound to the approved pre-Collector target universe.",
        "do_not_restart_from": ["GOVERNANCE", "UNIVERSE", "COMPARABLES"],
        "preserve_as_completed_subject_to_identity_validation": ["GOVERNANCE", "UNIVERSE", "COMPARABLES", "MODEL_SELECTION", "UNCERTAINTY"],
        "owner_approval_recommended_now": False,
        "next_owner_decision": "Approve or reject FORECAST_CONTROL_POINT_VALIDATION as the governed restart stage after reviewing exact artifact paths and target/comparable role evidence.",
        "forecast_execution_authorized": False,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    names = contract["required_outputs"]
    write_csv(OUTPUT_DIR / names[0], forecast_artifacts, list(forecast_artifacts[0].keys()) if forecast_artifacts else ["path"])
    write_csv(OUTPUT_DIR / names[1], dependencies, ["dependency", "required", "status", "evidence"])
    write_csv(OUTPUT_DIR / names[2], risks, ["risk", "severity", "disposition"])
    (OUTPUT_DIR / names[3]).write_text(json.dumps(recommendation, indent=2) + "\n", encoding="utf-8")

    summary = {
        "status": "PASS_PRECOLLECTOR_AUTHENTIC_CONTROL_POINT_EVIDENCE",
        "owner_review_package_sha256": actual,
        "last_non_quarantined_evidence_stage": "FORECAST",
        "recommended_restart_stage": "FORECAST_CONTROL_POINT_VALIDATION",
        "forecast_artifact_rows": len(forecast_artifacts),
        "authentic_control_point_certified": False,
        "owner_approval_required": True,
        "forecast_execution_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    (OUTPUT_DIR / names[4]).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    manifest = {"contract_sha256": sha256_file(CONTRACT_PATH), "input_package_sha256": actual, "outputs": {p.name: sha256_file(p) for p in sorted(OUTPUT_DIR.iterdir()) if p.is_file()}}
    (OUTPUT_DIR / names[5]).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_AUTHENTIC_CONTROL_POINT_EVIDENCE")
    print("LAST_NON_QUARANTINED_EVIDENCE_STAGE=FORECAST")
    print("RECOMMENDED_RESTART_STAGE=FORECAST_CONTROL_POINT_VALIDATION")
    print(f"FORECAST_ARTIFACT_ROWS={len(forecast_artifacts)}")
    print("AUTHENTIC_CONTROL_POINT_CERTIFIED=FALSE")
    print("OWNER_APPROVAL_REQUIRED=TRUE")
    print("FORECAST_EXECUTION_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={contract['next_stage_if_certified']}")


if __name__ == "__main__":
    main()
