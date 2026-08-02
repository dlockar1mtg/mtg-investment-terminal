from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "data/governance/permanence/certification/collector_ebay_canary_hardened_replay"
SUMMARY_PATH = OUTPUT_ROOT / "collector_ebay_canary_hardened_replay_summary.json"
CONTROL_PATH = OUTPUT_ROOT / "collector_ebay_canary_hardened_replay_project_control_summary.json"


def run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT, text=True)
    return {"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    steps = [
        run([sys.executable, "-m", "pytest", "tests/test_ebay_canary_hardening_regressions.py", "-q"]),
        run([sys.executable, "scripts/replay_collector_ebay_canary_after_hardening.py", "--strict"]),
    ]
    replay = json.loads(SUMMARY_PATH.read_text(encoding="utf-8")) if SUMMARY_PATH.exists() else {}
    passed = all(bool(step["passed"]) for step in steps) and bool(replay.get("full_universe_collection_authorized"))
    control = {
        "block_name": "Collector eBay Canary Hardened Replay and Project Control",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "steps": steps,
        "replay_passed": passed,
        "replayed_rows": replay.get("replayed_rows", 0),
        "year_as_quantity_defects": replay.get("year_as_quantity_defects", -1),
        "unsafe_accepted_rows": replay.get("unsafe_accepted_rows", -1),
        "lotr_accepted_rows": replay.get("lotr_accepted_rows", 0),
        "authorization_state": {
            "candidate_recall_improvement": "CONFIRMED",
            "matcher_precision_hardening": "COMPLETE" if passed else "REMEDIATION_REQUIRED",
            "full_universe_collection": "AUTHORIZED_ONE_CERTIFICATION_RUN" if passed else "BLOCKED",
            "current_supply_baseline": "NOT_AUTHORIZED",
            "continuity_accumulation": "NOT_AUTHORIZED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Run one governed 50-product high-recall acquisition and certify its acquisition coverage"
            if passed else "Inspect hardened replay failures and continue matcher remediation"
        ),
        "status": "PASS_CANARY_HARDENED_REPLAY_PROJECT_CONTROL" if passed else "FAIL_CANARY_HARDENED_REPLAY_PROJECT_CONTROL",
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    CONTROL_PATH.write_text(json.dumps(control, indent=2), encoding="utf-8")
    print(json.dumps(control, indent=2))
    return 0 if (passed or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
