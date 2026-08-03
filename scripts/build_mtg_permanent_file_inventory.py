from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/governance/permanence/inventory"
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(root: Path, output_root: Path) -> Iterable[Path]:
    output_resolved = output_root.resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        try:
            resolved = path.resolve()
        except OSError:
            continue
        # Do not recursively inventory the generated inventory itself.
        if output_resolved == resolved or output_resolved in resolved.parents:
            continue
        yield path


def classify(path: Path) -> tuple[str, str]:
    relative = path.relative_to(ROOT).as_posix()
    lower = relative.lower()
    if lower.startswith("data_vault/") or lower.startswith("data/raw/"):
        return "RAW_OR_SOURCE", "UNVERIFIED"
    if "/certified/" in lower or lower.startswith("data/certified/"):
        return "CERTIFIED_CANDIDATE", "UNVERIFIED"
    if lower.startswith("data/operations/"):
        return "DERIVED_OPERATIONAL", "UNVERIFIED"
    if lower.startswith("config/"):
        return "CONFIGURATION", "UNVERIFIED"
    if lower.startswith("scripts/") or lower.endswith(".py"):
        return "CODE", "UNVERIFIED"
    if lower.startswith("docs/"):
        return "DOCUMENTATION", "UNVERIFIED"
    return "OTHER", "UNVERIFIED"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a non-destructive SHA-256 inventory of the MTG project.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    output_root = args.output_root if args.output_root.is_absolute() else ROOT / args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows: list[dict[str, object]] = []
    failures: list[str] = []

    for path in sorted(iter_files(ROOT, output_root), key=lambda p: p.as_posix().lower()):
        try:
            stat = path.stat()
            sha = sha256_file(path)
            role, status = classify(path)
            rows.append(
                {
                    "relative_path": path.relative_to(ROOT).as_posix(),
                    "size_bytes": int(stat.st_size),
                    "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0).isoformat(),
                    "sha256": sha,
                    "suffix": path.suffix.lower(),
                    "suspected_role": role,
                    "certification_status": status,
                    "inventory_generated_at": generated_at,
                }
            )
        except (OSError, PermissionError) as exc:
            failures.append(f"unreadable:{path.relative_to(ROOT).as_posix()}:{type(exc).__name__}")

    inventory_csv = output_root / "mtg_permanent_file_inventory.csv"
    inventory_json = output_root / "mtg_permanent_file_inventory_summary.json"
    fieldnames = [
        "relative_path",
        "size_bytes",
        "modified_utc",
        "sha256",
        "suffix",
        "suspected_role",
        "certification_status",
        "inventory_generated_at",
    ]
    with inventory_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    duplicate_hash_groups = 0
    hash_counts: dict[str, int] = {}
    for row in rows:
        hash_counts[str(row["sha256"])] = hash_counts.get(str(row["sha256"]), 0) + 1
    duplicate_hash_groups = sum(1 for count in hash_counts.values() if count > 1)

    result = {
        "program": "MTG Permanent File Inventory",
        "version": "1.0.0",
        "root": str(ROOT),
        "generated_at": generated_at,
        "file_count": len(rows),
        "total_size_bytes": sum(int(row["size_bytes"]) for row in rows),
        "duplicate_content_hash_group_count": duplicate_hash_groups,
        "failure_count": len(failures),
        "failures": failures,
        "destructive_operation_performed": False,
        "files_deleted": 0,
        "files_moved": 0,
        "files_overwritten": 0,
        "status": "PASS" if not failures else "FAIL",
        "inventory_csv": inventory_csv.relative_to(ROOT).as_posix(),
    }
    inventory_json.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
