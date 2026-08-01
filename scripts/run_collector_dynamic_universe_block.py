"""Run dynamic Collector universe discovery, optionally refreshing the full catalog first."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "data/governance/permanence/certification/collector_dynamic_universe/collector_dynamic_universe_block_summary.json"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run dynamic Collector universe block")
    p.add_argument("--refresh-catalog", action="store_true")
    p.add_argument("--max-groups", type=int)
    p.add_argument("--sleep-seconds", type=float, default=0.1)
    p.add_argument("--strict", action="store_true")
    return p


def run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT)
    return {"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0}


def main() -> int:
    args = parser().parse_args()
    steps: list[dict[str, object]] = []

    if args.refresh_catalog:
        cmd = [sys.executable, "scripts/snapshot_tcgcsv_catalog_safe.py", "--category-id", "1", "--sleep-seconds", str(max(0.0, args.sleep_seconds))]
        if args.max_groups is not None:
            cmd.extend(["--max-groups", str(args.max_groups)])
        step = run(cmd)
        steps.append(step)
        if not step["passed"]:
            payload = {
                "block_name": "Collector Dynamic Universe Block",
                "block_version": "1.0.0",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "catalog_refresh_requested": True,
                "steps": steps,
                "status": "FAIL_CATALOG_REFRESH",
                "historical_append_authorized": False,
                "forecasting_resume_authorized": False,
                "purchase_recommendation_authorized": False,
            }
            SUMMARY.parent.mkdir(parents=True, exist_ok=True)
            SUMMARY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(payload, indent=2))
            return 1

    discover_cmd = [sys.executable, "scripts/build_dynamic_collector_universe.py"]
    if args.strict:
        discover_cmd.append("--strict")
    steps.append(run(discover_cmd))

    payload = {
        "block_name": "Collector Dynamic Universe Block",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_refresh_requested": bool(args.refresh_catalog),
        "steps": steps,
        "all_steps_passed": all(bool(s["passed"]) for s in steps),
        "fixed_product_count_assumed": False,
        "automatic_new_product_admission": False,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS_DYNAMIC_UNIVERSE_BLOCK" if all(bool(s["passed"]) for s in steps) else "REVIEW_REQUIRED",
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["all_steps_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
