"""Run official metadata, history tier refresh, and source completeness audit."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_source_completeness"
OFFICIAL_AUTHORITY = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run Collector source permanence block")
    p.add_argument("--strict", action="store_true")
    return p


def run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT)
    return {"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0}


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    strict_arg = ["--strict"] if args.strict else []
    steps = [
        run([sys.executable, "scripts/build_collector_official_release_date_authority.py", *strict_arg]),
        run([
            sys.executable,
            "scripts/run_collector_historical_bridge_certification_block.py",
            *strict_arg,
        ]),
        run([
            sys.executable,
            "scripts/adjudicate_collector_history_and_build_tiers.py",
            "--authority",
            str(OFFICIAL_AUTHORITY),
            *strict_arg,
        ]),
        run([sys.executable, "scripts/audit_collector_source_completeness.py", *strict_arg]),
    ]

    all_steps_passed = all(step["passed"] for step in steps)
    summary_path = OUT / "collector_source_completeness_summary.json"
    detail = json.loads(summary_path.read_text(encoding="utf-8-sig")) if summary_path.is_file() else {}
    summary = {
        "block_name": "Collector Source Permanence Block",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "all_steps_passed": all_steps_passed,
        "source_layer_certified": bool(detail.get("source_layer_certified", False)),
        "source_layer_blockers": int(detail.get("source_layer_blockers", 0)),
        "mtgjson_sealed_crosswalk_missing": int(detail.get("mtgjson_sealed_crosswalk_missing", 1)),
        "listing_supply_snapshot_not_certified": int(detail.get("listing_supply_snapshot_not_certified", 1)),
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_SOURCE_PERMANENCE" if all_steps_passed and detail.get("source_layer_certified") else "REVIEW_REQUIRED",
    }
    (OUT / "collector_source_permanence_block_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if all_steps_passed and (not args.strict or detail.get("source_layer_certified")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
