from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_end_to_end_governance_audit_v2_contract.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_end_to_end_governance_audit_v2"


def clean(value: Any) -> str:
    return str(value or "").strip()


def truthy(value: Any) -> bool:
    return clean(value).lower() in {"true", "1", "yes"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def locate_summary_by_status(stage_dir: Path, expected_status: str) -> tuple[Path | None, list[str]]:
    matches: list[Path] = []
    for path in sorted(stage_dir.glob("*.json")):
        payload = parse_json(path)
        if payload and clean(payload.get("status")) == expected_status:
            matches.append(path)
    return (matches[0] if len(matches) == 1 else None, [path.name for path in matches])


def inventory_file(path: Path, stage: str) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    relative = path.relative_to(ROOT).as_posix()
    row_count: int | str = ""
    header_count: int | str = ""
    duplicate_header_count: int | str = ""
    parse_status = "NOT_APPLICABLE"
    if path.suffix.lower() == ".csv":
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, [])
                row_count = sum(1 for _ in reader)
            header_count = len(header)
            duplicate_header_count = len(header) - len(set(header))
            parse_status = "PASS" if duplicate_header_count == 0 else "FAIL_DUPLICATE_HEADERS"
            if duplicate_header_count:
                failures.append(f"DUPLICATE_CSV_HEADERS:{relative}")
        except Exception as exc:
            parse_status = f"FAIL:{type(exc).__name__}"
            failures.append(f"CSV_PARSE_FAILED:{relative}")
    elif path.suffix.lower() == ".json":
        parse_status = "PASS" if parse_json(path) is not None else "FAIL_JSON_PARSE"
        if parse_status != "PASS":
            failures.append(f"JSON_PARSE_FAILED:{relative}")
    return ({
        "stage": stage,
        "relative_path": relative,
        "filename": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "row_count_excluding_header": row_count,
        "header_count": header_count,
        "duplicate_header_count": duplicate_header_count,
        "parse_status": parse_status,
    }, failures)


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []
    warnings: list[str] = []
    stage_rows: list[dict[str, Any]] = []
    inventory: dict[str, dict[str, Any]] = {}
    declared_hashes: list[tuple[str, str, str]] = []

    for stage in contract["stages"]:
        stage_dir = ROOT / stage["directory"]
        if not stage_dir.is_dir():
            failures.append(f"STAGE_DIRECTORY_MISSING:{stage['stage']}")
            continue
        for path in sorted(p for p in stage_dir.iterdir() if p.is_file()):
            row, file_failures = inventory_file(path, stage["stage"])
            inventory[row["relative_path"]] = row
            failures.extend(file_failures)
        summary_path, matches = locate_summary_by_status(stage_dir, stage["expected_status"])
        if summary_path is None:
            failures.append(f"STAGE_SUMMARY_STATUS_RESOLUTION_FAILED:{stage['stage']}:{len(matches)}")
            stage_rows.append({"stage": stage["stage"], "expected_status": stage["expected_status"], "observed_status": "", "summary_path": "", "stage_pass": False})
            continue
        payload = parse_json(summary_path) or {}
        critical = payload.get("critical_failures", []) or []
        if not isinstance(critical, list):
            critical = [critical]
        observed = clean(payload.get("status"))
        passed = observed == stage["expected_status"] and not critical
        if not passed:
            failures.append(f"STAGE_NOT_PASS:{stage['stage']}")
        stage_rows.append({
            "stage": stage["stage"],
            "summary_path": summary_path.relative_to(ROOT).as_posix(),
            "observed_status": observed,
            "expected_status": stage["expected_status"],
            "snapshot_id": clean(payload.get("snapshot_id")),
            "critical_failure_count": len(critical),
            "stage_pass": passed,
        })
        hashes = payload.get("authority_hashes", {})
        if isinstance(hashes, dict):
            for label, digest in hashes.items():
                declared_hashes.append((stage["stage"], clean(label), clean(digest)))

    final_counts: dict[str, int] = {}
    for label, relative in contract["final_authorities"].items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"FINAL_AUTHORITY_MISSING:{label}")
            continue
        row, file_failures = inventory_file(path, "FINAL_AUTHORITY")
        inventory[row["relative_path"]] = row
        failures.extend(file_failures)
        final_counts[label] = int(row["row_count_excluding_header"])

    canonical_summary = parse_json(ROOT / contract["canonical_summary"])
    if canonical_summary is None:
        failures.append("CANONICAL_SUMMARY_MISSING_OR_INVALID")
        coverage_rows = None
    else:
        coverage_rows = canonical_summary.get("coverage_rows")
        final_counts["coverage_rows"] = int(coverage_rows) if coverage_rows is not None else -1

    for label, expected in contract["required_final_counts"].items():
        observed = final_counts.get(label)
        if observed != int(expected):
            failures.append(f"FINAL_COUNT_MISMATCH:{label}:{observed}:{expected}")

    hashes_to_paths: dict[str, list[str]] = {}
    for relative, row in inventory.items():
        hashes_to_paths.setdefault(clean(row["sha256"]), []).append(relative)
    hash_rows: list[dict[str, Any]] = []
    for stage, label, digest in declared_hashes:
        matches = sorted(hashes_to_paths.get(digest, []))
        hash_rows.append({
            "source_stage": stage,
            "authority_label": label,
            "declared_sha256": digest,
            "matched_inventory_paths": "|".join(matches),
            "matched_file_count": len(matches),
            "reconciled_with_audited_inventory": bool(matches),
        })
        if not matches:
            warnings.append(f"DECLARED_HASH_NOT_RECONCILED:{stage}:{label}")

    standard_path = ROOT / contract["standard_path"]
    standards_rows: list[dict[str, Any]] = []
    if not standard_path.is_file():
        failures.append("MTG_STANDARD_MISSING")
    else:
        standard_text = " ".join(standard_path.read_text(encoding="utf-8").split()).lower()
        for requirement in contract["standard_requirements"]:
            required = " ".join(requirement["required_text"].split()).lower()
            documented = required in standard_text
            standards_rows.append({
                "control": requirement["control"],
                "required_text": requirement["required_text"],
                "documented_in_standard": documented,
                "audit_disposition": "DOCUMENTED_EXACTLY" if documented else "MISSING_FROM_STANDARD",
                "standard_path": contract["standard_path"],
            })
            if not documented:
                failures.append(f"STANDARD_REQUIREMENT_NOT_DOCUMENTED:{requirement['control']}")

    purchase_rows = read_csv(ROOT / contract["final_authorities"]["purchase_authority"])
    conditional_authorized = sum(
        clean(row.get("final_ranking_eligibility_status")) == "CONDITIONAL_RANKING_ELIGIBLE"
        and truthy(row.get("recommendation_authorized"))
        for row in purchase_rows
    )
    modified_rows = sum(truthy(row.get("forecast_values_modified")) for row in purchase_rows)
    purchase_summary = next((row for row in stage_rows if row["stage"] == "purchase_recommendation_certification"), None)
    purchase_payload = parse_json(ROOT / purchase_summary["summary_path"]) if purchase_summary and purchase_summary.get("summary_path") else None
    automatic_execution = purchase_payload.get("automatic_purchase_execution_authorized") if purchase_payload else None
    if conditional_authorized:
        failures.append(f"CONDITIONAL_PRODUCTS_PURCHASE_AUTHORIZED:{conditional_authorized}")
    if modified_rows:
        failures.append(f"FORECAST_VALUES_MODIFIED:{modified_rows}")
    if automatic_execution is not False:
        failures.append(f"AUTOMATIC_PURCHASE_EXECUTION_NOT_FALSE:{automatic_execution}")

    snapshots = {clean(row.get("snapshot_id")) for row in stage_rows if clean(row.get("snapshot_id"))}
    if snapshots != {contract["snapshot_id"]}:
        failures.append(f"SNAPSHOT_ID_INCONSISTENT:{sorted(snapshots)}")
    if len(stage_rows) != int(contract["required_stage_count"]):
        failures.append(f"STAGE_COUNT:{len(stage_rows)}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    inventory_rows = sorted(inventory.values(), key=lambda row: row["relative_path"])
    write_csv(OUTPUT / "collector_stage_certification_audit.csv", stage_rows)
    write_csv(OUTPUT / "collector_complete_output_inventory.csv", inventory_rows)
    write_csv(OUTPUT / "collector_authority_hash_reconciliation.csv", hash_rows)
    write_csv(OUTPUT / "collector_mtg_standard_control_matrix.csv", standards_rows)

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_END_TO_END_GOVERNANCE_AND_MTG_STANDARDS_AUDIT_V2"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "stages_audited": len(stage_rows),
        "stages_passed": sum(bool(row.get("stage_pass")) for row in stage_rows),
        "files_inventoried": len(inventory_rows),
        "json_and_csv_parse_failures": sum(row["parse_status"].startswith("FAIL") for row in inventory_rows),
        "final_authority_counts": final_counts,
        "declared_hashes_checked": len(hash_rows),
        "declared_hashes_reconciled_to_audited_inventory": sum(bool(row["reconciled_with_audited_inventory"]) for row in hash_rows),
        "standard_requirements_reviewed": len(standards_rows),
        "standard_requirements_documented": sum(bool(row["documented_in_standard"]) for row in standards_rows),
        "conditional_products_purchase_authorized": conditional_authorized,
        "forecast_values_modified_in_purchase_authority": modified_rows,
        "automatic_purchase_execution_authorized": automatic_execution,
        "human_review_required": True,
        "warnings": sorted(set(warnings)),
        "critical_failures": sorted(set(failures)),
        "status": status,
    }
    (OUTPUT / "collector_end_to_end_governance_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report = [
        "# Collector End-to-End Governance and MTG Standards Audit V2",
        "",
        f"- Status: **{status}**",
        f"- Stages passed: {summary['stages_passed']} / {summary['stages_audited']}",
        f"- Files inventoried: {summary['files_inventoried']}",
        f"- Standard requirements documented: {summary['standard_requirements_documented']} / {summary['standard_requirements_reviewed']}",
        f"- Critical failures: {len(summary['critical_failures'])}",
        f"- Warnings: {len(summary['warnings'])}",
        "",
        "## Critical Failures",
        *(f"- {item}" for item in summary["critical_failures"]),
        "",
        "## Warnings",
        *(f"- {item}" for item in summary["warnings"]),
        "",
        "This audit is read-only and does not alter forecasts, rankings, or recommendations.",
    ]
    (OUTPUT / "COLLECTOR_END_TO_END_GOVERNANCE_AUDIT_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
