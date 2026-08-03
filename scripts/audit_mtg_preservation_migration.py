from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "config/mtg/governance/mtg_preservation_migration_v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    manifest_index = ROOT / cfg["manifest_root"] / "preservation_manifest_index.csv"
    registry_path = ROOT / cfg["registry_path"]
    classification_path = ROOT / cfg["classification_path"]
    summary_path = ROOT / cfg["summary_path"]

    manifests = rows(manifest_index)
    registry = rows(registry_path)
    classifications = rows(classification_path)

    if not manifests:
        failures.append("manifest_index_missing_or_empty")
    if not registry:
        failures.append("dataset_registry_missing_or_empty")
    if not classifications:
        failures.append("classification_registry_missing_or_empty")

    registry_keys = {(row.get("dataset_id", ""), row.get("dataset_version", "")) for row in registry}
    duplicate_manifest_keys = 0
    missing_registry = 0
    missing_sources = 0
    missing_vault = 0
    source_hash_mismatch = 0
    vault_hash_mismatch = 0
    source_vault_mismatch = 0
    seen: set[tuple[str, str]] = set()

    for row in manifests:
        key = (row.get("dataset_id", ""), row.get("dataset_version", ""))
        if key in seen:
            duplicate_manifest_keys += 1
        seen.add(key)
        if key not in registry_keys:
            missing_registry += 1

        source = ROOT / row.get("source_relative_path", "")
        vault = ROOT / row.get("vault_relative_path", "")
        if not source.exists():
            missing_sources += 1
            continue
        if not vault.exists():
            missing_vault += 1
            continue

        actual_source = sha256(source)
        actual_vault = sha256(vault)
        if actual_source != row.get("source_sha256"):
            source_hash_mismatch += 1
        if actual_vault != row.get("vault_sha256"):
            vault_hash_mismatch += 1
        if actual_source != actual_vault:
            source_vault_mismatch += 1

    if duplicate_manifest_keys:
        failures.append("duplicate_manifest_dataset_keys")
    if missing_registry:
        failures.append("manifest_datasets_missing_from_registry")
    if missing_sources:
        failures.append("preserved_source_files_now_missing")
    if missing_vault:
        failures.append("vault_files_missing")
    if source_hash_mismatch:
        failures.append("source_hash_changed_after_preservation")
    if vault_hash_mismatch:
        failures.append("vault_hash_changed_after_preservation")
    if source_vault_mismatch:
        failures.append("source_vault_content_mismatch")

    invalid_certified = [
        row for row in registry
        if row.get("dataset_state") == "CERTIFIED" and row.get("promotion_status") != "CERTIFIED"
    ]
    if invalid_certified:
        failures.append("improper_certified_registry_entries")

    result = {
        "audit_name": "MTG Preservation Migration Audit",
        "audit_version": "1.0.0",
        "manifest_count": len(manifests),
        "registry_count": len(registry),
        "classification_count": len(classifications),
        "duplicate_manifest_key_count": duplicate_manifest_keys,
        "manifest_missing_registry_count": missing_registry,
        "missing_source_count": missing_sources,
        "missing_vault_count": missing_vault,
        "source_hash_mismatch_count": source_hash_mismatch,
        "vault_hash_mismatch_count": vault_hash_mismatch,
        "source_vault_mismatch_count": source_vault_mismatch,
        "improper_certified_entry_count": len(invalid_certified),
        "source_files_deleted": 0,
        "source_files_moved": 0,
        "source_files_overwritten": 0,
        "forecasting_resume_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }
    output = ROOT / "data/governance/permanence/certification/preservation_migration_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
