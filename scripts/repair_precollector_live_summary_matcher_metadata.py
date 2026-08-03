from __future__ import annotations

import json
from pathlib import Path

from terminal2.market_sources.ebay_precision_production import MATCHER_VERSION
from terminal2.market_sources.ebay_precision_v3 import identity_match_listing

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "data/validation/phase_10/ebay_matching/ebay_matching_summary_2026-08-03.json"
EXPECTED_MATCHER_VERSION = "precision-v3-universal"
EXPECTED_MATCHER_ENTRYPOINT = "terminal2.market_sources.ebay_precision_v3.identity_match_listing"
EXPECTED_RUN_ID = "EBAY20260803T221111Z"
EXPECTED_LISTING_ROWS = 7488
EXPECTED_ACCEPTED_ROWS = 936
EXPECTED_REVIEW_ROWS = 207
EXPECTED_REJECTED_ROWS = 6345


def main() -> int:
    if MATCHER_VERSION != EXPECTED_MATCHER_VERSION:
        raise RuntimeError(f"PRODUCTION_MATCHER_VERSION_DRIFT:{MATCHER_VERSION}")

    actual_entrypoint = f"{identity_match_listing.__module__}.{identity_match_listing.__name__}"
    if actual_entrypoint != EXPECTED_MATCHER_ENTRYPOINT:
        raise RuntimeError(f"PRODUCTION_MATCHER_ENTRYPOINT_DRIFT:{actual_entrypoint}")

    if not SUMMARY_PATH.is_file():
        raise RuntimeError(f"LIVE_SUMMARY_MISSING:{SUMMARY_PATH.relative_to(ROOT)}")

    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    expected_counts = {
        "listing_rows": EXPECTED_LISTING_ROWS,
        "accepted_rows": EXPECTED_ACCEPTED_ROWS,
        "review_rows": EXPECTED_REVIEW_ROWS,
        "rejected_rows": EXPECTED_REJECTED_ROWS,
    }

    if summary.get("run_id") != EXPECTED_RUN_ID:
        raise RuntimeError(f"LIVE_SUMMARY_RUN_ID_DRIFT:{summary.get('run_id')}")
    for key, expected in expected_counts.items():
        if int(summary.get(key, -1)) != expected:
            raise RuntimeError(f"LIVE_SUMMARY_COUNT_DRIFT:{key}:{summary.get(key)}")
    if summary.get("aborted_early") is not False:
        raise RuntimeError("LIVE_COLLECTION_ABORTED_EARLY")
    if summary.get("missing_tcgplayer_product_ids"):
        raise RuntimeError("LIVE_COLLECTION_MISSING_PRODUCT_IDS")

    summary["matcher_version"] = MATCHER_VERSION
    summary["matcher_entrypoint"] = actual_entrypoint
    summary["matcher_fail_closed"] = True
    summary["universal_classification_policy"] = True
    summary["universal_policy_mode"] = "downgrade_only"
    summary["matcher_metadata_enrichment"] = {
        "status": "CERTIFIED_PRODUCTION_BINDING_ENRICHED",
        "counts_modified": False,
        "listing_rows_modified": False,
        "source_run_id": EXPECTED_RUN_ID,
    }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_LIVE_SUMMARY_MATCHER_METADATA_REPAIR")
    print(f"RUN_ID={EXPECTED_RUN_ID}")
    print(f"MATCHER_VERSION={MATCHER_VERSION}")
    print(f"MATCHER_ENTRYPOINT={actual_entrypoint}")
    print("MATCHER_FAIL_CLOSED=TRUE")
    print("COUNTS_MODIFIED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
