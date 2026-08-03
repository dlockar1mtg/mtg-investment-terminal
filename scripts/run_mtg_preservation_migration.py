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
    return any(
        normalized == root.lower().rstrip("/")
        or normalized.startswith(root.lower().rstrip("/") + "/")
        for root in excluded_roots
    )


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


def compact_destination(vault_root: Path, ingestion_id: str, relative_path: str, suffix: str) -> Path:
    path_hash = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:24]
    safe_suffix = suffix.lower() if suffix else ".bin"
    return vault_root / ingestion_id / f"object-{path_hash}{safe_suffix}"


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
    missing_source_path = summary_path.parent / "preservation_migration_missing_sources.csv"
    copy_error_path = summary_path.parent / "preservation_migration_copy_errors.csv"

    for directory in [
        vault_root,
        manifest_root,
        registry_path.parent,
        lineage_path.parent,
        classification_path.parent,
        orphan_path.parent,
        summary_path.parent,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    discovered = discover_files(cfg)
    copied = 0
    reused = 0
    hash_mismatches = 0
    missing_sources: list[dict[str, object]] = []
    copy_errors: list[dict[str, object]] = []
    manifest_rows: list[dict[str, object]] = []
    classification_rows: list[dict[str, object]] = []

    existing_registry = read_csv_rows(registry_path)
    registry_by_id = {
        (row.get("dataset_id", ""), row.get("dataset_version", "")): row
        for row in existing_registry
    }

    for source in discovered:
        try:
            rel = source.relative_to(ROOT).as_posix()
        except ValueError:
            failures.append(f"source_outside_repository:{source}")
            continue

        if not source.exists() or not source.is_file():
            missing_sources.append({"source_relative_path": rel, "reason": "missing_after_discovery"})
            failures.append(f"source_missing_after_discovery:{rel}")
            continue

        try:
            source_hash = sha256(source)
            source_size = source.stat().st_size
        except OSError as exc:
            copy_errors.append({"source_relative_path": rel, "operation": "hash_source", "error": repr(exc)})
            failures.append(f"source_hash_error:{rel}:{type(exc).__name__}")
            continue

        ingestion_id = f"sha256-{source_hash[:16]}"
        destination = compact_destination(vault_root, ingestion_id, rel, source.suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
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
        except OSError as exc:
            copy_errors.append(
                {
                    "source_relative_path": rel,
                    "destination_relative_path": destination.relative_to(ROOT).as_posix(),
                    "operation": "copy_or_verify",
                    "error": repr(exc),
                }
            )
            failures.append(f"copy_error:{rel}:{type(exc).__name__}")
            continue

        state, reason = classify(rel)
        path_digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()
        dataset_id = "mtg-file-" + path_digest[:20]
        dataset_version = ingestion_id
        manifest = {
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "dataset_state": state,
            "source_relative_path": rel,
            "vault_relative_path": destination.relative_to(ROOT).as_posix(),
            "source_sha256": source_hash,
            "vault_sha256": destination_hash,
            "size_bytes": source_size,
            "copied_at": now,
            "copy_only": True,
            "source_preserved_in_place": True,
            "vault_path_policy": "COMPACT_CONTENT_ADDRESSED_OBJECT",
            "builder_commit": commit,
            "classification_reason": reason,
        }
        manifest_path = manifest_root / ingestion_id / f"{path_digest[:20]}.manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if manifest_path.exists():
            try:
                existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                failures.append(f"manifest_read_error:{rel}:{type(exc).__name__}")
                continue
            if (
                existing_manifest.get("source_sha256") != source_hash
                or existing_manifest.get("source_relative_path") != rel
            ):
                failures.append(f"manifest_conflict:{rel}:{ingestion_id}")
                continue
        else:
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        manifest_rows.append(manifest)
        classification_rows.append(
            {
                "dataset_id": dataset_id,
                "dataset_version": dataset_version,
                "relative_path": rel,
                "dataset_state": state,
                "classification_reason": reason,
                "content_sha256": source_hash,
                "review_required": state != "RAW",
            }
        )

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
            "copied_at", "copy_only", "source_preserved_in_place", "vault_path_policy",
            "builder_commit", "classification_reason",
        ],
        manifest_rows,
    )
    write_csv(missing_source_path, ["source_relative_path", "reason"], missing_sources)
    write_csv(
        copy_error_path,
        ["source_relative_path", "destination_relative_path", "operation", "error"],
        copy_errors,
    )

    if not discovered:
        failures.append("no_data_files_discovered")
    if hash_mismatches:
        failures.append("hash_verification_failures")

    summary = {
        "audit_name": cfg["program_name"],
        "audit_version": "1.1.0",
        "vault_path_policy": "COMPACT_CONTENT_ADDRESSED_OBJECT",
        "discovered_file_count": len(discovered),
        "vault_copy_created_count": copied,
        "vault_copy_reused_count": reused,
        "hash_mismatch_count": hash_mismatches,
        "missing_source_count": len(missing_sources),
        "copy_error_count": len(copy_errors),
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
