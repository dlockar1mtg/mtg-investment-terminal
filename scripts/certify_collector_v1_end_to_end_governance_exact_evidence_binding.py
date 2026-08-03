from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_end_to_end_governance_exact_evidence_binding_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_end_to_end_governance_exact_evidence_binding"


def clean(value: Any) -> str:
    return str(value or "").strip()


def truthy(value: Any) -> bool:
    return value is True or clean(value).lower() in {"true", "1", "yes", "pass", "passed"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def walk(value: Any, pointer: str = "$") -> list[tuple[str, str, Any]]:
    rows: list[tuple[str, str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_pointer = f"{pointer}.{key}"
            rows.append((child_pointer, clean(key), child))
            rows.extend(walk(child, child_pointer))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(walk(child, f"{pointer}[{index}]"))
    return rows


def alias_matches(payload: dict[str, Any], aliases: list[str], predicate) -> list[str]:
    alias_set = {alias.lower() for alias in aliases}
    return [pointer for pointer, key, value in walk(payload) if key.lower() in alias_set and predicate(value)]


def structured_failures(payload: dict[str, Any], relative: str) -> list[str]:
    failures: list[str] = []
    for pointer, key, value in walk(payload):
        key_lower = key.lower()
        if key_lower in {"status", "certification_status", "result"} and clean(value).upper().startswith("FAIL"):
            failures.append(f"{relative}:{pointer}:{clean(value)}")
        if key_lower == "critical_failures" and isinstance(value, list) and value:
            failures.append(f"{relative}:{pointer}:{value}")
    return failures


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []
    evidence_audit: list[dict[str, Any]] = []

    v2_path = ROOT / contract["v2_summary"]
    if not v2_path.is_file():
        raise SystemExit("V2_AUDIT_SUMMARY_MISSING")
    v2 = json.loads(v2_path.read_text(encoding="utf-8"))

    for key, expected in contract["required_v2_counts"].items():
        observed = v2.get(key)
        if observed != expected:
            failures.append(f"V2_COUNT_MISMATCH:{key}:{observed}:{expected}")

    if v2.get("critical_failures") != [contract["required_v2_critical_failure"]]:
        failures.append(f"V2_CRITICAL_FAILURE_SET_UNEXPECTED:{v2.get('critical_failures')}")
    if v2.get("warnings", []) not in ([], None):
        failures.append(f"V2_WARNINGS_NOT_EMPTY:{v2.get('warnings')}")
    if v2.get("automatic_purchase_execution_authorized") is not False:
        failures.append("AUTOMATIC_PURCHASE_EXECUTION_NOT_FALSE")

    final_counts = v2.get("final_authority_counts", {})
    for key, expected in contract["required_final_authority_counts"].items():
        observed = final_counts.get(key)
        if observed != expected:
            failures.append(f"FINAL_AUTHORITY_COUNT_MISMATCH:{key}:{observed}:{expected}")

    snapshot_matches: list[str] = []
    source_hash_matches: list[str] = []
    certification_matches: list[str] = []
    rebuild_matches: list[str] = []
    evidence_hashes: dict[str, str] = {}
    evidence_structured_failures: list[str] = []

    for relative in contract["evidence_files"]:
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"EXACT_EVIDENCE_FILE_MISSING:{relative}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            failures.append(f"EXACT_EVIDENCE_JSON_PARSE_FAILED:{relative}:{type(exc).__name__}")
            continue
        if not isinstance(payload, dict):
            failures.append(f"EXACT_EVIDENCE_ROOT_NOT_OBJECT:{relative}")
            continue

        flat = walk(payload)
        snapshot_ptrs = [pointer for pointer, key, value in flat if key.lower() == "snapshot_id" and clean(value) == contract["snapshot_id"]]
        source_ptrs = alias_matches(payload, contract["source_hash_aliases"], lambda value: clean(value).lower() == contract["source_bundle_sha256"].lower())
        certification_ptrs = alias_matches(payload, contract["certification_flag_aliases"], truthy)
        rebuild_ptrs = alias_matches(payload, contract["rebuild_authorization_aliases"], truthy)
        structured = structured_failures(payload, relative)

        snapshot_matches.extend(f"{relative}:{pointer}" for pointer in snapshot_ptrs)
        source_hash_matches.extend(f"{relative}:{pointer}" for pointer in source_ptrs)
        certification_matches.extend(f"{relative}:{pointer}" for pointer in certification_ptrs)
        rebuild_matches.extend(f"{relative}:{pointer}" for pointer in rebuild_ptrs)
        evidence_structured_failures.extend(structured)
        evidence_hashes[relative] = sha256(path)
        evidence_audit.append({
            "relative_path": relative,
            "sha256": evidence_hashes[relative],
            "snapshot_match": bool(snapshot_ptrs),
            "snapshot_pointers": snapshot_ptrs,
            "source_hash_match": bool(source_ptrs),
            "source_hash_pointers": source_ptrs,
            "model_input_certified": bool(certification_ptrs),
            "certification_pointers": certification_ptrs,
            "model_rebuild_authorized": bool(rebuild_ptrs),
            "rebuild_pointers": rebuild_ptrs,
            "structured_failures": structured,
        })

    if not snapshot_matches:
        failures.append("EXACT_SNAPSHOT_EVIDENCE_NOT_FOUND")
    if not source_hash_matches:
        failures.append("EXACT_SOURCE_HASH_EVIDENCE_NOT_FOUND")
    if not certification_matches:
        failures.append("EXACT_MODEL_INPUT_CERTIFICATION_NOT_FOUND")
    if not rebuild_matches:
        failures.append("EXACT_MODEL_REBUILD_AUTHORIZATION_NOT_FOUND")
    if evidence_structured_failures:
        failures.append(f"EXACT_EVIDENCE_STRUCTURED_FAILURES:{len(evidence_structured_failures)}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "collector_exact_august1_evidence_audit.json").write_text(json.dumps(evidence_audit, indent=2), encoding="utf-8")

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_END_TO_END_GOVERNANCE_EXACT_EVIDENCE_BINDING"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "source_bundle_sha256": contract["source_bundle_sha256"],
        "exact_evidence_files_required": len(contract["evidence_files"]),
        "exact_evidence_files_verified": len(evidence_audit),
        "snapshot_evidence_matches": len(snapshot_matches),
        "source_hash_evidence_matches": len(source_hash_matches),
        "model_input_certification_matches": len(certification_matches),
        "model_rebuild_authorization_matches": len(rebuild_matches),
        "structured_failure_evidence": evidence_structured_failures,
        "evidence_file_hashes": evidence_hashes,
        "v2_stages_audited": v2.get("stages_audited"),
        "v2_stages_passed_before_binding": v2.get("stages_passed"),
        "effective_stages_passed_after_binding": 11 if not failures else 10,
        "v2_hashes_checked": v2.get("declared_hashes_checked"),
        "v2_hashes_reconciled": v2.get("declared_hashes_reconciled_to_audited_inventory"),
        "standard_requirements_documented": v2.get("standard_requirements_documented"),
        "final_authority_counts": final_counts,
        "conditional_products_purchase_authorized": v2.get("conditional_products_purchase_authorized"),
        "forecast_values_modified_in_purchase_authority": v2.get("forecast_values_modified_in_purchase_authority"),
        "automatic_purchase_execution_authorized": v2.get("automatic_purchase_execution_authorized"),
        "human_review_required": True,
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_end_to_end_governance_exact_evidence_binding_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
