from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_current_data_lineage_audit"

TARGET_FIELDS = {
    "current_price",
    "latest_price_date",
    "accepted_listing_count",
    "review_listing_count",
    "source_observation_at_utc",
    "captured_at_utc",
    "source_snapshot_id",
}

TEXT_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".toml", ".md", ".sql", ".ps1", ".bat", ".sh"}
DATA_SUFFIXES = {".csv", ".json", ".parquet"}
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__"}

PRODUCER_PATTERNS = [
    re.compile(r"to_csv\s*\("),
    re.compile(r"write_text\s*\("),
    re.compile(r"json\.dump"),
    re.compile(r"DataFrame\s*\("),
    re.compile(r"\[[\"'](?:current_price|latest_price_date|accepted_listing_count|review_listing_count)[\"']\]\s*="),
]
CONSUMER_PATTERNS = [
    re.compile(r"read_csv\s*\("),
    re.compile(r"read_json\s*\("),
    re.compile(r"read_parquet\s*\("),
    re.compile(r"\[[\"'](?:current_price|latest_price_date|accepted_listing_count|review_listing_count)[\"']\]"),
]
RISK_PATTERNS = {
    "run_date_substitution": re.compile(r"(?:datetime\.now|Timestamp\.now|utcnow).*?(?:latest_price_date|observation_date)|(?:latest_price_date|observation_date).*?(?:datetime\.now|Timestamp\.now|utcnow)", re.I | re.S),
    "forward_fill": re.compile(r"ffill|fillna\s*\([^)]*(?:price|date)|forward[_ -]?fill", re.I),
    "latest_by_file_mtime": re.compile(r"st_mtime|getmtime|modified_at|creation_time", re.I),
    "unbounded_latest_file": re.compile(r"glob\([^)]*\).*?(?:max|sorted)|(?:max|sorted)\([^)]*glob", re.I | re.S),
    "historical_current_mix": re.compile(r"histor(?:y|ical).*?(?:current_price|latest_price_date)|(?:current_price|latest_price_date).*?histor(?:y|ical)", re.I | re.S),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def should_skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts) or OUT_DIR in path.parents


def scan_text_file(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    fields = sorted(field for field in TARGET_FIELDS if field in text)
    if not fields:
        return None
    producer = any(p.search(text) for p in PRODUCER_PATTERNS)
    consumer = any(p.search(text) for p in CONSUMER_PATTERNS)
    risks = sorted(name for name, pattern in RISK_PATTERNS.items() if pattern.search(text))
    lines = text.splitlines()
    evidence = []
    for idx, line in enumerate(lines, start=1):
        matched = [field for field in fields if field in line]
        if matched:
            evidence.append({"line": idx, "fields": matched, "text": line.strip()[:500]})
        if len(evidence) >= 12:
            break
    return {
        "path": rel(path),
        "suffix": path.suffix.lower(),
        "sha256": sha256(path),
        "fields": fields,
        "producer_candidate": producer,
        "consumer_candidate": consumer,
        "risk_flags": risks,
        "evidence": evidence,
    }


def inspect_data_file(path: Path) -> dict | None:
    if path.suffix.lower() != ".csv":
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            row_count = sum(1 for _ in reader)
    except (OSError, UnicodeError, csv.Error):
        return None
    fields = sorted(field for field in TARGET_FIELDS if field in header)
    if not fields:
        return None
    return {
        "path": rel(path),
        "sha256": sha256(path),
        "rows": row_count,
        "columns": header,
        "target_fields": fields,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    code_results = []
    data_results = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip(path):
            continue
        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIXES:
            result = scan_text_file(path)
            if result:
                code_results.append(result)
        if suffix in DATA_SUFFIXES:
            result = inspect_data_file(path)
            if result:
                data_results.append(result)

    producer_candidates = [r for r in code_results if r["producer_candidate"]]
    consumer_candidates = [r for r in code_results if r["consumer_candidate"]]
    risk_files = [r for r in code_results if r["risk_flags"]]

    field_coverage = {
        field: {
            "code_files": sorted(r["path"] for r in code_results if field in r["fields"]),
            "data_files": sorted(r["path"] for r in data_results if field in r["target_fields"]),
        }
        for field in sorted(TARGET_FIELDS)
    }

    checks = {
        "current_price_references_found": bool(field_coverage["current_price"]["code_files"] or field_coverage["current_price"]["data_files"]),
        "latest_price_date_references_found": bool(field_coverage["latest_price_date"]["code_files"] or field_coverage["latest_price_date"]["data_files"]),
        "listing_count_references_found": bool(field_coverage["accepted_listing_count"]["code_files"] or field_coverage["accepted_listing_count"]["data_files"]),
        "producer_candidates_found": bool(producer_candidates),
        "consumer_candidates_found": bool(consumer_candidates),
        "no_run_date_substitution_detected": not any("run_date_substitution" in r["risk_flags"] for r in risk_files),
        "no_forward_fill_detected": not any("forward_fill" in r["risk_flags"] for r in risk_files),
    }

    critical_failures = [name for name, passed in checks.items() if not passed]
    summary = {
        "block_name": "Collector V1 Current Data Source and Lineage Audit",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_files_with_target_fields": len(code_results),
        "data_files_with_target_fields": len(data_results),
        "producer_candidates": len(producer_candidates),
        "consumer_candidates": len(consumer_candidates),
        "risk_flagged_files": len(risk_files),
        "checks": checks,
        "critical_failures": critical_failures,
        "source_trace_complete_enough_for_adjudication": not critical_failures,
        "fresh_snapshot_capture_authorized": bool(producer_candidates) and checks["no_run_date_substitution_detected"],
        "model_rebuild_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": "PASS_COLLECTOR_V1_CURRENT_DATA_LINEAGE_AUDIT" if not critical_failures else "PARTIAL_COLLECTOR_V1_CURRENT_DATA_LINEAGE_AUDIT",
    }

    (OUT_DIR / "collector_v1_current_data_lineage_code_inventory.json").write_text(json.dumps(code_results, indent=2), encoding="utf-8")
    (OUT_DIR / "collector_v1_current_data_lineage_data_inventory.json").write_text(json.dumps(data_results, indent=2), encoding="utf-8")
    (OUT_DIR / "collector_v1_current_data_lineage_field_coverage.json").write_text(json.dumps(field_coverage, indent=2), encoding="utf-8")
    (OUT_DIR / "collector_v1_current_data_lineage_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with (OUT_DIR / "collector_v1_current_data_producer_candidates.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "fields", "risk_flags", "sha256"])
        writer.writeheader()
        for item in producer_candidates:
            writer.writerow({"path": item["path"], "fields": "|".join(item["fields"]), "risk_flags": "|".join(item["risk_flags"]), "sha256": item["sha256"]})

    print(json.dumps(summary, indent=2))
    return 0 if (not critical_failures or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
