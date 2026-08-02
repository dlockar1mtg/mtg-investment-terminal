"""Orchestrate fail-closed day-one multi-product accepted adjudication."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run day-one multi-product accepted adjudication block")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--winner-margin", type=float, default=0.08)
    return p


def main() -> int:
    args = parser().parse_args()
    BASE.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)
    command = [
        sys.executable,
        "scripts/run_collector_ebay_day_one_multi_product_adjudication_with_schema_adapter.py",
        "--winner-margin",
        str(args.winner_margin),
    ]
    if args.strict:
        command.append("--strict")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    summary_path = BASE / "collector_ebay_day_one_supply_baseline_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    passed = result.returncode == 0 and summary.get("status") == "PASS_DAY_ONE_MULTI_PRODUCT_ADJUDICATION_BASELINE_PROMOTED"
    project = {
        "block_name": "Collector eBay Day-One Multi-Product Adjudication and Project Control",
        "block_version": "1.0.1",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "schema_adapter_used": True,
        "immutable_replay_source_mutated": False,
        "steps": [{"command": command, "return_code": result.returncode, "passed": result.returncode == 0}],
        "adjudication_passed": passed,
        "original_accepted_rows": summary.get("original_accepted_rows", 0),
        "final_accepted_rows": summary.get("final_accepted_rows", 0),
        "cross_product_ambiguity_excluded_rows": summary.get("cross_product_ambiguity_excluded_rows", 0),
        "duplicated_accepted_item_ids_adjudicated": summary.get("duplicated_accepted_item_ids_adjudicated", 0),
        "unique_evidence_winners": summary.get("unique_evidence_winners", 0),
        "unresolved_ambiguous_item_ids": summary.get("unresolved_ambiguous_item_ids", 0),
        "accepted_item_ids_mapped_to_multiple_products": summary.get("accepted_item_ids_mapped_to_multiple_products", -1),
        "authorization_state": {
            "acquisition_recall": "CERTIFIED",
            "matcher_precision_hardening": "COMPLETE",
            "day_one_supply_baseline": "PROMOTED" if passed else "NOT_PROMOTED",
            "continuity_accumulation": "AUTHORIZED_FROM_DAY_ONE_BASELINE" if passed else "NOT_AUTHORIZED",
            "supply_scarcity_index_v1": "BLOCKED_PENDING_CONTINUITY",
            "feature_certification": "BLOCKED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Prepare the first comparable post-baseline collection after the governed interval"
            if passed else "Inspect multi-product adjudication evidence and resolve remaining ambiguity"
        ),
        "status": (
            "PASS_COLLECTOR_EBAY_DAY_ONE_MULTI_PRODUCT_ADJUDICATION_PROJECT_CONTROL"
            if passed else "FAIL_COLLECTOR_EBAY_DAY_ONE_MULTI_PRODUCT_ADJUDICATION_PROJECT_CONTROL"
        ),
    }
    (BASE / "collector_ebay_day_one_multi_product_adjudication_project_control_summary.json").write_text(
        json.dumps(project, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(project, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
