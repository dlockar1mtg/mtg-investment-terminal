from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_canary_matcher_hardening"
SUMMARY = OUT / "collector_ebay_canary_matcher_hardening_summary.json"
CONTROL = OUT / "collector_ebay_canary_matcher_hardening_project_control_summary.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    command = [sys.executable, "scripts/audit_collector_ebay_canary_matcher_hardening.py"]
    if args.strict:
        command.append("--strict")
    completed = subprocess.run(command, cwd=ROOT, env=env)

    payload = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.exists() else {}
    passed = completed.returncode == 0 and bool(payload)
    control = {
        "block_name": "Collector eBay Canary Matcher Hardening and Project Control",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": [{"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0}],
        "offline_only": True,
        "quota_calls": 0,
        "audit_passed": passed,
        "canary_listing_rows": payload.get("canary_listing_rows", 0),
        "hardening_findings": payload.get("hardening_findings", 0),
        "blocker_rows": payload.get("blocker_rows", 0),
        "lotr_alias_review_rows": payload.get("lotr_alias_review_rows", 0),
        "completed": [
            "Six-product high-recall canary completed",
            "Candidate recall improvement demonstrated for all six products",
            "Canary matcher outcomes preserved for offline adjudication",
            "Full-universe authorization revoked pending precision hardening",
        ],
        "currently_being_worked_on": [
            "Resolve multi-unit/case acceptance, year-as-quantity parsing, and Lord of the Rings alias handling"
        ],
        "still_outstanding": [
            "Implement precision matcher regression rules",
            "Replay all 601 canary rows offline through the hardened matcher",
            "Confirm zero unsafe accepts and resolve valid Lord of the Rings reviews",
            "Authorize one 50-product high-recall acquisition only after strict replay passes",
            "Establish the true marketplace-supply baseline after acquisition certification",
        ],
        "known_blockers": [
            "Canary exposed matcher hardening requirements; full-universe acquisition is not authorized"
        ],
        "authorization_state": {
            "ebay_acquisition_recall_canary": "COMPLETE",
            "candidate_recall_improvement": "CONFIRMED",
            "matcher_precision_hardening": "REQUIRED",
            "full_universe_collection": "BLOCKED_PENDING_HARDENING",
            "current_supply_baseline": "NOT_AUTHORIZED",
            "continuity_accumulation": "NOT_AUTHORIZED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": "Implement matcher hardening and replay all 601 canary candidates offline",
        "full_universe_collection_authorized": False,
        "continuity_accumulation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_CANARY_MATCHER_HARDENING_PROJECT_CONTROL" if passed else "REVIEW_REQUIRED",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    CONTROL.write_text(json.dumps(control, indent=2), encoding="utf-8")
    print(json.dumps(control, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
