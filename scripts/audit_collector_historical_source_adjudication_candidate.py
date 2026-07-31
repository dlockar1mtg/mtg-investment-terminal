from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_historical_source_adjudication_candidate_v1.json"
OUTPUT_DIR = ROOT / "data/operations/collector_backtest_source_adjudication/candidate_v1_0_0"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def inspect_csv(path: Path) -> tuple[bool, int, list[str], str | None]:
    if not path.exists():
        return False, 0, [], "FILE_NOT_FOUND"
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            row_count = sum(1 for _ in reader)
        return True, row_count, header, None
    except Exception as exc:  # diagnostic audit must preserve failure detail
        return False, 0, [], f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = load_json(CONFIG)
    failures: list[str] = []
    rows: list[dict[str, object]] = []

    if cfg.get("historical_snapshot_builder_authorized") is not False:
        failures.append("historical_snapshot_builder_authorized must remain false")
    if cfg.get("projection_authorized") is not False:
        failures.append("projection_authorized must remain false")
    if cfg.get("purchase_recommendation_authorized") is not False:
        failures.append("purchase_recommendation_authorized must remain false")
    if cfg.get("selection_rules", {}).get("future_information_prohibited") is not True:
        failures.append("future_information_prohibited must be true")

    for source in cfg.get("candidate_authoritative_sources", []):
        path = ROOT / source["path"]
        readable, row_count, columns, error = inspect_csv(path)
        status = source["adjudication_status"]
        rows.append(
            {
                "source_id": source["source_id"],
                "role": source["role"],
                "path": source["path"],
                "configured_status": status,
                "exists_and_readable": readable,
                "row_count": row_count,
                "column_count": len(columns),
                "columns": "|".join(columns),
                "inspection_error": error or "",
                "reason": source["reason"],
            }
        )
        if status.startswith("CANDIDATE_") and not readable:
            failures.append(f"candidate source unreadable: {source['source_id']} {source['path']}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    adjudication_path = OUTPUT_DIR / "collector_historical_source_adjudication.csv"
    with adjudication_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(rows[0].keys()) if rows else []
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    rejection_rows = [r for r in rows if "NOT_AUTHORIZED" in str(r["configured_status"]) or "DISCOVERY_REQUIRED" in str(r["configured_status"])]
    rejection_path = OUTPUT_DIR / "collector_historical_source_rejection_log.csv"
    with rejection_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(rows[0].keys()) if rows else []
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rejection_rows)

    role_counts = Counter(str(r["role"]) for r in rows)
    coverage = {
        "role_distribution": dict(sorted(role_counts.items())),
        "candidate_readable_count": sum(bool(r["exists_and_readable"]) for r in rows),
        "candidate_unreadable_count": sum(not bool(r["exists_and_readable"]) for r in rows),
        "historical_snapshot_builder_authorized": False,
    }
    (OUTPUT_DIR / "collector_historical_role_coverage.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True), encoding="utf-8"
    )

    summary = {
        "audit_name": "Collector Historical Source Adjudication Candidate Audit",
        "audit_version": "1.0.0",
        "candidate_source_count": len(rows),
        "readable_source_count": sum(bool(r["exists_and_readable"]) for r in rows),
        "rejected_or_reference_only_count": len(rejection_rows),
        "failure_count": len(failures),
        "failures": failures,
        "future_information_prohibited": True,
        "historical_snapshot_builder_authorized": False,
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS" if not failures else "REVIEW_REQUIRED",
        "governing_note": "This audit narrows repository-wide discovery to explicit Collector source candidates. It does not authorize snapshot construction or historical substitution.",
    }
    (OUTPUT_DIR / "collector_historical_source_adjudication_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
