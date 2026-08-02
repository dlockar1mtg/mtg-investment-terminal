from __future__ import annotations

import argparse
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


def flatten(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            values.append(str(key))
            values.extend(flatten(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(flatten(item))
    elif value is not None:
        values.append(str(value))
    return values


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
    reasons: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, [f"MANIFEST_READ_OR_PARSE_ERROR:{type(exc).__name__}"], None

    flattened = flatten(payload)
    joined = "\n".join(flattened)
    required = {
        "SNAPSHOT_ID_MISMATCH": SNAPSHOT_ID,
        "OPERATING_DATE_MISMATCH": OPERATING_DATE,
        "TIMEZONE_MISMATCH": TIMEZONE,
        "SOURCE_BUNDLE_SHA256_MISMATCH": BUNDLE_SHA,
    }
    for reason, expected in required.items():
        if expected not in joined:
            reasons.append(reason)

    numeric_values = {value for value in flattened if value.isdigit()}
    if str(PRODUCT_COUNT) not in numeric_values:
        reasons.append("CERTIFIED_PRODUCT_COUNT_MISMATCH")

    return not reasons, reasons, payload


def write_summary(output_root: Path, summary: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "collector_governance_locked_preflight_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )


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
        write_summary(args.output_root.resolve(), summary)
        print(json.dumps(summary, indent=2))
        return 2
    summary["governance_audit_passed"] = True

    manifests = candidate_manifests(args.search_root.resolve())
    summary["snapshot_manifest_match_count"] = len(manifests)
    if len(manifests) != 1:
        summary["status"] = "BLOCKED_SNAPSHOT_MANIFEST_NOT_RESOLVED" if not manifests else "BLOCKED_MULTIPLE_SNAPSHOT_MANIFESTS"
        summary["failure_reasons"] = [summary["status"]]
        write_summary(args.output_root.resolve(), summary)
        print(json.dumps(summary, indent=2))
        return 3

    manifest = manifests[0]
    summary["snapshot_manifest_resolved"] = True
    summary["snapshot_manifest_path"] = str(manifest.relative_to(ROOT)) if manifest.is_relative_to(ROOT) else str(manifest)
    valid, reasons, _ = validate_manifest(manifest)
    if not valid:
        summary["status"] = "BLOCKED_SNAPSHOT_IDENTITY_MISMATCH"
        summary["failure_reasons"] = reasons
        write_summary(args.output_root.resolve(), summary)
        print(json.dumps(summary, indent=2))
        return 4

    summary["snapshot_identity_verified"] = True
    summary["status"] = "PASS_COLLECTOR_AUGUST_1_SNAPSHOT_CONFORMANCE"
    write_summary(args.output_root.resolve(), summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
