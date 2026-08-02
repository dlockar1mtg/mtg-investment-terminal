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
LOTR_EXCLUDED_STANDARD = re.compile(r"\b(?:case|japanese|jpn|jp\s+version)\b", re.I)


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


def _clean(value: object) -> str:
    return str(value or "").strip()


def build_product_indexes(universe_rows: list[dict[str, str]]) -> tuple[
    dict[str, CanonicalProduct],
    dict[str, CanonicalProduct],
    dict[str, CanonicalProduct],
]:
    by_tcgplayer: dict[str, CanonicalProduct] = {}
    by_canonical_id: dict[str, CanonicalProduct] = {}
    by_name: dict[str, CanonicalProduct] = {}
    for row in universe_rows:
        product = product_from_row(row)
        if product.tcgplayer_product_id:
            by_tcgplayer[product.tcgplayer_product_id] = product
        if product.canonical_product_id:
            by_canonical_id[product.canonical_product_id] = product
        if product.canonical_product_name:
            by_name[product.canonical_product_name.casefold()] = product
    return by_tcgplayer, by_canonical_id, by_name


def resolve_product(
    listing: dict[str, str],
    by_tcgplayer: dict[str, CanonicalProduct],
    by_canonical_id: dict[str, CanonicalProduct],
    by_name: dict[str, CanonicalProduct],
) -> tuple[CanonicalProduct | None, str]:
    tcgplayer_id = _clean(listing.get("tcgplayer_product_id"))
    if tcgplayer_id and tcgplayer_id in by_tcgplayer:
        return by_tcgplayer[tcgplayer_id], "TCGPLAYER_PRODUCT_ID"

    canonical_id = _clean(listing.get("canonical_product_id"))
    if canonical_id and canonical_id in by_canonical_id:
        return by_canonical_id[canonical_id], "CANONICAL_PRODUCT_ID"

    canonical_name = _clean(listing.get("canonical_product_name"))
    if canonical_name and canonical_name.casefold() in by_name:
        return by_name[canonical_name.casefold()], "CANONICAL_PRODUCT_NAME"

    return None, "UNRESOLVED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    listings = read_csv(LISTINGS_PATH)
    universe_rows = read_csv(UNIVERSE_PATH)
    by_tcgplayer, by_canonical_id, by_name = build_product_indexes(universe_rows)
    observed = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, object]] = []
    unresolved_rows: list[dict[str, str]] = []
    resolution_methods: Counter[str] = Counter()

    for old in listings:
        product, resolution_method = resolve_product(old, by_tcgplayer, by_canonical_id, by_name)
        resolution_methods[resolution_method] += 1
        if product is None:
            unresolved_rows.append({
                "ebay_item_id": _clean(old.get("ebay_item_id")),
                "canonical_product_id": _clean(old.get("canonical_product_id")),
                "canonical_product_name": _clean(old.get("canonical_product_name")),
                "tcgplayer_product_id": _clean(old.get("tcgplayer_product_id")),
                "title": _clean(old.get("title")),
                "resolution_method": resolution_method,
            })
            continue

        item = {
            "itemId": old.get("ebay_item_id", ""),
            "title": old.get("title", ""),
            "price": {"value": old.get("price", ""), "currency": old.get("currency", "")},
            "condition": old.get("condition", ""),
        }
        new = identity_match_listing(product, item, "OFFLINE-HARDENED-REPLAY", observed)
        reasons = new.exclusion_reasons
        is_lotr_standard_candidate = (
            product.tcgplayer_product_id == LOTR_ID
            and old.get("match_state", "") == "REVIEW"
            and not LOTR_EXCLUDED_STANDARD.search(new.title)
        )
        rows.append({
            **asdict(new),
            "resolved_tcgplayer_product_id": product.tcgplayer_product_id,
            "product_resolution_method": resolution_method,
            "prior_match_state": old.get("match_state", ""),
            "classification_transition": f"{old.get('match_state', '')}->{new.match_state}",
            "year_parsed_as_quantity": bool(YEAR_QUANTITY.search(reasons)),
            "unsafe_title_accepted": bool(UNSAFE_TITLE.search(new.title)) and new.match_state == "ACCEPTED",
            "lotr_standard_candidate": is_lotr_standard_candidate,
            "lotr_standard_safe": is_lotr_standard_candidate and new.match_state in {"ACCEPTED", "REVIEW"},
            "lotr_standard_rejected": is_lotr_standard_candidate and new.match_state == "REJECTED",
            "lotr_standard_accepted": is_lotr_standard_candidate and new.match_state == "ACCEPTED",
        })

    transitions = Counter(row["classification_transition"] for row in rows)
    year_defects = sum(bool(row["year_parsed_as_quantity"]) for row in rows)
    unsafe_accepts = sum(bool(row["unsafe_title_accepted"]) for row in rows)
    lotr_standard_rows = sum(bool(row["lotr_standard_candidate"]) for row in rows)
    lotr_standard_safe_rows = sum(bool(row["lotr_standard_safe"]) for row in rows)
    lotr_standard_rejected_rows = sum(bool(row["lotr_standard_rejected"]) for row in rows)
    lotr_accepted_rows = sum(bool(row["lotr_standard_accepted"]) for row in rows)
    state_counts = Counter(row["match_state"] for row in rows)

    replay_complete = len(rows) == len(listings) == 601 and not unresolved_rows
    lotr_alias_gate_passed = (
        lotr_standard_rows >= 10
        and lotr_standard_safe_rows == lotr_standard_rows
        and lotr_standard_rejected_rows == 0
        and lotr_accepted_rows >= 5
    )
    summary = {
        "block_name": "Collector eBay Canary Hardened Matcher Replay",
        "block_version": "1.0.2",
        "generated_at": observed,
        "offline_only": True,
        "quota_calls": 0,
        "matcher_version": MATCHER_VERSION,
        "input_listing_rows": len(listings),
        "replayed_rows": len(rows),
        "unresolved_product_rows": len(unresolved_rows),
        "product_resolution_methods": dict(sorted(resolution_methods.items())),
        "state_counts": dict(sorted(state_counts.items())),
        "transition_counts": dict(sorted(transitions.items())),
        "year_as_quantity_defects": year_defects,
        "unsafe_accepted_rows": unsafe_accepts,
        "lotr_standard_candidate_rows": lotr_standard_rows,
        "lotr_standard_safe_rows": lotr_standard_safe_rows,
        "lotr_standard_rejected_rows": lotr_standard_rejected_rows,
        "lotr_accepted_rows": lotr_accepted_rows,
        "lotr_alias_gate_passed": lotr_alias_gate_passed,
        "replay_complete": replay_complete,
        "full_universe_collection_authorized": (
            replay_complete
            and year_defects == 0
            and unsafe_accepts == 0
            and lotr_alias_gate_passed
        ),
    }
    summary["status"] = (
        "PASS_CANARY_HARDENED_REPLAY_FULL_UNIVERSE_READY"
        if summary["full_universe_collection_authorized"]
        else "FAIL_CANARY_HARDENED_REPLAY_REMEDIATION_REQUIRED"
    )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT_ROOT / "collector_ebay_canary_hardened_replay.csv", rows)
    write_csv(OUTPUT_ROOT / "collector_ebay_canary_hardened_replay_unresolved_products.csv", unresolved_rows)
    (OUTPUT_ROOT / "collector_ebay_canary_hardened_replay_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (not args.strict or summary["full_universe_collection_authorized"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
