"""Run strict source inventory followed by Collector historical candidate construction."""
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_historical_candidate_panel"


def main() -> int:
    p = argparse.ArgumentParser(description="Run Collector historical candidate panel block")
    p.add_argument("--strict", action="store_true")
    a = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    commands = [
        [sys.executable, "scripts/run_collector_historical_source_inventory_block.py", "--strict"],
        [sys.executable, "scripts/build_collector_historical_candidate_panel.py"] + (["--strict"] if a.strict else []),
    ]
    steps = []
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT)
        steps.append({"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0})
        if completed.returncode != 0:
            break
    all_passed = len(steps) == len(commands) and all(step["passed"] for step in steps)
    summary = {
        "block_name": "Collector Historical Candidate Panel Block",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "all_steps_passed": all_passed,
        "historical_append_executed": False,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS_HISTORICAL_CANDIDATE_PANEL_ONLY" if all_passed else "REVIEW_REQUIRED",
    }
    (OUT / "collector_historical_candidate_panel_block_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
