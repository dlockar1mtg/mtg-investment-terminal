from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "data" / "discovered" / "collector_booster_model_input.csv"
CONTRACT = ROOT / "config" / "mtg" / "standards" / "collector_model_input_raw_lineage_contract_v1.json"
OUTPUT = ROOT / "data" / "governance" / "permanence" / "certification" / "collector_v1_model_input_raw_lineage"
TEXT_SUFFIXES = {".py", ".ps1", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".sql"}
DATA_SUFFIXES = {".csv", ".json", ".jsonl", ".parquet"}
SKIP_PARTS = {".git", ".pytest_cache", "__pycache__"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("/", "\\")


def read_header(path: Path) -> list[str]:
    if path.suffix.lower() != ".csv":
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return next(csv.reader(handle), [])
    except Exception:
        return []


def scan_text_references(target_name: str, target_stem: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    patterns = [target_name.lower(), target_stem.lower(), "product_master_model_input"]
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path == Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lower = text.lower()
        matched = [p for p in patterns if p in lower]
        if not matched:
            continue
        writer = bool(re.search(r"to_csv|write_csv|copyfile|shutil\.copy|open\([^\n]{0,120}[wa]['\"]", lower))
        rows.append({
            "reference_path": rel(path),
            "matched_terms": "|".join(sorted(set(matched))),
            "writer_signal": str(writer),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    if not CONTRACT.exists():
        failures.append("contract_missing")
    if not TARGET.exists():
        failures.append("target_missing")

    target_hash = sha256(TARGET) if TARGET.exists() else ""
    target_header = read_header(TARGET) if TARGET.exists() else []
    target_header_set = set(target_header)

    candidate_rows: list[dict[str, str]] = []
    if TARGET.exists():
        for path in ROOT.rglob("*"):
            if not path.is_file() or path == TARGET:
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.suffix.lower() not in DATA_SUFFIXES:
                continue
            identical = False
            try:
                identical = path.stat().st_size == TARGET.stat().st_size and sha256(path) == target_hash
            except OSError:
                pass
            header = read_header(path)
            overlap = len(target_header_set.intersection(header)) if header else 0
            schema_ratio = overlap / len(target_header_set) if target_header_set else 0.0
            if identical or schema_ratio >= 0.60 or "model_input" in path.name.lower():
                lower_path = rel(path).lower()
                likely_copy = any(token in lower_path for token in ("repair_input", "staging", "backup", "archive", "discovered"))
                candidate_rows.append({
                    "candidate_path": rel(path),
                    "source_sha256": sha256(path),
                    "byte_identical_to_target": str(identical),
                    "schema_overlap_ratio": f"{schema_ratio:.6f}",
                    "likely_copy_or_promoted_artifact": str(likely_copy),
                })

    references = scan_text_references(TARGET.name, TARGET.stem)
    writers = [row for row in references if row["writer_signal"] == "True"]
    identical = [row for row in candidate_rows if row["byte_identical_to_target"] == "True"]
    noncopy_schema = [row for row in candidate_rows if row["likely_copy_or_promoted_artifact"] == "False" and float(row["schema_overlap_ratio"]) >= 0.60]

    if writers and noncopy_schema:
        lineage_state = "LINEAGE_PARTIALLY_RECONSTRUCTED"
    elif writers or identical or noncopy_schema:
        lineage_state = "LINEAGE_PARTIALLY_RECONSTRUCTED"
    else:
        lineage_state = "LINEAGE_UNRESOLVED"

    raw_authority = False
    authority_reason = (
        "Raw observation authority is not granted until a generating transformation and its raw point-in-time inputs are both identified and reproducible."
    )

    candidate_path = OUTPUT / "collector_v1_model_input_lineage_candidates.csv"
    reference_path = OUTPUT / "collector_v1_model_input_code_references.csv"
    summary_path = OUTPUT / "collector_v1_model_input_raw_lineage_summary.json"

    candidate_fields = ["candidate_path", "source_sha256", "byte_identical_to_target", "schema_overlap_ratio", "likely_copy_or_promoted_artifact"]
    with candidate_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=candidate_fields)
        writer.writeheader()
        writer.writerows(candidate_rows)

    reference_fields = ["reference_path", "matched_terms", "writer_signal"]
    with reference_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=reference_fields)
        writer.writeheader()
        writer.writerows(references)

    summary = {
        "block_name": "Collector V1 Model Input Raw Lineage Trace",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_path": rel(TARGET),
        "target_sha256": target_hash,
        "target_column_count": len(target_header),
        "candidate_source_count": len(candidate_rows),
        "byte_identical_copy_count": len(identical),
        "schema_equivalent_noncopy_count": len(noncopy_schema),
        "code_reference_count": len(references),
        "writer_reference_count": len(writers),
        "lineage_state": lineage_state,
        "raw_historical_price_authority_certified": raw_authority,
        "authority_reason": authority_reason,
        "candidate_path": rel(candidate_path),
        "candidate_sha256": sha256(candidate_path),
        "reference_path": rel(reference_path),
        "reference_sha256": sha256(reference_path),
        "critical_failures": failures,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": "PASS_COLLECTOR_V1_MODEL_INPUT_RAW_LINEAGE_TRACE" if not failures else "FAIL_COLLECTOR_V1_MODEL_INPUT_RAW_LINEAGE_TRACE",
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
