from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTITUTION = ROOT / "config/mtg/governance/mtg_data_preservation_constitution_v1.json"

DIRECTORIES = [
    "data_vault/raw/mtg/collector_booster",
    "data_vault/manifests/mtg/collector_booster",
    "data/governance/permanence/inventory",
    "data/governance/permanence/registry",
    "data/governance/permanence/lineage",
    "data/governance/permanence/quarantine",
    "data/governance/permanence/certification",
    "data/governance/permanence/restore_tests",
    "data/candidate/mtg/collector_booster",
    "data/certified/mtg/collector_booster",
    "data/model_runs/mtg/collector_booster",
]

REGISTRY_COLUMNS = [
    "dataset_id",
    "dataset_version",
    "dataset_state",
    "created_at",
    "created_by",
    "schema_version",
    "row_count",
    "column_count",
    "content_sha256",
    "parent_dataset_ids",
    "parent_content_sha256",
    "builder_script",
    "builder_commit",
    "certification_report",
    "promotion_status",
]

LINEAGE_COLUMNS = [
    "child_dataset_id",
    "child_version",
    "parent_dataset_id",
    "parent_version",
    "parent_sha256",
    "relationship_type",
    "registered_at",
]


def create_once(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize MTG append-only data permanence directories and registries.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    created_directories: list[str] = []
    created_files: list[str] = []

    if not CONSTITUTION.exists():
        failures.append("data_preservation_constitution_missing")
    else:
        constitution = json.loads(CONSTITUTION.read_text(encoding="utf-8"))
        if constitution.get("effective_status") != "STOP_THE_LINE_ACTIVE":
            failures.append("stop_the_line_not_active")
        if constitution.get("authorization", {}).get("forecasting_resume_authorized") is not False:
            failures.append("forecasting_resume_must_remain_closed")

    for relative in DIRECTORIES:
        path = ROOT / relative
        if not path.exists():
            path.mkdir(parents=True, exist_ok=False)
            created_directories.append(relative)

    registry_path = ROOT / "data/governance/permanence/registry/dataset_registry.csv"
    lineage_path = ROOT / "data/governance/permanence/lineage/dataset_lineage.csv"
    registry_header = ",".join(REGISTRY_COLUMNS) + "\n"
    lineage_header = ",".join(LINEAGE_COLUMNS) + "\n"
    if create_once(registry_path, registry_header):
        created_files.append(registry_path.relative_to(ROOT).as_posix())
    if create_once(lineage_path, lineage_header):
        created_files.append(lineage_path.relative_to(ROOT).as_posix())

    readme = ROOT / "data_vault/README.md"
    readme_text = """# Immutable MTG Data Vault\n\nThis directory is append-only. Existing ingestion folders and files must never be edited, overwritten, moved, or deleted by project pipelines. Each ingestion must use a unique ingestion ID and include an original file, manifest, checksums, and source metadata. Models and feature builders may read registered vault inputs but may not write into this directory.\n"""
    if create_once(readme, readme_text):
        created_files.append(readme.relative_to(ROOT).as_posix())

    guard = ROOT / "data_vault/APPEND_ONLY_GUARD.json"
    guard_payload = {
        "guard_version": "1.0.0",
        "policy": "APPEND_ONLY_NO_OVERWRITE_NO_DELETE",
        "downstream_writeback_forbidden": True,
        "existing_ingestion_mutation_forbidden": True,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    if create_once(guard, json.dumps(guard_payload, indent=2, sort_keys=True)):
        created_files.append(guard.relative_to(ROOT).as_posix())

    result = {
        "program": "MTG Data Permanence Foundation Initializer",
        "version": "1.0.0",
        "created_directory_count": len(created_directories),
        "created_directories": created_directories,
        "created_file_count": len(created_files),
        "created_files": created_files,
        "existing_files_overwritten": 0,
        "existing_files_deleted": 0,
        "existing_files_moved": 0,
        "forecasting_resume_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }
    output = ROOT / "data/governance/permanence/registry/foundation_initialization_summary.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
