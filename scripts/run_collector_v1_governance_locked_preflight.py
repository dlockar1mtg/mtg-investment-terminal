from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "audit_collector_v1_chat_governance_conformance.py"
DEFAULT_SEARCH_ROOT = ROOT / "data"
DEFAULT_OUTPUT = ROOT / "data" / "governance" / "permanence" / "certification" / "collector_v1_governance_locked_preflight"
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OPERATING_DATE = "2026-08-01"
TIMEZONE = "America/Chicago"
BUNDLE_SHA = "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
PRODUCT_COUNT = 50
MAX_TEXT_BYTES = 10 * 1024 * 1024

IDENTITY_FIELD_ALIASES = {
    "snapshot_id": ("snapshot_id", "package_id"),
    "operating_date": ("operating_date", "snapshot_date", "as_of_date"),
    "timezone": ("timezone", "operating_timezone"),
    "source_bundle_sha256": ("source_bundle_sha256", "bundle_sha256", "sha256"),
    "certified_product_count": ("certified_product_count", "product_count", "governed_product_count"),
}

MANIFEST_FILENAME_HINTS = (
    "snapshot_manifest",
    "package_manifest",
    "package_summary",
    "source_manifest",
)

SNAPSHOT_PATH_HINTS = (
    "20260801",
    "2026-08-01",
    "august_1",
    "august1",
    SNAPSHOT_ID.lower(),
)

NONAUTHORITATIVE_PATH_TERMS = (
    "/certification/",
    "/validation/",
    "/tests/",
    "/test/",
    "/reports/",
    "/report/",
    "/backup/",
    "/backups/",
    "/attempt/",
    "/attempts/",
)

AUTHORITATIVE_SNAPSHOT_PATH_PREFIX = "/data/governance/permanence/snapshots/"
REQUIRED_FIFTY_ROW_ROLES = (
    "live_price_observations",
    "current_authority",
    "live_price_candidates",
    "ebay_supply_snapshot",
    "feature_matrix",
)


def nested_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for current_key, item in value.items():
            if str(current_key).lower() == key.lower():
                found.append(item)
            found.extend(nested_values(item, key))
    elif isinstance(value, list):
        for item in value:
            found.extend(nested_values(item, key))
    return found


def first_alias_value(payload: dict[str, Any], aliases: tuple[str, ...]) -> Any | None:
    for alias in aliases:
        values = nested_values(payload, alias)
        if values:
            return values[0]
    return None


def read_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"READ_OR_PARSE_ERROR:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return None, "TOP_LEVEL_JSON_NOT_OBJECT"
    return payload, ""


def registered_product_count_valid(payload: dict[str, Any]) -> bool:
    explicit = first_alias_value(payload, IDENTITY_FIELD_ALIASES["certified_product_count"])
    if explicit is not None:
        return str(explicit) == str(PRODUCT_COUNT)

    files = payload.get("files")
    if not isinstance(files, list):
        return False

    rows_by_role: dict[str, Any] = {}
    for item in files:
        if isinstance(item, dict) and item.get("role"):
            rows_by_role[str(item["role"])] = item.get("rows")

    role_rows_valid = all(
        str(rows_by_role.get(role, "")) == str(PRODUCT_COUNT)
        for role in REQUIRED_FIFTY_ROW_ROLES
    )
    checks = payload.get("checks")
    checks_valid = isinstance(checks, dict) and all(
        checks.get(control) is True
        for control in (
            "all_required_authorities_present",
            "all_registered_artifacts_in_august_1_operating_cycle",
            "all_required_row_coverage_valid",
            "all_json_controls_parseable",
            "no_json_control_reports_explicit_failure",
            "source_hash_bundle_created",
        )
    )
    critical_failures = payload.get("critical_failures")
    no_critical_failures = isinstance(critical_failures, list) and not critical_failures
    status_valid = payload.get("status") == "PASS_COLLECTOR_V1_AUGUST_1_GOVERNED_SNAPSHOT_REGISTRATION"
    model_input_valid = payload.get("certified_for_model_input") is True
    purchase_boundary_valid = payload.get("purchase_recommendations_authorized") is False

    return all(
        (
            role_rows_valid,
            checks_valid,
            no_critical_failures,
            status_valid,
            model_input_valid,
            purchase_boundary_valid,
        )
    )


