"""Run a controlled live Collector TCGCSV pull and continuity certification.

The block requires the governed 50-product map, writes fresh observations to a
new operational file, relies on the collector's immutable raw vaulting, and
never appends to historical data.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = ROOT / "data/governance/permanence/certification/collector_current_authority/governed_collector_tcgcsv_product_map.csv"
DEFAULT_OBS = ROOT / "data/operations/tcgcsv/collector_live_price_observations.csv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_live_current_prices/collector_live_current_price_block_summary.json"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run controlled live Collector current-price block")
    p.add_argument("--product-map", type=Path, default=DEFAULT_MAP)
    p.add_argument("--observations-output", type=Path, default=DEFAULT_OBS)
    p.add_argument("--summary-output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p


def run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return {
        "command": command,
        "return_code": completed.returncode,
        "passed": completed.returncode == 0,
    }


def main() -> int:
    args = parser().parse_args()
    product_map = args.product_map.resolve()
    observations = args.observations_output.resolve()
    summary_path = args.summary_output.resolve()
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    steps: list[dict[str, object]] = []

    dry_run = [
        sys.executable,
        "scripts/run_daily_tcgcsv_collection.py",
        "--product-map",
        str(product_map),
        "--observations-output",
        str(observations),
        "--dry-run",
    ]
    steps.append(run(dry_run))

    if steps[-1]["passed"]:
        live = [
            sys.executable,
            "scripts/run_daily_tcgcsv_collection.py",
            "--product-map",
            str(product_map),
            "--observations-output",
            str(observations),
        ]
        steps.append(run(live))

    if steps[-1]["passed"] and observations.is_file():
        certify = [
            sys.executable,
            "scripts/certify_collector_live_current_prices.py",
            "--fresh-observations",
            str(observations),
        ]
        if args.strict:
            certify.append("--strict")
        steps.append(run(certify))

    all_passed = bool(steps) and all(bool(step["passed"]) for step in steps)
    payload = {
        "block_name": "Collector Live Current Price Block",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product_map": str(product_map),
        "observations_output": str(observations),
        "steps": steps,
        "all_steps_passed": all_passed,
        "live_collection_executed": len(steps) >= 2,
        "historical_append_executed": False,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS_LIVE_CURRENT_PRICE_CANDIDATES_ONLY" if all_passed else "FAIL",
    }
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
