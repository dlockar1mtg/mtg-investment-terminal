from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/governance/mtg_certified_pipeline_repository_hygiene_v1.json"


def audit() -> dict:
    failures: list[str] = []
    if not CONTRACT.exists():
        failures.append(f"Missing contract: {CONTRACT.relative_to(ROOT)}")
        return {"status": "FAIL", "failure_count": 1, "failures": failures}

    data = json.loads(CONTRACT.read_text(encoding="utf-8"))

    required_scopes = {
        "COLLECTOR_BOOSTER",
        "PRE_COLLECTOR_BOOSTER",
        "SECRET_LAIR",
        "MTG_TO_UIP_INTERFACE",
    }
    if set(data.get("scope", [])) != required_scopes:
        failures.append("Contract must cover all three MTG lanes and the UIP interface.")

    dispositions = data.get("disposition_classes", {})
    required_dispositions = {
        "ACTIVE_CERTIFIED",
        "ACTIVE_SUPPORTING",
        "ARCHIVE_READ_ONLY",
        "DELETE_CANDIDATE",
        "PROTECTED_NEVER_DELETE",
        "OWNER_REVIEW_REQUIRED",
    }
    if not required_dispositions.issubset(dispositions):
        failures.append("Disposition taxonomy is incomplete.")

    deletion = data.get("deletion_controls", {})
    if deletion.get("automatic_deletion_allowed") is not False:
        failures.append("Automatic deletion must remain prohibited.")
    if deletion.get("owner_approval_required") is not True:
        failures.append("Owner approval must be required before deletion.")
    if deletion.get("archive_first_default") is not True:
        failures.append("Archive-first must be the default disposition.")

    discovery = data.get("active_discovery_controls", {})
    if discovery.get("allowlist_required") is not True:
        failures.append("Certified production discovery must use an allowlist.")
    if discovery.get("recursive_repository_guessing_prohibited_after_certification") is not True:
        failures.append("Repository-wide guessing must be prohibited after certification.")
    if discovery.get("production_scripts_must_fail_closed_on_unlisted_inputs") is not True:
        failures.append("Production must fail closed on unlisted inputs.")

    docs = set(data.get("permanent_documentation_requirements", []))
    required_docs = {
        "system_control_index",
        "certified_active_file_allowlist",
        "authoritative_pipeline_map",
        "data_source_and_lineage_map",
        "owner_approval_register",
        "archive_manifest",
        "deletion_manifest",
        "prohibited_path_register",
        "daily_operations_runbook",
        "backtest_and_recalibration_runbook",
        "UIP_interface_contract",
    }
    if not required_docs.issubset(docs):
        failures.append("Permanent documentation requirements are incomplete.")

    state = data.get("current_state", {})
    if state.get("cleanup_execution_authorized") is not False:
        failures.append("Cleanup execution must remain unauthorized before final certification.")

    return {
        "audit_name": "MTG Certified Pipeline Repository Hygiene Audit",
        "audit_version": "1.0.0",
        "scope_count": len(data.get("scope", [])),
        "disposition_class_count": len(dispositions),
        "permanent_document_requirement_count": len(docs),
        "archive_first_default": deletion.get("archive_first_default"),
        "automatic_deletion_allowed": deletion.get("automatic_deletion_allowed"),
        "owner_approval_required_for_deletion": deletion.get("owner_approval_required"),
        "active_allowlist_required": discovery.get("allowlist_required"),
        "repository_guessing_prohibited_after_certification": discovery.get(
            "recursive_repository_guessing_prohibited_after_certification"
        ),
        "cleanup_execution_authorized": state.get("cleanup_execution_authorized"),
        "failure_count": len(failures),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
        "governing_note": (
            "This audit validates the cleanup and documentation contract only. "
            "It does not archive or delete files and does not certify any lane."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = audit()
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.strict and result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
