from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
SOURCE_SHA256 = "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
SEARCH_ROOTS = [
    ROOT / "data/governance/permanence/certification/collector_v1_august1_current_data_package",
    ROOT / "data/operations",
    ROOT / "data/governance/permanence/certification",
]
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_evidence_diagnostic"
TEXT_SUFFIXES = {".json", ".csv", ".md", ".txt", ".yaml", ".yml", ".log"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_text(path: Path) -> tuple[str, str]:
    try:
        return path.read_text(encoding="utf-8-sig", errors="strict"), ""
    except Exception as exc:  # noqa: BLE001
        return "", f"{type(exc).__name__}:{exc}"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    seen: set[Path] = set()
    inventory: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []

    for search_root in SEARCH_ROOTS:
        if not search_root.is_dir():
            continue
        for path in sorted(p for p in search_root.rglob("*") if p.is_file()):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            relative = path.relative_to(ROOT).as_posix()
            suffix = path.suffix.lower()
            digest = sha256(path)
            text = ""
            read_error = ""
            if suffix in TEXT_SUFFIXES:
                text, read_error = read_text(path)
            lower = text.lower()
            snapshot_match = SNAPSHOT_ID.lower() in lower
            source_hash_match = SOURCE_SHA256.lower() in lower
            model_input_terms = [
                "certified_for_model_input",
                "model_input_certified",
                "certified for model input",
            ]
            rebuild_terms = [
                "model_rebuild_authorized",
                "rebuild_authorized",
                "model rebuild authorized",
            ]
            model_input_match = any(term in lower for term in model_input_terms)
            rebuild_match = any(term in lower for term in rebuild_terms)
            explicit_failure_match = any(term in lower for term in [
                '"status": "fail',
                '"critical_failures": [',
                "fail_collector",
            ])
            row = {
                "relative_path": relative,
                "suffix": suffix,
                "size_bytes": path.stat().st_size,
                "sha256": digest,
                "text_read_error": read_error,
                "snapshot_match": snapshot_match,
                "source_hash_match": source_hash_match,
                "model_input_term_match": model_input_match,
                "rebuild_authorization_term_match": rebuild_match,
                "explicit_failure_term_match": explicit_failure_match,
            }
            inventory.append(row)
            if snapshot_match or source_hash_match or model_input_match or rebuild_match:
                matches.append(row)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_august1_evidence_file_inventory.csv", inventory)
    write_csv(OUTPUT / "collector_august1_evidence_matches.csv", matches)
    summary = {
        "snapshot_id": SNAPSHOT_ID,
        "source_bundle_sha256": SOURCE_SHA256,
        "files_inventoried": len(inventory),
        "candidate_evidence_files": len(matches),
        "snapshot_match_files": sum(bool(row["snapshot_match"]) for row in matches),
        "source_hash_match_files": sum(bool(row["source_hash_match"]) for row in matches),
        "model_input_term_match_files": sum(bool(row["model_input_term_match"]) for row in matches),
        "rebuild_authorization_term_match_files": sum(bool(row["rebuild_authorization_term_match"]) for row in matches),
        "search_roots": [path.relative_to(ROOT).as_posix() for path in SEARCH_ROOTS],
        "status": "PASS_COLLECTOR_AUGUST1_EVIDENCE_DIAGNOSTIC",
    }
    (OUTPUT / "collector_august1_evidence_diagnostic_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print("\nCANDIDATE EVIDENCE FILES")
    for row in matches:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
