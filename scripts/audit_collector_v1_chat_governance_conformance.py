from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_chat_governance_conformance"
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OPERATING_DATE = "2026-08-01"
BUNDLE_SHA = "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
PRODUCT_COUNT = 50
AUDIT_RECORDED_AT_UTC = "2026-08-02T15:23:01+00:00"

ARTIFACTS = [
    "config/mtg/standards/collector_evidence_tournament_contract_v1.json",
    "config/mtg/standards/collector_first_year_breakout_entry_timing_contract_v1.json",
    "config/mtg/standards/collector_historical_feature_availability_contract_v1.json",
    "config/mtg/standards/collector_historical_row_level_temporal_verification_contract_v1.json",
    "config/mtg/standards/collector_historical_source_scope_lineage_contract_v1.json",
    "config/mtg/standards/collector_historical_source_precedence_contract_v1.json",
    "config/mtg/standards/collector_model_input_raw_lineage_contract_v1.json",
    "config/mtg/standards/collector_history_foundation_lineage_contract_v1.json",
    "config/mtg/standards/collector_history_foundation_reproducibility_contract_v1.json",
    "config/mtg/standards/collector_frozen_history_source_manifest_contract_v1.json",
    "config/mtg/standards/collector_tcgcsv_authority_verification_contract_v1.json",
    "config/mtg/standards/collector_historical_price_recovery_contract_v1.json",
    "config/mtg/standards/collector_governance_locked_preflight_contract_v1.json",
    "scripts/build_collector_v1_evidence_tournament_reconstruction_plan.py",
    "scripts/build_collector_v1_first_year_breakout_reconstruction_plan.py",
    "scripts/audit_collector_v1_historical_feature_availability.py",
    "scripts/verify_collector_v1_historical_rows.py",
    "scripts/adjudicate_collector_v1_historical_source_scope_lineage.py",
    "scripts/build_collector_v1_historical_source_precedence_registry.py",
    "scripts/trace_collector_v1_model_input_raw_lineage.py",
    "scripts/trace_collector_v1_history_foundation_lineage.py",
    "scripts/audit_collector_v1_history_foundation_reproducibility.py",
    "scripts/build_collector_v1_frozen_history_source_manifest.py",
    "scripts/verify_collector_v1_tcgcsv_historical_authority.py",
    "scripts/recover_collector_v1_historical_price_authority.py",
    "scripts/run_collector_v1_governance_locked_preflight.py",
]

PROHIBITED_RECOVERY_PATTERNS = [
    "datetime.now(timezone.utc)",
    "rglob(\"*.csv\")",
    "APPROVED_ROOTS",
    "build_universe(args.universe.resolve())",
    "historical_authority = len(ledger) > 0",
]


