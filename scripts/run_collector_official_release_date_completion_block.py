"""Run official release-date authority, then rebuild tiers using that authority."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority"
OFFICIAL_AUTHORITY = OUT / "collector_official_release_date_authority.csv"
SUMMARY = OUT / "collector_official_release_date_completion_block_summary.json"


def main() -> int:
    p = argparse.ArgumentParser(description="Run Collector official release-date completion block")
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    steps = []
    commands = [
        [sys.executable, "scripts/build_collector_official_release_date_authority.py", "--strict"],
        [sys.executable, "scripts/run_collector_historical_bridge_certification_block.py", "--strict"],
        [sys.executable, "scripts/adjudicate_collector_history_and_build_tiers.py", "--authority", str(OFFICIAL_AUTHORITY), "--strict"],
    ]
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT)
        steps.append({"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0})
        if completed.returncode != 0:
            break

    release_summary_path = OUT / "collector_official_release_date_authority_summary.json"
    release_summary = json.loads(release_summary_path.read_text(encoding="utf-8-sig")) if release_summary_path.is_file() else {}
    all_passed = len(steps) == len(commands) and all(step["passed"] for step in steps)
    summary = {
        "block_name": "Collector Official Release Date Completion Block",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "governed_products": release_summary.get("governed_products", 0),
        "authorized_release_dates": release_summary.get("authorized_release_dates", 0),
        "blank_official_release_dates": release_summary.get("blank_official_release_dates", 0),
        "unverified_release_dates": release_summary.get("unverified_release_dates", 0),
        "unresolved_rows": release_summary.get("unresolved_rows", 0),
        "all_steps_passed": all_passed,
        "release_date_authority_authorized": bool(release_summary.get("release_date_authority_authorized", False)),
        "historical_append_executed": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_ZERO_BLANK_ZERO_UNVERIFIED_RELEASE_DATES" if all_passed else "REVIEW_REQUIRED",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
