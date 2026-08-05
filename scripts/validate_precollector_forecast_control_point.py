from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_forecast_control_point_validation_contract_v1.json"
APPROVAL = ROOT / "config/mtg/governance/precollector_forecast_control_point_owner_approval_v1.json"
OUTPUT = ROOT / "artifacts/precollector/forecast_control_point_validation"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"GIT_FAILED:{' '.join(args)}:{result.stderr.strip()}")
    return result.stdout.strip()


def introduced_commit(path: str) -> str:
    value = git("log", "--diff-filter=A", "--format=%H", "--", path)
    return value.splitlines()[-1] if value else "UNKNOWN"


def in_quarantine(commit: str, base: str, head: str) -> bool:
    return commit != "UNKNOWN" and commit in set(git("rev-list", f"{base}..{head}").splitlines())


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    contract = load_json(CONTRACT)
    approval = load_json(APPROVAL)
    if approval.get("approved_restart_stage") != "FORECAST_CONTROL_POINT_VALIDATION":
        raise RuntimeError("OWNER_APPROVAL_RESTART_STAGE_MISMATCH")

    package = Path(os.environ.get("PRECOLLECTOR_CONTROL_POINT_EVIDENCE_PACKAGE", Path(os.environ.get("TEMP", ".")) / contract["required_evidence_package"]["package_name"]))
    if not package.is_file():
        raise RuntimeError(f"CONTROL_POINT_EVIDENCE_PACKAGE_MISSING:{package}")
    actual_hash = sha256_file(package)
    if actual_hash != contract["required_evidence_package"]["sha256"]:
        raise RuntimeError(f"CONTROL_POINT_EVIDENCE_PACKAGE_HASH_DRIFT:{actual_hash}")
    with zipfile.ZipFile(package) as z:
        if not any(name.endswith("precollector_authentic_control_point_evidence_summary.json") for name in z.namelist()):
            raise RuntimeError("CONTROL_POINT_EVIDENCE_SUMMARY_MISSING")

    base = contract["quarantined_commit_range"]["base_exclusive"]
    head = contract["quarantined_commit_range"]["head_inclusive"]
    tracked = git("ls-files").splitlines()
    paths = [p for p in tracked if "precollector" in p.casefold() and ("forecast" in p.casefold() or "monte_carlo" in p.casefold())]

    artifacts: list[dict] = []
    blockers: list[dict] = []
    reuse: list[dict] = []
    authorities: list[dict] = []

    approved_authority_tokens = (
        "precollector_candidate_universe",
        "precollector_universe_reconciliation",
        "precollector_reconciled_candidate_universe",
        "precollector_booster_product_scope_owner_decision",
    )
    forbidden_target_tokens = ("collector_v1", "secret_lair")

    for path in sorted(paths):
        file_path = ROOT / path
        content = file_path.read_text(encoding="utf-8", errors="replace") if file_path.is_file() else ""
        lowered = content.casefold()
        commit = introduced_commit(path)
        quarantined = in_quarantine(commit, base, head)
        has_precollector_authority = any(t in lowered for t in approved_authority_tokens)
        has_collector_v1 = "collector_v1" in lowered
        explicit_comparable_role = any(t in lowered for t in ("comparable", "reference_lane", "reference_product"))
        invalid_collector_target = has_collector_v1 and any(t in lowered for t in ("target", "current_foundation", "target_authority", "target_universe")) and not explicit_comparable_role
        status = "VALIDATION_CANDIDATE"
        reason = "Non-quarantined forecast artifact requires exact authority review"
        if quarantined:
            status = "QUARANTINED_REUSABLE_ONLY"
            reason = "Introduced in quarantined cross-lane range"
        elif invalid_collector_target:
            status = "REJECTED_COLLECTOR_TARGET_BINDING"
            reason = "Collector v1 appears in a target-authority context"
        elif has_precollector_authority:
            status = "PRECOLLECTOR_AUTHORITY_REFERENCE_PRESENT"
            reason = "References a governed pre-Collector scope or universe authority"
        elif has_collector_v1 and explicit_comparable_role:
            status = "COLLECTOR_COMPARABLE_REFERENCE_REQUIRES_ROW_VALIDATION"
            reason = "Collector reference appears comparable-related but must be proven at row level"

        row = {
            "path": path,
            "introducing_commit": commit,
            "introduced_in_quarantined_range": str(quarantined).upper(),
            "contains_precollector_authority": str(has_precollector_authority).upper(),
            "contains_collector_v1": str(has_collector_v1).upper(),
            "explicit_comparable_role_language": str(explicit_comparable_role).upper(),
            "invalid_collector_target_binding": str(invalid_collector_target).upper(),
            "validation_status": status,
            "validation_reason": reason,
            "sha256": sha256_file(file_path) if file_path.is_file() else "",
        }
        artifacts.append(row)
        if quarantined:
            reuse.append({"path": path, "reuse_disposition": "REBIND_AND_RETEST_CODE_ONLY", "authoritative_output": "FALSE"})
        if invalid_collector_target:
            blockers.append({"blocker": "COLLECTOR_TARGET_AUTHORITY_BINDING", "path": path, "severity": "CRITICAL", "resolution": "Remove target binding; Collector may remain only as explicitly typed comparable evidence"})

    authority_paths = [
        "config/mtg/governance/precollector_booster_product_scope_owner_decision_v1.json",
        "config/mtg/standards/precollector_candidate_universe_inventory_contract_v1.json",
        "config/mtg/standards/precollector_universe_reconciliation_contract_v1.json",
        "config/mtg/governance/precollector_forecast_control_point_owner_approval_v1.json",
    ]
    for path in authority_paths:
        p = ROOT / path
        authorities.append({"path": path, "exists": str(p.is_file()).upper(), "sha256": sha256_file(p) if p.is_file() else "", "binding_role": "REQUIRED"})
        if not p.is_file():
            blockers.append({"blocker": "REQUIRED_AUTHORITY_MISSING", "path": path, "severity": "CRITICAL", "resolution": "Restore binding authority"})

    non_quarantined = [r for r in artifacts if r["introduced_in_quarantined_range"] == "FALSE"]
    precollector_bound = [r for r in non_quarantined if r["contains_precollector_authority"] == "TRUE"]
    if not non_quarantined:
        blockers.append({"blocker": "NO_NON_QUARANTINED_FORECAST_ARTIFACTS", "path": "", "severity": "CRITICAL", "resolution": "Identify authentic forecast control point"})
    if not precollector_bound:
        blockers.append({"blocker": "NO_EXPLICIT_PRECOLLECTOR_TARGET_AUTHORITY_BINDING", "path": "", "severity": "CRITICAL", "resolution": "Bind forecast control point to approved pre-Collector universe identity"})

    OUTPUT.mkdir(parents=True, exist_ok=True)
    names = contract["required_outputs"]
    write_csv(OUTPUT / names[0], artifacts, list(artifacts[0].keys()) if artifacts else ["path"])
    write_csv(OUTPUT / names[1], authorities, ["path", "exists", "sha256", "binding_role"])
    write_csv(OUTPUT / names[2], blockers, ["blocker", "path", "severity", "resolution"])
    write_csv(OUTPUT / names[3], reuse, ["path", "reuse_disposition", "authoritative_output"])

    summary = {
        "status": "PASS_PRECOLLECTOR_FORECAST_CONTROL_POINT_VALIDATION",
        "governed_lane": contract["governed_lane"],
        "evidence_package_sha256": actual_hash,
        "forecast_artifacts_reviewed": len(artifacts),
        "non_quarantined_forecast_artifacts": len(non_quarantined),
        "quarantined_forecast_artifacts": len(artifacts) - len(non_quarantined),
        "explicit_precollector_authority_artifacts": len(precollector_bound),
        "critical_blockers": len([b for b in blockers if b["severity"] == "CRITICAL"]),
        "control_point_validated": len(blockers) == 0,
        "forecast_execution_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    (OUTPUT / names[4]).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    manifest = {"contract_sha256": sha256_file(CONTRACT), "owner_approval_sha256": sha256_file(APPROVAL), "input_package_sha256": actual_hash, "outputs": {p.name: sha256_file(p) for p in sorted(OUTPUT.iterdir()) if p.is_file()}}
    (OUTPUT / names[5]).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_FORECAST_CONTROL_POINT_VALIDATION")
    print(f"FORECAST_ARTIFACTS_REVIEWED={len(artifacts)}")
    print(f"NON_QUARANTINED_FORECAST_ARTIFACTS={len(non_quarantined)}")
    print(f"QUARANTINED_FORECAST_ARTIFACTS={len(artifacts) - len(non_quarantined)}")
    print(f"EXPLICIT_PRECOLLECTOR_AUTHORITY_ARTIFACTS={len(precollector_bound)}")
    print(f"CRITICAL_BLOCKERS={summary['critical_blockers']}")
    print(f"CONTROL_POINT_VALIDATED={str(summary['control_point_validated']).upper()}")
    print("FORECAST_EXECUTION_AUTHORIZED=FALSE")
    print("RANKING_EXECUTION_AUTHORIZED=FALSE")
    print("PURCHASE_ANALYSIS_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={contract['next_stage_if_certified']}")


if __name__ == "__main__":
    main()
