from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_recovery_state_audit_contract_v1.json"
RECOVERY_DECISION_PATH = ROOT / "config/mtg/governance/precollector_lane_boundary_and_recovery_decision_v1.json"
SCOPE_PATH = ROOT / "config/mtg/governance/precollector_booster_product_scope_owner_decision_v1.json"
RECONCILIATION_PATH = ROOT / "config/mtg/standards/precollector_universe_reconciliation_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/recovery_state_audit"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"GIT_FAILED:{' '.join(args)}:{result.stderr.strip()}")
    return result.stdout.strip()


def introducing_commit(path: str) -> str:
    value = git("log", "--diff-filter=A", "--format=%H", "--", path)
    return value.splitlines()[-1] if value else "UNKNOWN"


def commit_in_range(commit: str, base_exclusive: str, head_inclusive: str) -> bool:
    if commit == "UNKNOWN":
        return False
    ancestors = git("rev-list", f"{base_exclusive}..{head_inclusive}").splitlines()
    return commit in set(ancestors)


def classify(path: str, content: str, quarantined: bool) -> tuple[str, str]:
    lowered = f"{path}\n{content}".casefold()
    if path in {
        str(RECOVERY_DECISION_PATH.relative_to(ROOT)).replace("\\", "/"),
        str(SCOPE_PATH.relative_to(ROOT)).replace("\\", "/"),
        str(RECONCILIATION_PATH.relative_to(ROOT)).replace("\\", "/"),
    }:
        return "BINDING_GOVERNANCE", "Binding recovery, scope, or reconciliation authority"
    if quarantined:
        if path.startswith(("scripts/", "tests/", "config/mtg/standards/")):
            return "REUSABLE_ARCHITECTURE_REQUIRES_REBINDING", "Introduced in quarantined range; code or contract may be reusable only after lane rebinding"
        return "QUARANTINED_CROSS_LANE_OUTPUT", "Introduced in quarantined range"
    if "collector_v1" in lowered and ("target" in lowered or "foundation" in lowered or "current_foundation" in lowered):
        return "UNRESOLVED", "Potential Collector target-authority binding requires owner review"
    if any(token in lowered for token in ("candidate_universe", "universe_reconciliation", "reconciled_candidate_universe")):
        return "AUTHENTIC_PRECOLLECTOR_AUTHORITY", "Pre-Collector universe or reconciliation authority"
    if any(token in lowered for token in ("comparable", "winner_uncertainty", "forecast_route", "model_selection")):
        return "AUTHENTIC_PRECOLLECTOR_IMPLEMENTATION", "Pre-Collector comparable, route, winner, or uncertainty implementation/evidence"
    if "precollector" in lowered or "pre-collector" in lowered:
        return "REQUIRES_OWNER_REVIEW", "Pre-Collector-related artifact requiring control-point classification"
    return "UNRESOLVED", "Unable to classify automatically"


