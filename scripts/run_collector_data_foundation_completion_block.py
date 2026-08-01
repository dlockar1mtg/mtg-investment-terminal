"""Run the consolidated Collector data-foundation completion block."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_data_foundation_completion"
MTGJSON_SUMMARY = ROOT / "data/governance/permanence/certification/collector_mtgjson_sealed_crosswalk/collector_mtgjson_sealed_crosswalk_summary.json"
SOURCE_SUMMARY = ROOT / "data/governance/permanence/certification/collector_source_completeness/collector_source_completeness_summary.json"


def run(command: list[str]) -> dict[str, object]:
    process = subprocess.run(command, cwd=ROOT)
    return {"command": command, "return_code": process.returncode, "passed": process.returncode == 0}


def read_summary(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    python = sys.executable
    steps = [
        run([python, "scripts/run_collector_official_release_date_completion_block.py", "--strict"]),
        run([python, "scripts/build_collector_mtgjson_sealed_crosswalk.py"] + (["--strict"] if args.strict else [])),
        run([python, "scripts/build_collector_ebay_search_contracts.py", "--strict"]),
        run([python, "scripts/audit_collector_source_completeness.py"] + (["--strict"] if args.strict else [])),
    ]

    source_summary = read_summary(SOURCE_SUMMARY)
    mtgjson_summary = read_summary(MTGJSON_SUMMARY)
    mtgjson_complete = bool(mtgjson_summary.get("crosswalk_complete", False))
    mtgjson_review_required = int(mtgjson_summary.get("review_required", 0) or 0)
    mtgjson_source_errors = int(mtgjson_summary.get("source_errors", 0) or 0)

    all_steps_passed = all(step["passed"] for step in steps)
    source_audit_passed = bool(source_summary.get("source_layer_certified", False))
    fully_certified = all_steps_passed and source_audit_passed and mtgjson_complete and mtgjson_review_required == 0 and mtgjson_source_errors == 0

    result = {
        "block_name": "Collector Data Foundation Completion Block",
        "block_version": "1.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "all_steps_passed": all_steps_passed,
        "source_audit_passed": source_audit_passed,
        "mtgjson_crosswalk_complete": mtgjson_complete,
        "mtgjson_exact_id_matches": mtgjson_summary.get("exact_id_matches", ""),
        "mtgjson_review_required": mtgjson_review_required,
        "mtgjson_source_errors": mtgjson_source_errors,
        "source_layer_certified": fully_certified,
        "source_layer_blockers": (
            int(source_summary.get("source_layer_blockers", 0) or 0)
            + mtgjson_review_required
            + mtgjson_source_errors
            + (0 if mtgjson_complete else 1)
        ),
        "ebay_contracts_ready": steps[2]["passed"],
        "ebay_live_collection_executed": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_DATA_FOUNDATION_SOURCE_LAYER" if fully_certified else "REVIEW_REQUIRED",
    }

    (OUT / "collector_data_foundation_completion_summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 1 if args.strict and not fully_certified else 0


if __name__ == "__main__":
    raise SystemExit(main())