def add(rows, artifact, control, status, severity, detail):
    rows.append({"artifact": artifact, "control": control, "status": status, "severity": severity, "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Retained for compatibility; audit is always fail-closed.")
    parser.parse_args()
    findings = []

    for rel in ARTIFACTS:
        path = ROOT / rel
        if not path.exists():
            add(findings, rel, "artifact_presence", "FAIL", "CRITICAL", "Required chat artifact missing")
            continue
        text = path.read_text(encoding="utf-8")
        add(findings, rel, "artifact_presence", "PASS", "INFO", "Artifact exists")
        if "purchase_recommendations_authorized\": true" in text.lower():
            add(findings, rel, "purchase_authorization", "FAIL", "CRITICAL", "Unauthorized purchase flag")
        if "model_tournament_authorized\": true" in text.lower():
            add(findings, rel, "model_authorization", "FAIL", "CRITICAL", "Unauthorized model tournament flag")

    first_year = (ROOT / "config/mtg/standards/collector_first_year_breakout_entry_timing_contract_v1.json").read_text(encoding="utf-8")
    add(findings, "collector_first_year_breakout_entry_timing_contract_v1.json", "checkpoints", "PASS" if all(str(x) in first_year for x in (0, 30, 60, 90, 120, 180, 270, 365)) else "FAIL", "CRITICAL", "Governed first-year checkpoints")
    add(findings, "collector_first_year_breakout_entry_timing_contract_v1.json", "panel_authorization", "PASS" if '"lifecycle_panel_reconstruction_authorized": false' in first_year else "FAIL", "CRITICAL", "Panel must remain unauthorized")

    tournament = (ROOT / "config/mtg/standards/collector_evidence_tournament_contract_v1.json").read_text(encoding="utf-8")
    for horizon in (90, 180, 365, 1095, 1825):
        add(findings, "collector_evidence_tournament_contract_v1.json", f"horizon_{horizon}", "PASS" if str(horizon) in tournament else "FAIL", "CRITICAL", "Required governed horizon")

    recovery = ROOT / "scripts/recover_collector_v1_historical_price_authority.py"
    recovery_text = recovery.read_text(encoding="utf-8") if recovery.exists() else ""
    for pattern in PROHIBITED_RECOVERY_PATTERNS:
        add(findings, str(recovery.relative_to(ROOT)), f"recovery_drift:{pattern}", "FAIL" if pattern in recovery_text else "PASS", "CRITICAL", "Recovery must be August-1 snapshot-bound and fail closed")
    for token, control in ((SNAPSHOT_ID, "snapshot_id"), (OPERATING_DATE, "operating_date"), (BUNDLE_SHA, "bundle_sha"), (str(PRODUCT_COUNT), "product_count")):
        add(findings, str(recovery.relative_to(ROOT)), control, "PASS" if token in recovery_text else "FAIL", "CRITICAL", "Mandatory August 1 binding")

    recovery_contract = (ROOT / "config/mtg/standards/collector_historical_price_recovery_contract_v1.json").read_text(encoding="utf-8")
    add(findings, "collector_historical_price_recovery_contract_v1.json", "broad_roots_revoked", "PASS" if '"approved_source_roots": []' in recovery_contract else "FAIL", "CRITICAL", "Broad source roots must remain revoked")
    add(findings, "collector_historical_price_recovery_contract_v1.json", "recovery_authorization", "PASS" if '"historical_price_recovery_authorized": false' in recovery_contract else "FAIL", "CRITICAL", "Recovery remains blocked until snapshot conformance")

    preflight = ROOT / "scripts/run_collector_v1_governance_locked_preflight.py"
    preflight_text = preflight.read_text(encoding="utf-8") if preflight.exists() else ""
    for token, control in ((SNAPSHOT_ID, "preflight_snapshot_id"), (OPERATING_DATE, "preflight_operating_date"), (TIMEZONE if False else "America/Chicago", "preflight_timezone"), (BUNDLE_SHA, "preflight_bundle_sha"), (str(PRODUCT_COUNT), "preflight_product_count")):
        add(findings, str(preflight.relative_to(ROOT)), control, "PASS" if token in preflight_text else "FAIL", "CRITICAL", "Mandatory preflight binding")
    add(findings, str(preflight.relative_to(ROOT)), "preflight_runs_governance_first", "PASS" if "subprocess.run([sys.executable, str(AUDIT)]" in preflight_text else "FAIL", "CRITICAL", "Governance audit must execute before snapshot resolution")

    summary_path = ROOT / "data/governance/permanence/certification/collector_v1_historical_price_recovery/collector_historical_price_recovery_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        revoked = summary.get("status") == "PASS_COLLECTOR_V1_HISTORICAL_PRICE_RECOVERY_AND_COVERAGE" or summary.get("raw_historical_price_authority_certified") is True
        add(findings, str(summary_path.relative_to(ROOT)), "revoked_recovery_result", "FAIL" if revoked else "PASS", "CRITICAL", "Latest broad-root recovery result is revoked")

    failures = [row for row in findings if row["status"] == "FAIL"]
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "collector_chat_governance_conformance_findings.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["artifact", "control", "status", "severity", "detail"])
        writer.writeheader()
        writer.writerows(findings)

    summary = {
        "block_name": "Collector Chat Governance Conformance Audit",
        "generated_at_utc": AUDIT_RECORDED_AT_UTC,
        "governing_snapshot_id": SNAPSHOT_ID,
        "governing_operating_date": OPERATING_DATE,
        "governing_source_bundle_sha256": BUNDLE_SHA,
        "governing_product_count": PRODUCT_COUNT,
        "artifact_count": len(ARTIFACTS),
        "finding_count": len(findings),
        "critical_failure_count": len(failures),
        "historical_price_authority_certified": False,
        "historical_coverage_assessment_completed": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": "PASS_COLLECTOR_CHAT_GOVERNANCE_CONFORMANCE" if not failures else "FAIL_COLLECTOR_CHAT_GOVERNANCE_CONFORMANCE",
    }
    (OUT / "collector_chat_governance_conformance_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
