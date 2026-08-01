from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/governance/permanence/certification/permanence_preservation_block_summary.json"


def run(script: str, strict: bool) -> dict[str, object]:
    command = [sys.executable, str(ROOT / "scripts" / script)]
    if strict:
        command.append("--strict")
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return {
        "script": script,
        "command": command,
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    steps = [
        "run_mtg_data_permanence_foundation_block.py",
        "run_mtg_preservation_migration.py",
        "audit_mtg_preservation_migration.py",
    ]
    results: list[dict[str, object]] = []
    for script in steps:
        result = run(script, args.strict)
        results.append(result)
        print(result["stdout"], end="")
        if result["stderr"]:
            print(result["stderr"], file=sys.stderr, end="")
        if result["return_code"] != 0:
            break

    failures = [result["script"] for result in results if result["return_code"] != 0]
    summary = {
        "program_name": "MTG Permanence Preservation Block",
        "program_version": "1.0.0",
        "covered_phases": [0, 1, 2, 3],
        "steps_requested": steps,
        "steps_completed": [result["script"] for result in results],
        "step_results": results,
        "source_files_deleted": 0,
        "source_files_moved": 0,
        "source_files_overwritten": 0,
        "forecasting_resume_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "status": "PASS" if not failures and len(results) == len(steps) else "FAIL",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "step_results"}, indent=2, sort_keys=True))
    return 1 if args.strict and summary["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
