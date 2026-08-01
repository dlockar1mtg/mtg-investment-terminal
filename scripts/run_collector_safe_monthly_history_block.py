"""Run Collector historical source-grain audit and safe monthly candidate build."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_safe_monthly_history"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run Collector safe monthly history block")
    p.add_argument("--strict", action="store_true")
    return p


def run(command: list[str]) -> dict[str, object]:
    result = subprocess.run(command, cwd=ROOT)
    return {"command": command, "return_code": result.returncode, "passed": result.returncode == 0}


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, object]] = []

    grain_cmd = [sys.executable, "scripts/audit_collector_historical_source_grain.py"]
    if args.strict:
        grain_cmd.append("--strict")
    grain = run(grain_cmd)
    steps.append(grain)

    if grain["passed"]:
        build_cmd = [sys.executable, "scripts/build_collector_safe_monthly_history_candidate.py"]
        if args.strict:
            build_cmd.append("--strict")
        steps.append(run(build_cmd))

    passed = bool(steps) and all(bool(step["passed"]) for step in steps)
    summary = {
        "block_name": "Collector Safe Monthly History Block",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "all_steps_passed": passed,
        "listing_rows_selected_as_monthly_market_price": False,
        "historical_append_executed": False,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS_SAFE_MONTHLY_HISTORY_CANDIDATE_ONLY" if passed else "REVIEW_REQUIRED",
    }
    (OUT / "collector_safe_monthly_history_block_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
