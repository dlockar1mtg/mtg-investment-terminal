"""Run the governed Collector eBay daily acquisition-to-continuity cycle.

The cycle is fail-closed and prevents accidental pseudo-day creation by requiring a
minimum interval since the prior live collection. It performs one live Browse API
shadow acquisition, then offline production replay, daily supply certification,
identity integrity repair, and continuity accumulation.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COLLECTION_SUMMARY = ROOT / "data/governance/permanence/certification/collector_ebay_supply_collection/collector_ebay_supply_collection_summary.json"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_daily_cycle"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run guarded Collector eBay certified daily cycle")
    p.add_argument("--minimum-hours", type=float, default=18.0)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--force", action="store_true", help="Bypass interval guard only for controlled testing")
    return p


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def run(command: list[str], env: dict[str, str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    return {"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0}


def write_summary(payload: dict[str, object]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_ebay_certified_daily_cycle_summary.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, default=str))


def main() -> int:
    args = parser().parse_args()
    now = datetime.now(timezone.utc)
    previous = read_json(COLLECTION_SUMMARY)
    previous_time = parse_time(previous.get("generated_at"))
    elapsed_hours = ((now - previous_time).total_seconds() / 3600.0) if previous_time else None

    credentials_present = bool(os.getenv("EBAY_CLIENT_ID", "").strip() and os.getenv("EBAY_CLIENT_SECRET", "").strip())
    interval_ready = previous_time is None or elapsed_hours is None or elapsed_hours >= args.minimum_hours

    if not credentials_present:
        summary = {
            "block_name": "Collector eBay Certified Daily Cycle",
            "block_version": "1.0.0",
            "generated_at": now.isoformat(),
            "credentials_present": False,
            "minimum_hours": args.minimum_hours,
            "previous_collection_at": previous_time.isoformat() if previous_time else "",
            "elapsed_hours": round(elapsed_hours, 4) if elapsed_hours is not None else "",
            "live_collection_executed": False,
            "status": "CREDENTIALS_REQUIRED",
        }
        write_summary(summary)
        return 1 if args.strict else 0

    if not interval_ready and not args.force:
        summary = {
            "block_name": "Collector eBay Certified Daily Cycle",
            "block_version": "1.0.0",
            "generated_at": now.isoformat(),
            "credentials_present": True,
            "minimum_hours": args.minimum_hours,
            "previous_collection_at": previous_time.isoformat() if previous_time else "",
            "elapsed_hours": round(elapsed_hours, 4) if elapsed_hours is not None else "",
            "next_eligible_at": (previous_time.timestamp() + args.minimum_hours * 3600) if previous_time else "",
            "live_collection_executed": False,
            "force_used": False,
            "status": "DAILY_INTERVAL_NOT_REACHED",
        }
        write_summary(summary)
        return 1 if args.strict else 0

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")

    commands = [
        [sys.executable, "scripts/run_collector_packaging_and_ebay_foundation_block.py", "--ebay-mode", "shadow", "--strict"],
        [sys.executable, "scripts/run_collector_ebay_authority_reconciliation_block.py", "--strict"],
        [sys.executable, "scripts/run_collector_ebay_daily_supply_integrity_block.py", "--strict"],
        [sys.executable, "scripts/run_collector_ebay_supply_continuity_block.py", "--strict"],
    ]

    steps: list[dict[str, object]] = []
    for command in commands:
        result = run(command, env)
        steps.append(result)
        if not result["passed"]:
            break

    passed = len(steps) == len(commands) and all(bool(step["passed"]) for step in steps)
    continuity = read_json(
        ROOT / "data/governance/permanence/certification/collector_ebay_supply_continuity/collector_ebay_supply_continuity_summary.json"
    )
    cycle_collection = read_json(COLLECTION_SUMMARY)

    summary = {
        "block_name": "Collector eBay Certified Daily Cycle",
        "block_version": "1.0.0",
        "generated_at": now.isoformat(),
        "credentials_present": True,
        "minimum_hours": args.minimum_hours,
        "previous_collection_at": previous_time.isoformat() if previous_time else "",
        "elapsed_hours": round(elapsed_hours, 4) if elapsed_hours is not None else "",
        "force_used": bool(args.force),
        "steps": steps,
        "live_collection_executed": bool(steps),
        "cycle_passed": passed,
        "collection_status": cycle_collection.get("status", ""),
        "continuity_status": continuity.get("status", ""),
        "certified_snapshot_days": continuity.get("certified_snapshot_days", 0),
        "trend_features_available": continuity.get("trend_features_available", False),
        "full_supply_scarcity_index_authorized": continuity.get("full_supply_scarcity_index_authorized", False),
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_EBAY_CERTIFIED_DAILY_CYCLE" if passed else "REVIEW_REQUIRED",
    }
    write_summary(summary)
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
