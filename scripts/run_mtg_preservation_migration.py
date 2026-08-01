from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "config/mtg/governance/mtg_preservation_migration_v1.json"
DATA_SUFFIXES = {".csv", ".json", ".jsonl", ".parquet", ".duckdb", ".db", ".sqlite", ".xlsx", ".xls", ".zip", ".txt"}
FORECAST_TOKENS = {"forecast", "replay", "tournament", "prediction", "leaderboard", "model_run", "qualification"}
RAW_TOKENS = {"raw", "source", "input", "snapshot", "download", "export"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"


def is_excluded(relative: str, excluded_roots: list[str]) -> bool:
    normalized = relative.replace("\\", "/").lower()
    return any(normalized == root.lower().rstrip("/") or normalized.startswith(root.lower().rstrip("/") + "/") for root in excluded_roots)


def discover_files(cfg: dict) -> list[Path]:
    found: dict[str, Path] = {}
    for root_text in cfg["source_roots"]:
        source_root = ROOT / root_text
        if not source_root.exists():
            continue
        for path in source_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in DATA_SUFFIXES:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if is_excluded(rel, cfg["excluded_source_roots"]):
                continue
            found[rel] = path
    return [found[key] for key in sorted(found)]


def classify(relative_path: str) -> tuple[str, str]:
    lower = relative_path.lower()
    name = Path(relative_path).name.lower()
    if any(token in lower or token in name for token in FORECAST_TOKENS):
        return "INVALIDATED", "forecast_or_validation_output_requires_recertification"
    if any(token in lower or token in name for token in RAW_TOKENS):
        return "RAW", "source_like_dataset_preserved_as_raw_candidate"
    return "UNVERIFIED", "existing_dataset_requires_lineage_and_semantic_certification"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    commit = git_commit()
    now = utc_now()

    vault_root = ROOT / cfg["vault_root"]
    manifest_root = ROOT / cfg["manifest_root"]
    registry_path = ROOT / cfg["registry_path"]
    lineage_path = ROOT / cfg["lineage_path"]
    classification_path = ROOT / cfg["classification_path"]
    orphan_path = ROOT / cfg["orphan_report_path"]
    summary_path = ROOT / cfg["summary_path"]

    for directory in [vault_root, manifest_root, registry_path.parent, lineage_path.parent, classification_path.parent, orphan_path.parent, summary_path.parent]:
        directory.mkdir(parents=True, exist_ok=True)

    discovered = discover_files(cfg)
    copied = 0
    reused = 0
    hash_mismatches = 0
    manifest_rows: list[dict[str, object]] = []
    classification_rows: list[dict[str, object]] = []

    existing_registry = read_csv_rows(registry_path)
    registry_by_id = {(row.get("dataset_id", ""), row.get("dataset_version", "")): row for row in existing_registry}

    for source in discovered:
        rel = source.relative_to(ROOT).as_posix()
        source_hash = sha256(source)
        ingestion_id = f"sha256-{source_hash[:16]}"
        destination = vault_root / ingestion_id / rel
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            destination_hash = sha256(destination)
            if destination_hash != source_hash:
                failures.append(f"vault_hash_conflict:{rel}:{ingestion_id}")
                hash_mismatches += 1
                continue
            reused += 1
        else:
            shutil.copy2(source, destination)
            destination_hash = sha256(destination)
            if destination_hash != source_hash:
                failures.append(f"copy_hash_mismatch:{rel}:{ingestion_id}")
                hash_mismatches += 1
                destination.unlink(missing_ok=True)
                continue
            copied += 1

        state, reason = classify(rel)
        dataset_id = "mtg-file-" + hashlib.sha256(rel.encode("utf-8")).hexdigest()[:20]
        dataset_version = ingestion_id
        manifest = {
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "dataset_state": state,
            "source_relative_path": rel,
            "vault_relative_path": destination.relative_to(ROOT).as_posix(),
            "source_sha256": source_hash,
            "vault_sha256": destination_hash,
            "size_bytes": source.stat().st_size,
            "copied_at": now,
            "copy_only": True,
            "source_preserved_in_place": True,
            "builder_commit": commit,
            "classification_reason": reason,
        }
        manifest_path = manifest_root / ingestion_id / (hashlib.sha256(rel.encode("utf-8")).hexdigest()[:20] + ".manifest.json")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if manifest_path.exists():
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing_manifest.get("source_sha256") != source_hash or existing_manifest.get("source_relative_path") != rel:
                failures.append(f"manifest_conflict:{rel}:{ingestion_id}")
        else:
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        manifest_rows.append(manifest)
        classification_rows.append({
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "relative_path": rel,
            "dataset_state": state,
            "classification_reason": reason,
            "content_sha256": source_hash,
            "review_required": state != "RAW",
        })

        key = (dataset_id, dataset_version)
        if key not in registry_by_id:
            registry_by_id[key] = {
                "dataset_id": dataset_id,
                "dataset_version": dataset_version,
                "dataset_state": state,
                "created_at": now,
                "created_by": "scripts/run_mtg_preservation_migration.py",
                "schema_version": "UNASSESSED",
                "row_count": "UNASSESSED",
                "column_count": "UNASSESSED",
                "content_sha256": source_hash,
                "parent_dataset_ids": "",
                "parent_content_sha256": "",
                "builder_script": "PRESERVED_EXISTING_FILE",
                "builder_commit": commit,
                "certification_report": "",
                "promotion_status": "NOT_CERTIFIED",
            }

    registry_fields = [
        "dataset_id", "dataset_version", "dataset_state", "created_at", "created_by",
        "schema_version", "row_count", "column_count", "content_sha256",
        "parent_dataset_ids", "parent_content_sha256", "builder_script", "builder_commit",
        "certification_report", "promotion_status",
    ]
    write_csv(registry_path, registry_fields, list(registry_by_id.values()))

    classification_fields = [
        "dataset_id", "dataset_version", "relative_path", "dataset_state",
        "classification_reason", "content_sha256", "review_required",
    ]
    write_csv(classification_path, classification_fields, classification_rows)

    lineage_fields = [
        "child_dataset_id", "child_version", "parent_dataset_id", "parent_version",
        "parent_sha256", "relationship_type", "registered_at",
    ]
    if not lineage_path.exists():
        write_csv(lineage_path, lineage_fields, [])

    orphan_rows = [
        {
            "dataset_id": row["dataset_id"],
            "dataset_version": row["dataset_version"],
            "relative_path": row["relative_path"],
            "issue": "NO_REGISTERED_PARENT_LINEAGE",
            "severity": "EXPECTED_FOR_RAW" if row["dataset_state"] == "RAW" else "REVIEW_REQUIRED",
        }
        for row in classification_rows
    ]
    write_csv(orphan_path, ["dataset_id", "dataset_version", "relative_path", "issue", "severity"], orphan_rows)

    manifest_index = manifest_root / "preservation_manifest_index.csv"
    write_csv(
        manifest_index,
        [
            "dataset_id", "dataset_version", "dataset_state", "source_relative_path",
            "vault_relative_path", "source_sha256", "vault_sha256", "size_bytes",
            "copied_at", "copy_only", "source_preserved_in_place", "builder_commit",
            "classification_reason",
        ],
        manifest_rows,
    )

    if not discovered:
        failures.append("no_data_files_discovered")
    if hash_mismatches:
        failures.append("hash_verification_failures")

    summary = {
        "audit_name": cfg["program_name"],
        "audit_version": cfg["program_version"],
        "discovered_file_count": len(discovered),
        "vault_copy_created_count": copied,
        "vault_copy_reused_count": reused,
        "hash_mismatch_count": hash_mismatches,
        "registered_dataset_count": len(registry_by_id),
        "classified_dataset_count": len(classification_rows),
        "raw_classification_count": sum(1 for row in classification_rows if row["dataset_state"] == "RAW"),
        "invalidated_classification_count": sum(1 for row in classification_rows if row["dataset_state"] == "INVALIDATED"),
        "unverified_classification_count": sum(1 for row in classification_rows if row["dataset_state"] == "UNVERIFIED"),
        "source_files_deleted": 0,
        "source_files_moved": 0,
        "source_files_overwritten": 0,
        "copy_only": True,
        "hash_verification_required": True,
        "forecasting_resume_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