def identity_values(payload: dict[str, Any]) -> dict[str, Any | None]:
    return {
        "snapshot_id": first_alias_value(payload, IDENTITY_FIELD_ALIASES["snapshot_id"]),
        "operating_date": first_alias_value(payload, IDENTITY_FIELD_ALIASES["operating_date"]),
        "timezone": first_alias_value(payload, IDENTITY_FIELD_ALIASES["timezone"]),
        "source_bundle_sha256": first_alias_value(payload, IDENTITY_FIELD_ALIASES["source_bundle_sha256"]),
        "certified_product_count": PRODUCT_COUNT if registered_product_count_valid(payload) else None,
    }


def path_text(path: Path) -> str:
    return "/" + str(path).replace("\\", "/").lower().lstrip("/")


def is_nonauthoritative_path(normalized_path: str) -> bool:
    if AUTHORITATIVE_SNAPSHOT_PATH_PREFIX in normalized_path:
        return False
    return any(term in normalized_path for term in NONAUTHORITATIVE_PATH_TERMS)


def adjudicate_manifest(path: Path) -> dict[str, Any]:
    relative = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    normalized_path = path_text(path)
    filename = path.name.lower()
    payload, read_error = read_json(path)

    row: dict[str, Any] = {
        "candidate_path": relative,
        "candidate_role": "REJECTED",
        "identity_match": False,
        "filename_authority_hint": any(hint in filename for hint in MANIFEST_FILENAME_HINTS),
        "snapshot_path_hint": any(hint in normalized_path for hint in SNAPSHOT_PATH_HINTS),
        "generated_or_nonauthoritative_path": is_nonauthoritative_path(normalized_path),
        "rejection_reasons": "",
    }

    reasons: list[str] = []
    if read_error:
        reasons.append(read_error)
        row["rejection_reasons"] = "|".join(reasons)
        return row

    assert payload is not None
    values = identity_values(payload)
    identity_checks = {
        "SNAPSHOT_ID_MISMATCH": str(values["snapshot_id"] or "") == SNAPSHOT_ID,
        "OPERATING_DATE_MISMATCH": str(values["operating_date"] or "")[:10] == OPERATING_DATE,
        "TIMEZONE_MISMATCH": str(values["timezone"] or "") == TIMEZONE,
        "SOURCE_BUNDLE_SHA256_MISMATCH": str(values["source_bundle_sha256"] or "").lower() == BUNDLE_SHA,
        "CERTIFIED_PRODUCT_COUNT_MISMATCH": str(values["certified_product_count"] or "") == str(PRODUCT_COUNT),
    }
    for reason, passed in identity_checks.items():
        if not passed:
            reasons.append(reason)

    row["identity_match"] = not reasons
    if not row["filename_authority_hint"]:
        reasons.append("FILENAME_NOT_MANIFEST_AUTHORITY")
    if not row["snapshot_path_hint"]:
        reasons.append("PATH_NOT_BOUND_TO_AUGUST_1_SNAPSHOT")
    if row["generated_or_nonauthoritative_path"]:
        reasons.append("GENERATED_OR_NONAUTHORITATIVE_COPY")

    if not reasons:
        row["candidate_role"] = "AUTHORITATIVE_SNAPSHOT_MANIFEST"
    elif row["identity_match"]:
        row["candidate_role"] = "IDENTITY_COPY_NOT_AUTHORITATIVE"

    row["rejection_reasons"] = "|".join(reasons)
    return row


def candidate_manifests(search_root: Path) -> list[Path]:
    matches: list[Path] = []
    if not search_root.exists():
        return matches
    for path in sorted(search_root.rglob("*.json")):
        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                continue
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        if SNAPSHOT_ID in text and BUNDLE_SHA in text:
            matches.append(path.resolve())
    return matches


