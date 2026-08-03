from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    [sys.executable, str(ROOT / "scripts/initialize_mtg_data_permanence_foundation.py"), "--strict"],
    [sys.executable, str(ROOT / "scripts/build_mtg_permanent_file_inventory.py"), "--strict"],
]


def run_step(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MTG data permanence Foundation Block for Phases 0-3.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    results: list[dict[str, object]] = []
    failures: list[str] = []
    for command in STEPS:
        result = run_step(command)
        results.append(result)
        if result["status"] != "PASS":
            failures.append(Path(command[1]).name)
            break

    summary = {
        "program": "MTG Data Permanence Foundation Block",
        "version": "1.0.0",
        "phases": [0, 1, 2, 3],
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "step_count": len(results),
        "passed_step_count": sum(1 for item in results if item["status"] == "PASS"),
        "failure_count": len(failures),
        "failures": failures,
        "forecasting_resume_authorized": False,
        "destructive_operation_authorized": False,
        "status": "PASS" if not failures else "FAIL",
        "steps": results,
    }
    output = ROOT / "data/governance/permanence/certification/foundation_block_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "steps"}, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
