from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_precision_v3 import MATCHER_VERSION, identity_match_listing

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_acquisition"
LISTINGS = SOURCE / "collector_ebay_full_universe_deduplicated_listing_results.csv"
UNIVERSE = SOURCE / "collector_ebay_full_universe_match_universe.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_hardened_replay"
KNOWN_UNSAFE_ITEM = "v1|198519464141|0"
UNSAFE_ACCEPT = re.compile(
    r"(?:\bcase\b|\b(?:japanese|jpn)\b|\b\d+\s*[x×]\s*(?:magic\s+the\s+gathering\s+|magic\s+|mtg\s+)?(?:collector\s+)?booster\s+(?:box|boxes|display|displays)\b|\b(?:collector\s+)?booster\s+(?:box|boxes|display|displays)\b.*\b[x×]\s*\d+\b)",
    re.I,
)


def pick(frame: pd.DataFrame, *names: str) -> str:
    for name in names:
        if name in frame.columns:
            return name
    raise RuntimeError(f"Missing required columns; expected one of {names}")


def clean(value: object) -> str:
    return str(value or "").strip()


def product_from_row(row: pd.Series) -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id=clean(row.get("canonical_product_id")),
        canonical_product_name=clean(row.get("canonical_product_name")),
        canonical_set_name=clean(row.get("canonical_set_name")),
        product_class=clean(row.get("product_class")) or "COLLECTOR_BOOSTER_BOX",
        tcgplayer_product_id=clean(row.get("tcgplayer_product_id")),
        release_date=clean(row.get("release_date")),
        ebay_query=clean(row.get("ebay_query")),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    generated = datetime.now(timezone.utc).isoformat()

    missing = [str(path) for path in (LISTINGS, UNIVERSE) if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing full-universe replay inputs: {missing}")

    listings = pd.read_csv(LISTINGS, dtype=str, encoding="utf-8-sig").fillna("")
    universe = pd.read_csv(UNIVERSE, dtype=str, encoding="utf-8-sig").fillna("")
    canonical_id_col = pick(listings, "canonical_product_id")
    item_id_col = pick(listings, "ebay_item_id", "item_id")
    title_col = pick(listings, "title")

    products = {
        clean(row.get("canonical_product_id")): product_from_row(row)
        for _, row in universe.iterrows()
        if clean(row.get("canonical_product_id"))
    }
    unresolved: list[dict[str, str]] = []
    rows: list[dict[str, object]] = []

    for _, old in listings.iterrows():
        canonical_id = clean(old.get(canonical_id_col))
        product = products.get(canonical_id)
        if product is None:
            unresolved.append({
                "canonical_product_id": canonical_id,
                "ebay_item_id": clean(old.get(item_id_col)),
                "title": clean(old.get(title_col)),
            })
            continue
        item = {
            "itemId": clean(old.get(item_id_col)),
            "title": clean(old.get(title_col)),
            "price": {"value": clean(old.get("price")), "currency": clean(old.get("currency"))},
            "condition": clean(old.get("condition")),
        }
        new = identity_match_listing(product, item, "FULL-UNIVERSE-HARDENED-REPLAY", generated)
        unsafe = bool(UNSAFE_ACCEPT.search(new.title)) and new.match_state == "ACCEPTED"
        rows.append({
            **asdict(new),
            "prior_match_state": clean(old.get("match_state")),
            "classification_transition": f"{clean(old.get('match_state'))}->{new.match_state}",
            "unsafe_title_accepted": unsafe,
            "known_unsafe_spaced_multiplier_row": clean(old.get(item_id_col)) == KNOWN_UNSAFE_ITEM,
        })

    replay = pd.DataFrame(rows)
    unresolved_frame = pd.DataFrame(unresolved, columns=["canonical_product_id", "ebay_item_id", "title"])
    OUT.mkdir(parents=True, exist_ok=True)
    replay.to_csv(OUT / "collector_ebay_full_universe_hardened_replay.csv", index=False)
    unresolved_frame.to_csv(OUT / "collector_ebay_full_universe_hardened_replay_unresolved.csv", index=False)

    transitions = Counter(replay["classification_transition"].astype(str)) if not replay.empty else Counter()
    unsafe_accepts = int(replay["unsafe_title_accepted"].astype(bool).sum()) if not replay.empty else 0
    known_rows = replay[replay["known_unsafe_spaced_multiplier_row"].astype(bool)] if not replay.empty else replay
    known_row_downgraded = (
        len(known_rows) == 1
        and known_rows.iloc[0]["prior_match_state"] == "ACCEPTED"
        and known_rows.iloc[0]["match_state"] == "REJECTED"
    )
    replay_complete = len(replay) == len(listings) == 4413 and not unresolved
    baseline_authorized = replay_complete and unsafe_accepts == 0 and known_row_downgraded
    summary = {
        "block_name": "Collector eBay Full-Universe Hardened Matcher Replay",
        "block_version": "1.0.0",
        "generated_at": generated,
        "offline_only": True,
        "quota_calls": 0,
        "matcher_version": MATCHER_VERSION,
        "input_listing_rows": len(listings),
        "replayed_rows": len(replay),
        "unresolved_product_rows": len(unresolved),
        "state_counts": dict(sorted(Counter(replay["match_state"].astype(str)).items())) if not replay.empty else {},
        "transition_counts": dict(sorted(transitions.items())),
        "unsafe_accepted_rows": unsafe_accepts,
        "known_unsafe_item_id": KNOWN_UNSAFE_ITEM,
        "known_unsafe_row_downgraded": known_row_downgraded,
        "replay_complete": replay_complete,
        "acquisition_recall_remains_certified": True,
        "supply_baseline_authorized": baseline_authorized,
        "continuity_accumulation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": (
            "PASS_FULL_UNIVERSE_HARDENED_REPLAY_BASELINE_READY"
            if baseline_authorized
            else "FAIL_FULL_UNIVERSE_HARDENED_REPLAY_REMEDIATION_REQUIRED"
        ),
    }
    (OUT / "collector_ebay_full_universe_hardened_replay_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if baseline_authorized else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