def validate_manifest(path: Path) -> tuple[bool, list[str], dict[str, Any] | None]:
    payload, read_error = read_json(path)
    if read_error:
        return False, [read_error], payload
    assert payload is not None
    values = identity_values(payload)
    reasons: list[str] = []
    checks = {
        "SNAPSHOT_ID_MISMATCH": str(values["snapshot_id"] or "") == SNAPSHOT_ID,
        "OPERATING_DATE_MISMATCH": str(values["operating_date"] or "")[:10] == OPERATING_DATE,
        "TIMEZONE_MISMATCH": str(values["timezone"] or "") == TIMEZONE,
        "SOURCE_BUNDLE_SHA256_MISMATCH": str(values["source_bundle_sha256"] or "").lower() == BUNDLE_SHA,
        "CERTIFIED_PRODUCT_COUNT_MISMATCH": str(values["certified_product_count"] or "") == str(PRODUCT_COUNT),
    }
    for reason, passed in checks.items():
        if not passed:
            reasons.append(reason)
    return not reasons, reasons, payload


def write_outputs(output_root: Path, summary: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "collector_governance_locked_preflight_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    fields = [
        "candidate_path",
        "candidate_role",
        "identity_match",
        "filename_authority_hint",
        "snapshot_path_hint",
        "generated_or_nonauthoritative_path",
        "rejection_reasons",
    ]
    with (output_root / "collector_snapshot_manifest_candidate_adjudication.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidates)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the mandatory Collector governance and August 1 snapshot preflight.")
    parser.add_argument("--search-root", type=Path, default=DEFAULT_SEARCH_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summary: dict[str, Any] = {
        "block_name": "Collector V1 Governance-Locked Preflight",
        "governing_snapshot_id": SNAPSHOT_ID,
        "governing_operating_date": OPERATING_DATE,
        "governing_timezone": TIMEZONE,
        "governing_source_bundle_sha256": BUNDLE_SHA,
        "governing_certified_product_count": PRODUCT_COUNT,
        "governance_audit_passed": False,
        "snapshot_manifest_resolved": False,
        "snapshot_manifest_path": "",
        "snapshot_manifest_match_count": 0,
        "authoritative_snapshot_manifest_count": 0,
        "snapshot_identity_verified": False,
        "historical_price_recovery_authorized": False,
        "historical_coverage_measurement_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": "BLOCKED_PRECHECK_NOT_RUN",
        "failure_reasons": [],
    }

    audit = subprocess.run([sys.executable, str(AUDIT)], cwd=ROOT, check=False)
    if audit.returncode != 0:
        summary["status"] = "BLOCKED_GOVERNANCE_CONFORMANCE_FAILED"
        summary["failure_reasons"] = [f"GOVERNANCE_AUDIT_EXIT_CODE_{audit.returncode}"]
        write_outputs(args.output_root.resolve(), summary, [])
        print(json.dumps(summary, indent=2))
        return 2
    summary["governance_audit_passed"] = True

    raw_matches = candidate_manifests(args.search_root.resolve())
    candidates = [adjudicate_manifest(path) for path in raw_matches]
    authoritative = [
        row for row in candidates
        if row["candidate_role"] == "AUTHORITATIVE_SNAPSHOT_MANIFEST"
    ]
    summary["snapshot_manifest_match_count"] = len(raw_matches)
    summary["authoritative_snapshot_manifest_count"] = len(authoritative)

    if len(authoritative) != 1:
        summary["status"] = (
            "BLOCKED_SNAPSHOT_MANIFEST_NOT_RESOLVED"
            if not authoritative
            else "BLOCKED_MULTIPLE_AUTHORITATIVE_SNAPSHOT_MANIFESTS"
        )
        summary["failure_reasons"] = [summary["status"]]
        write_outputs(args.output_root.resolve(), summary, candidates)
        print(json.dumps(summary, indent=2))
        return 3

    manifest_path_text = authoritative[0]["candidate_path"]
    manifest = ROOT / manifest_path_text
    summary["snapshot_manifest_resolved"] = True
    summary["snapshot_manifest_path"] = manifest_path_text
    valid, reasons, _ = validate_manifest(manifest)
    if not valid:
        summary["status"] = "BLOCKED_SNAPSHOT_IDENTITY_MISMATCH"
        summary["failure_reasons"] = reasons
        write_outputs(args.output_root.resolve(), summary, candidates)
        print(json.dumps(summary, indent=2))
        return 4

    summary["snapshot_identity_verified"] = True
    summary["status"] = "PASS_COLLECTOR_AUGUST_1_SNAPSHOT_CONFORMANCE"
    write_outputs(args.output_root.resolve(), summary, candidates)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
