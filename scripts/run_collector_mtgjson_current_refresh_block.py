"""Fetch, verify, vault, and certify the current MTGJSON sealed-product crosswalk."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_mtgjson_current_refresh"


def run(command: list[str]) -> dict:
    result = subprocess.run(command, cwd=ROOT)
    return {"command": command, "return_code": result.returncode, "passed": result.returncode == 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    python = sys.executable

    steps = [
        run([python, "scripts/fetch_current_mtgjson_allprintings.py", "--strict"]),
        run([python, "scripts/build_collector_mtgjson_current_crosswalk.py"] + (["--strict"] if args.strict else [])),
    ]

    source_path = ROOT / "data/governance/permanence/certification/collector_mtgjson_current_source/collector_mtgjson_current_source_summary.json"
    crosswalk_path = ROOT / "data/governance/permanence/certification/collector_mtgjson_sealed_crosswalk/collector_mtgjson_sealed_crosswalk_summary.json"
    source = json.loads(source_path.read_text(encoding="utf-8")) if source_path.is_file() else {}
    crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8")) if crosswalk_path.is_file() else {}

    passed = all(step["passed"] for step in steps)
    complete = bool(crosswalk.get("crosswalk_complete_for_released_products", False))
    summary = {
        "block_name": "Collector Current MTGJSON Refresh Block",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "all_steps_passed": passed,
        "source_sha256_verified": bool(source.get("sha256_verified", False)),
        "source_retrieval_id": source.get("retrieval_id", ""),
        "exact_tcgplayer_id_verified": crosswalk.get("exact_tcgplayer_id_verified", 0),
        "exact_name_structurally_verified": crosswalk.get("exact_name_structurally_verified", 0),
        "presale_not_present": crosswalk.get("presale_not_present", 0),
        "released_product_blockers": crosswalk.get("released_product_blockers", ""),
        "review_required": crosswalk.get("review_required", ""),
        "crosswalk_complete_for_released_products": complete,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_CURRENT_MTGJSON_REFRESH" if passed and complete else "REVIEW_REQUIRED",
    }
    (OUT / "collector_mtgjson_current_refresh_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and summary["status"] != "PASS_CURRENT_MTGJSON_REFRESH" else 0


if __name__ == "__main__":
    raise SystemExit(main())
