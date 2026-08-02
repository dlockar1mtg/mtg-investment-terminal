from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_hardened_replay"
SUMMARY = OUT / "collector_ebay_full_universe_hardened_replay_summary.json"
CONTROL = OUT / "collector_ebay_full_universe_hardened_replay_project_control_summary.json"


def run(command: list[str]) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    return {"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    steps = [
        run([sys.executable, "-m", "pytest", "tests/test_ebay_canary_hardening_regressions.py", "-q"]),
        run([sys.executable, "scripts/replay_collector_ebay_full_universe_after_multiplier_hardening.py", "--strict"]),
    ]
    summary = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.is_file() else {}
    passed = all(bool(step["passed"]) for step in steps) and bool(summary.get("supply_baseline_authorized"))
    control = {
        "block_name": "Collector eBay Full-Universe Hardened Replay and Project Control",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "steps": steps,
        "replay_passed": passed,
        "replayed_rows": summary.get("replayed_rows", 0),
        "unsafe_accepted_rows": summary.get("unsafe_accepted_rows", -1),
        "known_unsafe_row_downgraded": summary.get("known_unsafe_row_downgraded", False),
        "authorization_state": {
            "acquisition_recall": "CERTIFIED",
            "matcher_precision_hardening": "COMPLETE" if passed else "REMEDIATION_REQUIRED",
            "current_supply_baseline": "AUTHORIZED_FOR_PROMOTION" if passed else "NOT_AUTHORIZED",
            "continuity_accumulation": "NOT_AUTHORIZED",
            "supply_scarcity_index_v1": "BLOCKED",
            "feature_certification": "BLOCKED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Promote the hardened 50-product acquisition into the true day-one supply baseline"
            if passed else "Inspect remaining unsafe accepts or unresolved replay rows"
        ),
        "status": (
            "PASS_COLLECTOR_EBAY_FULL_UNIVERSE_HARDENED_REPLAY_PROJECT_CONTROL"
            if passed
            else "FAIL_COLLECTOR_EBAY_FULL_UNIVERSE_HARDENED_REPLAY_PROJECT_CONTROL"
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    CONTROL.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(control, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
