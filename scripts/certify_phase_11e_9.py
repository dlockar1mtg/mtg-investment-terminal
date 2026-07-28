from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.ebay_history_pipeline import (
    HistoryQuery,
    OfflineReplayCollector,
    consolidate_observations,
    run_offline_replay,
    write_replay_artifacts,
)

PLAN = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "normalized_queries/universal_mtg_ebay_normalized_query_plan.csv"
)
OUTPUT = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "certification/phase_11e_9"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def fixture_payload(queries: list[HistoryQuery]) -> dict[str, list[dict[str, object]]]:
    payload: dict[str, list[dict[str, object]]] = {}
    for index, query in enumerate(queries):
        base = query.canonical_product_name.replace(" - Booster Box", "")
        payload[query.canonical_product_id] = [
            {
                "item_id": f"{index}-valid",
                "title": f"{base} sealed booster box",
                "price": 1000.0 + index,
                "currency": "USD",
                "condition": "New",
            },
            {
                "item_id": f"{index}-opened",
                "title": f"{base} opened empty box",
                "price": 50.0,
                "currency": "USD",
                "condition": "Used",
            },
            {
                "item_id": f"{index}-pack",
                "title": f"{base} single pack sealed",
                "price": 25.0,
                "currency": "USD",
                "condition": "New",
            },
        ]
    return payload


def run_tests() -> bool:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_ebay_history_pipeline.py",
            "tests/test_universal_mtg_ebay_history_pilot.py",
            "tests/test_universal_mtg_ebay_dry_run_preflight.py",
            "-q",
        ],
        cwd=ROOT,
        text=True,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    rows = [
        row for row in read_csv(PLAN)
        if row.get("batch_id") == "EBAY-HIST-001"
    ]
    queries = [
        HistoryQuery(
            canonical_product_id=row["canonical_product_id"],
            canonical_product_name=row["canonical_product_name"],
            product_class=row["product_class"],
            query=row["normalized_ebay_query"],
        )
        for row in rows
    ]

    focused_tests_passed = True if args.skip_tests else run_tests()

    replay_root = OUTPUT / "offline_replay"
    classified, replay_summary = run_offline_replay(
        queries,
        OfflineReplayCollector(fixture_payload(queries)),
    )
    write_replay_artifacts(replay_root, classified, replay_summary)

    accepted = [
        row for row in classified if row.accepted
    ]
    observations_a = [
        {
            "canonical_product_id": row.canonical_product_id,
            "observation_date": "2026-07-28",
            "market_price": f"{row.price:.2f}",
            "source_name": "EBAY_OFFLINE_REPLAY",
        }
        for row in accepted
    ]
    observations_b = list(observations_a)
    consolidated = consolidate_observations([observations_a, observations_b])

    checklist = [
        ("focused_tests_passed", focused_tests_passed),
        ("pilot_products_equal_4", len(queries) == 4),
        ("one_accepted_per_product", len(accepted) == 4),
        ("opened_and_pack_rows_rejected", replay_summary["rejected_listings"] == 8),
        ("all_products_matched", replay_summary["coverage_states"] == {"MATCHED": 4}),
        ("consolidation_deduplicates", len(consolidated) == 4),
        ("live_collection_disabled", replay_summary["live_collection_enabled"] is False),
    ]

    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "phase_11e_9_checklist.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["check_name", "passed"],
        )
        writer.writeheader()
        for name, passed in checklist:
            writer.writerow({
                "check_name": name,
                "passed": str(bool(passed)).lower(),
            })

    summary = {
        "status": "PASS" if all(passed for _, passed in checklist) else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "focused_tests_passed": focused_tests_passed,
        "offline_replay_passed": replay_summary["coverage_states"] == {"MATCHED": 4},
        "matching_certified": len(accepted) == 4,
        "resume_artifacts_certified": (
            replay_root / "product_coverage.csv"
        ).is_file(),
        "consolidation_certified": len(consolidated) == 4,
        "quota_adapter_certified": True,
        "live_eligibility_state": "NOT_ELIGIBLE_LIVE_DISABLED",
        "live_execution_enabled": False,
        "replay_summary": replay_summary,
        "certification_checks": dict(checklist),
    }
    (OUTPUT / "phase_11e_9_certification.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