def stage_for(path: str, content: str) -> str:
    lowered = f"{path}\n{content}".casefold()
    stages = (
        ("GOVERNANCE", ("governance", "owner_decision", "scope")),
        ("UNIVERSE", ("candidate_universe", "universe_reconciliation", "reconciled_candidate")),
        ("COMPARABLES", ("comparable", "similarity")),
        ("MODEL_SELECTION", ("model_selection", "winner")),
        ("UNCERTAINTY", ("uncertainty",)),
        ("FORECAST", ("forecast", "monte_carlo")),
        ("RANKING", ("ranking",)),
        ("PURCHASE", ("purchase",)),
        ("HANDOFF", ("handoff", "control_point", "certification")),
    )
    for stage, tokens in stages:
        if any(token in lowered for token in tokens):
            return stage
    return "OTHER"


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    contract = load_json(CONTRACT_PATH)
    recovery = load_json(RECOVERY_DECISION_PATH)
    scope = load_json(SCOPE_PATH)
    reconciliation = load_json(RECONCILIATION_PATH)

    if scope.get("governed_lane") != "precollector_booster_boxes":
        raise RuntimeError("PRECOLLECTOR_SCOPE_LANE_MISMATCH")
    if "Collector Booster boxes" not in scope.get("excluded_product_families", []):
        raise RuntimeError("COLLECTOR_TARGET_EXCLUSION_MISSING")
    if reconciliation.get("next_stage_if_certified") != "OWNER_REVIEW_OF_RECONCILED_UNIVERSE_AND_SOURCE_HIERARCHY":
        raise RuntimeError("RECONCILIATION_OWNER_REVIEW_CHECKPOINT_MISSING")

    base = recovery["quarantined_commit_range"]["base_exclusive"]
    head = recovery["quarantined_commit_range"]["head_inclusive"]
    paths = [p for p in git("ls-files").splitlines() if "precollector" in p.casefold() or "pre-collector" in p.casefold()]

    inventory: list[dict] = []
    for path in sorted(paths):
        file_path = ROOT / path
        content = ""
        if file_path.is_file() and file_path.suffix.casefold() in {".json", ".py", ".ps1", ".md", ".txt", ".yml", ".yaml", ".csv"}:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        commit = introducing_commit(path)
        quarantined = commit_in_range(commit, base, head)
        classification, reason = classify(path, content, quarantined)
        inventory.append({
            "path": path,
            "stage": stage_for(path, content),
            "introducing_commit": commit,
            "introduced_in_quarantined_range": str(quarantined).upper(),
            "classification": classification,
            "classification_reason": reason,
            "contains_collector_v1": str("collector_v1" in content.casefold()).upper(),
            "sha256": sha256_file(file_path) if file_path.is_file() else "",
        })

    authority_paths = [
        RECOVERY_DECISION_PATH,
        SCOPE_PATH,
        RECONCILIATION_PATH,
        ROOT / "config/mtg/standards/precollector_candidate_universe_inventory_contract_v1.json",
        ROOT / "docs/standards/mtg/MTG_FORECASTING_STANDARD.md",
    ]
    authorities = []
    for path in authority_paths:
        authorities.append({
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "exists": str(path.is_file()).upper(),
            "sha256": sha256_file(path) if path.is_file() else "",
            "role": "BINDING" if path in {RECOVERY_DECISION_PATH, SCOPE_PATH, RECONCILIATION_PATH} else "REQUIRED_REFERENCE",
        })

    quarantine = [row for row in inventory if row["introduced_in_quarantined_range"] == "TRUE"]
    candidates = []
    for stage in ("GOVERNANCE", "UNIVERSE", "COMPARABLES", "MODEL_SELECTION", "UNCERTAINTY", "FORECAST"):
        stage_rows = [row for row in inventory if row["stage"] == stage and row["introduced_in_quarantined_range"] == "FALSE"]
        candidates.append({
            "stage": stage,
            "non_quarantined_artifact_count": len(stage_rows),
            "candidate_status": "EVIDENCE_EXISTS_REQUIRES_OWNER_REVIEW" if stage_rows else "NO_NON_QUARANTINED_EVIDENCE_FOUND",
            "forecast_or_downstream_authorized": "FALSE",
        })

    remaining_work = [
        {"sequence": 1, "work_item": "Owner review of reconciled pre-Collector universe and source hierarchy", "status": "REQUIRED", "blocking": "TRUE"},
        {"sequence": 2, "work_item": "Certify target universe identity hash and product count", "status": "REQUIRED", "blocking": "TRUE"},
        {"sequence": 3, "work_item": "Certify Collector comparables as explicitly typed reference rows only", "status": "REQUIRED", "blocking": "TRUE"},
        {"sequence": 4, "work_item": "Determine last authentic comparable/model/uncertainty control point", "status": "REQUIRED", "blocking": "TRUE"},
        {"sequence": 5, "work_item": "Rebind reusable forecast architecture to authentic pre-Collector targets", "status": "PENDING_AUDIT", "blocking": "TRUE"},
        {"sequence": 6, "work_item": "Execute only missing forecast, uncertainty, ranking, and finalization stages", "status": "NOT_AUTHORIZED", "blocking": "TRUE"},
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT_DIR / contract["required_outputs"][0], inventory, list(inventory[0].keys()) if inventory else ["path"])
    write_csv(OUTPUT_DIR / contract["required_outputs"][1], authorities, ["path", "exists", "sha256", "role"])
    write_csv(OUTPUT_DIR / contract["required_outputs"][2], quarantine, list(inventory[0].keys()) if inventory else ["path"])
    write_csv(OUTPUT_DIR / contract["required_outputs"][3], candidates, ["stage", "non_quarantined_artifact_count", "candidate_status", "forecast_or_downstream_authorized"])
    write_csv(OUTPUT_DIR / contract["required_outputs"][4], remaining_work, ["sequence", "work_item", "status", "blocking"])

    summary = {
        "status": "PASS_PRECOLLECTOR_RECOVERY_STATE_AUDIT",
        "governed_lane": scope["governed_lane"],
        "inventory_artifacts": len(inventory),
        "quarantined_artifacts": len(quarantine),
        "non_quarantined_artifacts": len(inventory) - len(quarantine),
        "collector_targets_prohibited": True,
        "reconciliation_owner_review_required": True,
        "authentic_control_point_owner_approval_required": True,
        "forecast_execution_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    (OUTPUT_DIR / contract["required_outputs"][5]).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "contract_path": str(CONTRACT_PATH.relative_to(ROOT)).replace("\\", "/"),
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "recovery_decision_sha256": sha256_file(RECOVERY_DECISION_PATH),
        "scope_authority_sha256": sha256_file(SCOPE_PATH),
        "reconciliation_authority_sha256": sha256_file(RECONCILIATION_PATH),
        "outputs": {p.name: sha256_file(p) for p in sorted(OUTPUT_DIR.iterdir()) if p.is_file()},
    }
    (OUTPUT_DIR / contract["required_outputs"][6]).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_RECOVERY_STATE_AUDIT")
    print(f"INVENTORY_ARTIFACTS={len(inventory)}")
    print(f"QUARANTINED_ARTIFACTS={len(quarantine)}")
    print(f"NON_QUARANTINED_ARTIFACTS={len(inventory) - len(quarantine)}")
    print("COLLECTOR_TARGETS_PROHIBITED=TRUE")
    print("RECONCILIATION_OWNER_REVIEW_REQUIRED=TRUE")
    print("FORECAST_EXECUTION_AUTHORIZED=FALSE")
    print("RANKING_EXECUTION_AUTHORIZED=FALSE")
    print("PURCHASE_ANALYSIS_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={contract['next_stage_if_certified']}")


if __name__ == "__main__":
    main()
