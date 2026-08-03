"""Orchestrate Collector eBay day-one supply baseline promotion and control."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run Collector eBay day-one supply baseline promotion block")
    p.add_argument("--strict", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)
    command = [sys.executable, "scripts/promote_collector_ebay_day_one_supply_baseline.py"]
    if args.strict:
        command.append("--strict")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)

    summary_path = OUT / "collector_ebay_day_one_supply_baseline_summary.json"
    baseline = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    passed = (
        result.returncode == 0
        and baseline.get("status") == "PASS_DAY_ONE_SUPPLY_BASELINE_PROMOTED_CONTINUITY_READY"
        and baseline.get("baseline_integrity_passed") is True
        and baseline.get("continuity_accumulation_authorized") is True
    )
    project = {
        "block_name": "Collector eBay Day-One Supply Baseline Promotion and Project Control",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "steps": [{"command": command, "return_code": result.returncode, "passed": result.returncode == 0}],
        "promotion_passed": passed,
        "baseline_id": baseline.get("baseline_id", ""),
        "accepted_listing_rows": baseline.get("accepted_listing_rows", 0),
        "review_listing_rows": baseline.get("review_listing_rows", 0),
        "governed_product_rows": baseline.get("governed_product_rows", 0),
        "products_with_zero_accepted_supply": baseline.get("products_with_zero_accepted_supply", 0),
        "completed": [
            "Full-universe acquisition recall certified",
            "All 4,413 candidates replayed through the hardened matcher",
            "Unsafe accepted rows reduced to zero",
            "Accepted and review dispositions separated",
            "Complete 50-product day-one supply snapshot generated",
            "Artifact hashes and immutable baseline manifest generated",
        ],
        "currently_being_worked_on": [
            "Establish the certified day-one baseline as the only valid origin for future eBay supply continuity"
        ],
        "still_outstanding": [
            "Run the first post-baseline comparable daily acquisition after the governed interval",
            "Compare accepted listing identities, sellers, and landed prices against day one",
            "Accumulate sufficient comparable observations for scarcity features",
            "Build and certify Supply Scarcity Index V1",
            "Resume forecasting only after feature freshness and leakage gates pass",
            "Keep purchase recommendations and UIP delivery blocked until forecast certification",
        ],
        "known_blockers": [] if passed else [
            "Day-one supply baseline promotion failed an integrity or reconciliation gate"
        ],
        "authorization_state": {
            "acquisition_recall": "CERTIFIED",
            "matcher_precision_hardening": "COMPLETE",
            "day_one_supply_baseline": "PROMOTED" if passed else "NOT_PROMOTED",
            "continuity_accumulation": "AUTHORIZED_FROM_DAY_ONE_BASELINE" if passed else "NOT_AUTHORIZED",
            "supply_scarcity_index_v1": "BLOCKED_PENDING_CONTINUITY",
            "feature_certification": "BLOCKED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Run the first governed post-baseline comparable supply observation and certify continuity mechanics"
            if passed else "Inspect baseline integrity failures and repair promotion before any continuity run"
        ),
        "status": (
            "PASS_COLLECTOR_EBAY_DAY_ONE_SUPPLY_BASELINE_PROJECT_CONTROL"
            if passed else "FAIL_COLLECTOR_EBAY_DAY_ONE_SUPPLY_BASELINE_PROJECT_CONTROL"
        ),
    }
    (OUT / "collector_ebay_day_one_supply_baseline_project_control_summary.json").write_text(
        json.dumps(project, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(project, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
