from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "config/mtg/governance/mtg_system_control_index_v1.json"
REQUIRED_SCOPES = {"collector_booster", "pre_collector", "secret_lair", "uip_connection"}
REQUIRED_FIELDS = {
    "certification_status",
    "certified_version",
    "certification_commit",
    "active_file_allowlist",
    "authoritative_pipeline_map",
    "data_source_and_lineage_map",
    "model_and_parameter_version_map",
    "owner_approval_register",
    "archive_manifest",
    "deletion_manifest",
    "prohibited_path_register",
    "daily_operations_runbook",
    "backtest_and_recalibration_runbook",
    "certification_history",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    if not INDEX_PATH.exists():
        failures.append(f"Missing index: {INDEX_PATH}")
        data = {}
    else:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    scopes = data.get("scopes", {})
    if set(scopes) != REQUIRED_SCOPES:
        failures.append("Scope set does not match the four required MTG certification scopes.")

    for scope_name, scope in scopes.items():
        missing = REQUIRED_FIELDS - set(scope)
        if missing:
            failures.append(f"{scope_name} missing fields: {sorted(missing)}")

    global_rules = data.get("global_rules", {})
    required_true = [
        "active_inputs_must_be_allowlisted",
        "unlisted_inputs_fail_closed",
        "archive_paths_prohibited_for_active_discovery",
        "repair_input_paths_prohibited_for_active_discovery",
        "superseded_model_paths_prohibited_for_active_discovery",
        "cleanup_requires_post_cleanup_recertification",
        "deletion_requires_owner_approval",
    ]
    for key in required_true:
        if global_rules.get(key) is not True:
            failures.append(f"Global rule must be true: {key}")

    summary = {
        "audit_name": "MTG System Control Index Audit",
        "audit_version": "1.0.0",
        "scope_count": len(scopes),
        "required_review_before_future_mtg_work": data.get("required_review_before_future_mtg_work"),
        "collector_certification_status": scopes.get("collector_booster", {}).get("certification_status"),
        "all_scopes_certified": all(
            scope.get("certification_status") == "CERTIFIED_POST_CLEANUP"
            for scope in scopes.values()
        ) if scopes else False,
        "failure_count": len(failures),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
        "governing_note": "This audit validates the permanent control-index structure. It does not certify a lane or authorize cleanup.",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
