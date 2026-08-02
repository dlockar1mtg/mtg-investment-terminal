from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_precision_v3 import MATCHER_VERSION, identity_match_listing

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "data/governance/permanence/certification/collector_ebay_valid_high_recall_canary"
OUTPUT_ROOT = ROOT / "data/governance/permanence/certification/collector_ebay_canary_hardened_replay"
LISTINGS_PATH = SOURCE_ROOT / "collector_ebay_canary_listing_results.csv"
UNIVERSE_PATH = SOURCE_ROOT / "collector_ebay_canary_universe.csv"
LOTR_ID = "484912"
YEAR_QUANTITY = re.compile(r"universal_quantity:(?:19|20)\d{2}(?:\||$)")
UNSAFE_TITLE = re.compile(r"(?:\bcase\b|\bmaster case\b|\b[x×]\s*[2-9]\b|\b[2-9]\s*[x×]\b|\b[2-9]\s+(?:boxes|displays)\b)", re.I)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def product_from_row(row: dict[str, str]) -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id=row.get("canonical_product_id", ""),
        canonical_product_name=row.get("canonical_product_name", ""),
        canonical_set_name=row.get("canonical_set_name", ""),
        product_class=row.get("product_class", "COLLECTOR_BOOSTER_BOX"),
        tcgplayer_product_id=row.get("tcgplayer_product_id", ""),
        release_date=row.get("release_date", ""),
        ebay_query=row.get("ebay_query", ""),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    listings = read_csv(LISTINGS_PATH)
    products = {row["tcgplayer_product_id"]: product_from_row(row) for row in read_csv(UNIVERSE_PATH)}
    observed = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, object]] = []

    for old in listings:
        product = products[old["tcgplayer_product_id"]]
        item = {
            "itemId": old.get("ebay_item_id", ""),
            "title": old.get("title", ""),
            "price": {"value": old.get("price", ""), "currency": old.get("currency", "")},
            "condition": old.get("condition", ""),
        }
        new = identity_match_listing(product, item, "OFFLINE-HARDENED-REPLAY", observed)
        reasons = new.exclusion_reasons
        rows.append({
            **asdict(new),
            "prior_match_state": old.get("match_state", ""),
            "classification_transition": f"{old.get('match_state', '')}->{new.match_state}",
            "year_parsed_as_quantity": bool(YEAR_QUANTITY.search(reasons)),
            "unsafe_title_accepted": bool(UNSAFE_TITLE.search(new.title)) and new.match_state == "ACCEPTED",
            "lotr_standard_display_accepted": product.tcgplayer_product_id == LOTR_ID and new.match_state == "ACCEPTED",
        })

    transitions = Counter(row["classification_transition"] for row in rows)
    year_defects = sum(bool(row["year_parsed_as_quantity"]) for row in rows)
    unsafe_accepts = sum(bool(row["unsafe_title_accepted"]) for row in rows)
    lotr_accepts = sum(bool(row["lotr_standard_display_accepted"]) for row in rows)
    state_counts = Counter(row["match_state"] for row in rows)

    summary = {
        "block_name": "Collector eBay Canary Hardened Matcher Replay",
        "block_version": "1.0.0",
        "generated_at": observed,
        "offline_only": True,
        "quota_calls": 0,
        "matcher_version": MATCHER_VERSION,
        "replayed_rows": len(rows),
        "state_counts": dict(sorted(state_counts.items())),
        "transition_counts": dict(sorted(transitions.items())),
        "year_as_quantity_defects": year_defects,
        "unsafe_accepted_rows": unsafe_accepts,
        "lotr_accepted_rows": lotr_accepts,
        "full_universe_collection_authorized": len(rows) == 601 and year_defects == 0 and unsafe_accepts == 0 and lotr_accepts >= 10,
    }
    summary["status"] = (
        "PASS_CANARY_HARDENED_REPLAY_FULL_UNIVERSE_READY"
        if summary["full_universe_collection_authorized"]
        else "FAIL_CANARY_HARDENED_REPLAY_REMEDIATION_REQUIRED"
    )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT_ROOT / "collector_ebay_canary_hardened_replay.csv", rows)
    (OUTPUT_ROOT / "collector_ebay_canary_hardened_replay_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (not args.strict or summary["full_universe_collection_authorized"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
