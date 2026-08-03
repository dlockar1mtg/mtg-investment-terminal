"""Run the governed Collector current-authority block in dependency order."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "data/governance/permanence/certification/collector_current_authority/collector_current_authority_block_summary.json"


def run_step(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT, text=True)
    return {"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Collector current authority block")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    steps = [
        run_step([sys.executable, "scripts/certify_tcgcsv_collector_current_prices.py"]),
        run_step([sys.executable, "scripts/build_governed_collector_current_authority.py"] + (["--strict"] if args.strict else [])),
    ]
    governed_map = ROOT / "data/governance/permanence/certification/collector_current_authority/governed_collector_tcgcsv_product_map.csv"
    if governed_map.is_file():
        steps.append(
            run_step(
                [
                    sys.executable,
                    "scripts/run_daily_tcgcsv_collection.py",
                    "--product-map",
                    str(governed_map),
                    "--dry-run",
                ]
            )
        )
    else:
        steps.append({"command": ["dry-run governed map"], "return_code": 1, "passed": False})

    payload = {
        "block_name": "Collector Current Authority Block",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "all_steps_passed": all(bool(step["passed"]) for step in steps),
        "live_collection_executed": False,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
    }
    payload["status"] = "PASS_CURRENT_AUTHORITY_ONLY" if payload["all_steps_passed"] else "REVIEW_REQUIRED"
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["all_steps_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
