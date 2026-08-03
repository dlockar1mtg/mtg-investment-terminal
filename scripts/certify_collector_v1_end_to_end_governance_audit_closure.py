from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_end_to_end_governance_audit_closure_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_end_to_end_governance_audit_closure"


def clean(value: Any) -> str:
    return str(value or "").strip()


def truthy(value: Any) -> bool:
    return value is True or clean(value).lower() in {"true", "1", "yes", "pass", "passed"}


def walk_values(value: Any, pointer: str = "$") -> list[tuple[str, str, Any]]:
    found: list[tuple[str, str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_pointer = f"{pointer}.{key}"
            found.append((child_pointer, clean(key), child))
            found.extend(walk_values(child, child_pointer))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(walk_values(child, f"{pointer}[{index}]"))
    return found


def payload_has_alias(payload: dict[str, Any], aliases: list[str], predicate) -> tuple[bool, list[str]]:
    matches: list[str] = []
    alias_set = {alias.lower() for alias in aliases}
    for pointer, key, value in walk_values(payload):
        if key.lower() in alias_set and predicate(value):
            matches.append(pointer)
    return bool(matches), matches


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []
    evidence_rows: list[dict[str, Any]] = []

    v2_path = ROOT / contract["v2_summary"]
    august_dir = ROOT / contract["august1_directory"]
    if not v2_path.is_file():
        raise SystemExit("V2_AUDIT_SUMMARY_MISSING")
    if not august_dir.is_dir():
        raise SystemExit("AUGUST1_CERTIFICATION_DIRECTORY_MISSING")

    v2 = json.loads(v2_path.read_text(encoding="utf-8"))
    for key, expected in contract["required_v2_counts"].items():
        observed = v2.get(key)
        if observed != expected:
            failures.append(f"V2_COUNT_MISMATCH:{key}:{observed}:{expected}")

    final_counts = v2.get("final_authority_counts", {})
    for key, expected in contract["required_final_authority_counts"].items():
        observed = final_counts.get(key)
        if observed != expected:
            failures.append(f"V2_FINAL_AUTHORITY_COUNT_MISMATCH:{key}:{observed}:{expected}")

    critical = v2.get("critical_failures", [])
    if critical != [contract["required_v2_critical_failure"]]:
        failures.append(f"V2_CRITICAL_FAILURE_SET_UNEXPECTED:{critical}")
    if v2.get("warnings", []) not in ([], None):
        failures.append(f"V2_WARNINGS_NOT_EMPTY:{v2.get('warnings')}")
    if v2.get("automatic_purchase_execution_authorized") is not False:
        failures.append("AUTOMATIC_PURCHASE_EXECUTION_NOT_FALSE")

    json_files = sorted(august_dir.rglob("*.json"))
    if not json_files:
        failures.append("AUGUST1_JSON_EVIDENCE_MISSING")

    snapshot_matches = 0
    certified_matches = 0
    rebuild_matches = 0
    source_hash_matches = 0
    explicit_failures: list[str] = []

    for path in json_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            failures.append(f"AUGUST1_JSON_PARSE_FAILED:{path.relative_to(ROOT).as_posix()}:{type(exc).__name__}")
            continue
        if not isinstance(payload, dict):
            continue

        flat = walk_values(payload)
        snapshot_ptrs = [pointer for pointer, key, value in flat if key.lower() == "snapshot_id" and clean(value) == contract["snapshot_id"]]
        certified, certified_ptrs = payload_has_alias(payload, contract["certification_flag_aliases"], truthy)
        rebuild, rebuild_ptrs = payload_has_alias(payload, contract["rebuild_authorization_aliases"], truthy)
        source_hash, source_hash_ptrs = payload_has_alias(
            payload,
            contract["source_hash_aliases"],
            lambda value: clean(value).lower() == contract["source_bundle_sha256"].lower(),
        )

        for pointer, key, value in flat:
            key_lower = key.lower()
            value_text = clean(value).upper()
            if key_lower in {"status", "certification_status", "result"} and value_text.startswith("FAIL"):
                explicit_failures.append(f"{path.relative_to(ROOT).as_posix()}:{pointer}:{value_text}")
            if key_lower == "critical_failures" and isinstance(value, list) and value:
                explicit_failures.append(f"{path.relative_to(ROOT).as_posix()}:{pointer}:{value}")

        snapshot_matches += int(bool(snapshot_ptrs))
        certified_matches += int(certified)
        rebuild_matches += int(rebuild)
        source_hash_matches += int(source_hash)
        evidence_rows.append({
            "relative_path": path.relative_to(ROOT).as_posix(),
            "snapshot_match": bool(snapshot_ptrs),
            "snapshot_pointers": "|".join(snapshot_ptrs),
            "certified_for_model_input": certified,
            "certification_pointers": "|".join(certified_ptrs),
            "model_rebuild_authorized": rebuild,
            "rebuild_pointers": "|".join(rebuild_ptrs),
            "source_bundle_hash_match": source_hash,
            "source_hash_pointers": "|".join(source_hash_ptrs),
        })

    if snapshot_matches < 1:
        failures.append("AUGUST1_SNAPSHOT_EVIDENCE_NOT_FOUND")
    if certified_matches < 1:
        failures.append("AUGUST1_MODEL_INPUT_CERTIFICATION_NOT_FOUND")
    if rebuild_matches < 1:
        failures.append("AUGUST1_MODEL_REBUILD_AUTHORIZATION_NOT_FOUND")
    if source_hash_matches < 1:
        failures.append("AUGUST1_SOURCE_BUNDLE_HASH_NOT_FOUND")
    if explicit_failures:
        failures.append(f"AUGUST1_EXPLICIT_FAILURE_EVIDENCE:{len(explicit_failures)}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    evidence_path = OUTPUT / "collector_august1_certification_evidence.json"
    evidence_path.write_text(json.dumps(evidence_rows, indent=2), encoding="utf-8")

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_END_TO_END_GOVERNANCE_AUDIT_CLOSURE"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "source_bundle_sha256": contract["source_bundle_sha256"],
        "v2_stages_audited": v2.get("stages_audited"),
        "v2_stages_passed_before_closure": v2.get("stages_passed"),
        "effective_stages_passed_after_closure": 11 if not failures else 10,
        "v2_hashes_checked": v2.get("declared_hashes_checked"),
        "v2_hashes_reconciled": v2.get("declared_hashes_reconciled_to_audited_inventory"),
        "standard_requirements_documented": v2.get("standard_requirements_documented"),
        "august1_json_files_reviewed": len(json_files),
        "august1_snapshot_evidence_files": snapshot_matches,
        "august1_model_input_certification_files": certified_matches,
        "august1_rebuild_authorization_files": rebuild_matches,
        "august1_source_hash_evidence_files": source_hash_matches,
        "august1_explicit_failure_evidence": explicit_failures,
        "final_authority_counts": final_counts,
        "conditional_products_purchase_authorized": v2.get("conditional_products_purchase_authorized"),
        "forecast_values_modified_in_purchase_authority": v2.get("forecast_values_modified_in_purchase_authority"),
        "automatic_purchase_execution_authorized": v2.get("automatic_purchase_execution_authorized"),
        "human_review_required": True,
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_end_to_end_governance_audit_closure_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
