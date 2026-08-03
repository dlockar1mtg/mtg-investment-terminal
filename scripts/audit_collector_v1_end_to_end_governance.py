from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_end_to_end_governance_audit_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_end_to_end_governance_audit"


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


def parse_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}:{exc}"
    if not isinstance(payload, dict):
        return None, "JSON_ROOT_NOT_OBJECT"
    return payload, ""


def locate_summary(stage_dir: Path, preferred: str) -> Path | None:
    preferred_path = stage_dir / preferred
    if preferred_path.is_file():
        return preferred_path
    candidates = sorted(stage_dir.glob("*summary.json"))
    return candidates[0] if len(candidates) == 1 else None


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []
    warnings: list[str] = []
    stage_rows: list[dict[str, Any]] = []
    inventory_rows: list[dict[str, Any]] = []
    hash_rows: list[dict[str, Any]] = []
    standards_rows: list[dict[str, Any]] = []
    all_files: dict[str, Path] = {}
    all_hashes: dict[str, list[str]] = {}

    for stage in contract["stages"]:
        stage_dir = ROOT / stage["directory"]
        if not stage_dir.is_dir():
            failures.append(f"STAGE_DIRECTORY_MISSING:{stage['stage']}")
            stage_rows.append({
                "stage": stage["stage"],
                "directory": stage["directory"],
                "summary_path": "",
                "observed_status": "",
                "expected_status": stage["expected_status"],
                "status_matches": False,
                "critical_failure_count": "",
                "json_parse_error": "DIRECTORY_MISSING",
                "stage_pass": False,
            })
            continue

        for path in sorted(p for p in stage_dir.iterdir() if p.is_file()):
            relative = path.relative_to(ROOT).as_posix()
            digest = sha256(path)
            all_files[relative] = path
            all_hashes.setdefault(digest, []).append(relative)
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
                except Exception as exc:  # noqa: BLE001
                    parse_status = f"FAIL:{type(exc).__name__}"
                    failures.append(f"CSV_PARSE_FAILED:{relative}")
            elif path.suffix.lower() == ".json":
                payload, error = parse_json(path)
                parse_status = "PASS" if payload is not None else f"FAIL:{error}"
                if payload is None:
                    failures.append(f"JSON_PARSE_FAILED:{relative}:{error}")
            inventory_rows.append({
                "stage": stage["stage"],
                "relative_path": relative,
                "filename": path.name,
                "extension": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "sha256": digest,
                "row_count_excluding_header": row_count,
                "header_count": header_count,
                "duplicate_header_count": duplicate_header_count,
                "parse_status": parse_status,
            })

        summary_path = locate_summary(stage_dir, stage["summary"])
        if summary_path is None:
            failures.append(f"STAGE_SUMMARY_NOT_UNIQUELY_RESOLVED:{stage['stage']}")
            stage_rows.append({
                "stage": stage["stage"],
                "directory": stage["directory"],
                "summary_path": "",
                "observed_status": "",
                "expected_status": stage["expected_status"],
                "status_matches": False,
                "critical_failure_count": "",
                "json_parse_error": "SUMMARY_NOT_UNIQUELY_RESOLVED",
                "stage_pass": False,
            })
            continue

        payload, error = parse_json(summary_path)
        observed_status = clean(payload.get("status")) if payload else ""
        critical = payload.get("critical_failures", []) if payload else []
        if critical is None:
            critical = []
        if not isinstance(critical, list):
            critical = [critical]
        status_matches = observed_status == stage["expected_status"]
        stage_pass = payload is not None and status_matches and len(critical) == 0
        if not status_matches:
            failures.append(
                f"STAGE_STATUS_MISMATCH:{stage['stage']}:{observed_status}:{stage['expected_status']}"
            )
        if critical:
            failures.append(f"STAGE_CRITICAL_FAILURES:{stage['stage']}:{len(critical)}")
        stage_rows.append({
            "stage": stage["stage"],
            "directory": stage["directory"],
            "summary_path": summary_path.relative_to(ROOT).as_posix(),
            "observed_status": observed_status,
            "expected_status": stage["expected_status"],
            "status_matches": status_matches,
            "critical_failure_count": len(critical),
            "json_parse_error": error,
            "snapshot_id": clean(payload.get("snapshot_id")) if payload else "",
            "stage_pass": stage_pass,
        })

        if payload:
            authority_hashes = payload.get("authority_hashes", {})
            if isinstance(authority_hashes, dict):
                for label, digest in authority_hashes.items():
                    digest_text = clean(digest)
                    matched_paths = all_hashes.get(digest_text, [])
                    hash_rows.append({
                        "source_stage": stage["stage"],
                        "authority_label": label,
                        "declared_sha256": digest_text,
                        "matched_inventory_paths": "|".join(matched_paths),
                        "matched_file_count": len(matched_paths),
                        "reconciled_with_audited_inventory": bool(matched_paths),
                    })
                    if not matched_paths:
                        warnings.append(f"DECLARED_HASH_NOT_IN_STAGE_INVENTORY:{stage['stage']}:{label}")

    final_authority_counts: dict[str, int] = {}
    for label, relative in contract["final_authorities"].items():
        path = ROOT / relative
        exists = path.is_file()
        count: int | str = ""
        digest = ""
        duplicate_headers: int | str = ""
        if exists:
            digest = sha256(path)
            all_files[relative] = path
            all_hashes.setdefault(digest, []).append(relative)
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.reader(handle)
                    header = next(reader, [])
                    count = sum(1 for _ in reader)
                duplicate_headers = len(header) - len(set(header))
                final_authority_counts[label] = int(count)
                if duplicate_headers:
                    failures.append(f"FINAL_AUTHORITY_DUPLICATE_HEADERS:{label}")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"FINAL_AUTHORITY_PARSE_FAILED:{label}:{type(exc).__name__}")
        else:
            failures.append(f"FINAL_AUTHORITY_MISSING:{label}")
        inventory_rows.append({
            "stage": "FINAL_AUTHORITY",
            "relative_path": relative,
            "filename": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": path.stat().st_size if exists else "",
            "sha256": digest,
            "row_count_excluding_header": count,
            "header_count": "",
            "duplicate_header_count": duplicate_headers,
            "parse_status": "PASS" if exists and duplicate_headers == 0 else "FAIL",
        })

    expected = contract["required_final_counts"]
    count_checks = {
        "current_price": expected["governed_products"],
        "final_forecasts": expected["forecast_rows"],
        "forecast_lineage": expected["forecast_rows"],
        "coverage": expected["coverage_rows"],
        "calibration": expected["forecast_rows"],
        "eligibility": expected["ranking_rows"],
        "rankings": expected["ranking_rows"],
        "purchase_authority": expected["purchase_rows"],
    }
    for label, required_count in count_checks.items():
        observed = final_authority_counts.get(label)
        if observed != required_count:
            failures.append(f"FINAL_COUNT_MISMATCH:{label}:{observed}:{required_count}")

    standard_tokens = {
        "identity_authority": ["identity", "canonical"],
        "data_lineage": ["lineage"],
        "current_price_authority": ["current price"],
        "historical_evidence": ["historical"],
        "comparable_governance": ["comparable"],
        "limited_history_confidence": ["limited", "confidence"],
        "no_zero_fill": ["zero"],
        "probabilistic_forecasting": ["probabil"],
        "calibration": ["calibrat"],
        "ranking_separation": ["ranking"],
        "purchase_separation": ["purchase"],
    }
    for relative in contract["standards"]:
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"STANDARD_MISSING:{relative}")
            continue
        text = path.read_text(encoding="utf-8").lower()
        for control, tokens in standard_tokens.items():
            present = all(token in text for token in tokens)
            standards_rows.append({
                "standard_path": relative,
                "control": control,
                "required_tokens": "|".join(tokens),
                "documented_in_standard": present,
                "audit_disposition": "DOCUMENTED" if present else "REVIEW_STANDARD_TEXT",
            })
            if not present:
                warnings.append(f"STANDARD_TOKEN_REVIEW:{control}")

    purchase_path = ROOT / contract["final_authorities"]["purchase_authority"]
    conditional_authorized = 0
    modified_purchase_rows = 0
    if purchase_path.is_file():
        purchase_rows = read_csv(purchase_path)
        conditional_authorized = sum(
            clean(row.get("final_ranking_eligibility_status")) == "CONDITIONAL_RANKING_ELIGIBLE"
            and truthy(row.get("recommendation_authorized"))
            for row in purchase_rows
        )
        modified_purchase_rows = sum(truthy(row.get("forecast_values_modified")) for row in purchase_rows)
        if conditional_authorized:
            failures.append(f"CONDITIONAL_PRODUCTS_PURCHASE_AUTHORIZED:{conditional_authorized}")
        if modified_purchase_rows:
            failures.append(f"PURCHASE_ROWS_FORECAST_VALUES_MODIFIED:{modified_purchase_rows}")

    purchase_summary_stage = next(
        (row for row in stage_rows if row["stage"] == "purchase_recommendation_certification"), None
    )
    automatic_execution = None
    if purchase_summary_stage and purchase_summary_stage["summary_path"]:
        payload, _ = parse_json(ROOT / purchase_summary_stage["summary_path"])
        automatic_execution = payload.get("automatic_purchase_execution_authorized") if payload else None
        if automatic_execution is not False:
            failures.append(f"AUTOMATIC_PURCHASE_EXECUTION_NOT_FALSE:{automatic_execution}")

    snapshots = {clean(row.get("snapshot_id")) for row in stage_rows if clean(row.get("snapshot_id"))}
    if snapshots != {contract["snapshot_id"]}:
        failures.append(f"SNAPSHOT_ID_INCONSISTENT:{sorted(snapshots)}")

    duplicate_inventory_paths = [path for path, count in Counter(row["relative_path"] for row in inventory_rows).items() if count > 1]
    if duplicate_inventory_paths:
        warnings.append(f"INVENTORY_PATHS_REPEATED:{len(duplicate_inventory_paths)}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_stage_certification_audit.csv", stage_rows)
    write_csv(OUTPUT / "collector_complete_output_inventory.csv", inventory_rows)
    write_csv(OUTPUT / "collector_authority_hash_reconciliation.csv", hash_rows)
    write_csv(OUTPUT / "collector_mtg_standard_control_matrix.csv", standards_rows)

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_END_TO_END_GOVERNANCE_AND_MTG_STANDARDS_AUDIT"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "stages_audited": len(stage_rows),
        "stages_passed": sum(bool(row.get("stage_pass")) for row in stage_rows),
        "files_inventoried": len(inventory_rows),
        "json_and_csv_parse_failures": sum("PARSE_FAILED" in failure for failure in failures),
        "final_authority_counts": final_authority_counts,
        "declared_hashes_checked": len(hash_rows),
        "declared_hashes_reconciled_to_audited_inventory": sum(bool(row["reconciled_with_audited_inventory"]) for row in hash_rows),
        "standard_controls_reviewed": len(standards_rows),
        "standard_controls_documented": sum(bool(row["documented_in_standard"]) for row in standards_rows),
        "conditional_products_purchase_authorized": conditional_authorized,
        "forecast_values_modified_in_purchase_authority": modified_purchase_rows,
        "automatic_purchase_execution_authorized": automatic_execution,
        "human_review_required": True,
        "warnings": sorted(set(warnings)),
        "critical_failures": sorted(set(failures)),
        "status": status,
    }
    (OUTPUT / "collector_end_to_end_governance_audit_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    report_lines = [
        "# Collector End-to-End Governance and MTG Standards Audit",
        "",
        f"- Status: **{status}**",
        f"- Snapshot: `{contract['snapshot_id']}`",
        f"- Stages passed: {summary['stages_passed']} / {summary['stages_audited']}",
        f"- Files inventoried: {summary['files_inventoried']}",
        f"- Critical failures: {len(summary['critical_failures'])}",
        f"- Warnings requiring human review: {len(summary['warnings'])}",
        "",
        "## Stage Certification",
        "",
        "| Stage | Observed status | Expected status | Pass |",
        "|---|---|---|---|",
    ]
    for row in stage_rows:
        report_lines.append(
            f"| {row['stage']} | `{row['observed_status']}` | `{row['expected_status']}` | {row['stage_pass']} |"
        )
    report_lines.extend(["", "## Final Authority Counts", "", "| Authority | Rows |", "|---|---:|"])
    for label, count in sorted(final_authority_counts.items()):
        report_lines.append(f"| {label} | {count} |")
    report_lines.extend(["", "## Critical Failures", ""])
    report_lines.extend([f"- {failure}" for failure in summary["critical_failures"]] or ["- None"])
    report_lines.extend(["", "## Warnings / Human Review", ""])
    report_lines.extend([f"- {warning}" for warning in summary["warnings"]] or ["- None"])
    report_lines.extend([
        "",
        "## Audit Outputs",
        "",
        "- `collector_complete_output_inventory.csv`",
        "- `collector_stage_certification_audit.csv`",
        "- `collector_authority_hash_reconciliation.csv`",
        "- `collector_mtg_standard_control_matrix.csv`",
        "- `collector_end_to_end_governance_audit_summary.json`",
        "",
        "This audit does not alter forecasts, rankings, recommendations, or source authorities.",
    ])
    (OUTPUT / "COLLECTOR_END_TO_END_GOVERNANCE_AUDIT_REPORT.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )

    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
