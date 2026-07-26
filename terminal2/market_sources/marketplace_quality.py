from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

CERTIFIED_FIELDS = (
    "observed_at_utc", "source_name", "product_name", "tcgplayer_product_id",
    "market_price", "low_price", "median_price", "listing_count", "seller_count",
    "confidence", "source_status", "source_run_id", "certified_price",
    "quality_state", "eligible_for_decisioning", "quality_reason_codes",
)


def _number(value: object) -> float | None:
    try:
        text = str(value or "").replace("$", "").replace(",", "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def certify_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_markets: dict[str, dict[str, float]] = defaultdict(dict)
    materialized = [dict(row) for row in rows]
    for row in materialized:
        product_id = str(row.get("tcgplayer_product_id") or "").strip()
        source = str(row.get("source_name") or "").upper()
        market = _number(row.get("market_price"))
        if product_id and source and market and market > 0:
            source_markets[product_id][source] = market

    certified: list[dict[str, Any]] = []
    state_counts: dict[str, int] = defaultdict(int)
    reason_counts: dict[str, int] = defaultdict(int)

    for original in materialized:
        row = dict(original)
        source = str(row.get("source_name") or "").upper()
        product_id = str(row.get("tcgplayer_product_id") or "").strip()
        market = _number(row.get("market_price"))
        low = _number(row.get("low_price"))
        median = _number(row.get("median_price"))
        listings = int(_number(row.get("listing_count")) or 0)
        sellers = int(_number(row.get("seller_count")) or 0)
        confidence = _number(row.get("confidence")) or 0.0
        reasons: list[str] = []

        # TCGCSV's market price is the source's current transaction-oriented
        # valuation and is preferred over its higher retail midpoint. eBay uses
        # the median accepted landed listing price as its governed observation.
        if source == "TCGCSV":
            certified_price = market or median
        else:
            certified_price = median or market
        eligible = bool(certified_price and certified_price > 0)

        if not eligible:
            reasons.append("PRICE_NOT_AVAILABLE")

        if source == "EBAY":
            if listings < 3:
                reasons.append("EBAY_INSUFFICIENT_ACCEPTED_LISTINGS")
            if sellers < 2:
                reasons.append("EBAY_INSUFFICIENT_SELLER_DIVERSITY")
            if confidence < 70:
                reasons.append("EBAY_CONFIDENCE_BELOW_THRESHOLD")
            if low and median and low / median < 0.35:
                reasons.append("EBAY_LOW_PRICE_OUTLIER_QUARANTINED")
                row["low_price"] = ""
            peer = source_markets.get(product_id, {}).get("TCGCSV")
            if peer and certified_price and max(peer, certified_price) / min(peer, certified_price) > 1.5:
                reasons.append("CROSS_SOURCE_PRICE_DIVERGENCE")

        elif source == "TCGCSV":
            if confidence < 60:
                reasons.append("TCGCSV_QUALITY_BELOW_THRESHOLD")
        else:
            reasons.append("UNRECOGNIZED_MARKETPLACE_SOURCE")

        blocking = {
            "PRICE_NOT_AVAILABLE",
            "EBAY_INSUFFICIENT_ACCEPTED_LISTINGS",
            "EBAY_INSUFFICIENT_SELLER_DIVERSITY",
            "EBAY_CONFIDENCE_BELOW_THRESHOLD",
            "CROSS_SOURCE_PRICE_DIVERGENCE",
            "TCGCSV_QUALITY_BELOW_THRESHOLD",
            "UNRECOGNIZED_MARKETPLACE_SOURCE",
        }
        eligible = eligible and not any(reason in blocking for reason in reasons)
        quality_state = "CERTIFIED" if eligible and not reasons else "CERTIFIED_WITH_WARNING" if eligible else "QUARANTINED"

        row["certified_price"] = round(float(certified_price), 2) if certified_price else ""
        row["quality_state"] = quality_state
        row["eligible_for_decisioning"] = str(eligible).lower()
        row["quality_reason_codes"] = "|".join(reasons) if reasons else "MARKETPLACE_OBSERVATION_CERTIFIED"
        certified.append(row)
        state_counts[quality_state] += 1
        for reason in reasons or ["MARKETPLACE_OBSERVATION_CERTIFIED"]:
            reason_counts[reason] += 1

    summary = {
        "status": "PASS" if any(row["eligible_for_decisioning"] == "true" for row in certified) else "INCOMPLETE",
        "observation_count": len(certified),
        "eligible_observation_count": sum(row["eligible_for_decisioning"] == "true" for row in certified),
        "quarantined_observation_count": sum(row["quality_state"] == "QUARANTINED" for row in certified),
        "warning_observation_count": sum(row["quality_state"] == "CERTIFIED_WITH_WARNING" for row in certified),
        "quality_state_counts": dict(sorted(state_counts.items())),
        "reason_code_counts": dict(sorted(reason_counts.items())),
    }
    return certified, summary


def certify_file(input_path: Path, output_path: Path) -> dict[str, Any]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    certified, summary = certify_rows(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CERTIFIED_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(certified)
    summary["input_path"] = str(input_path.resolve())
    summary["output_path"] = str(output_path.resolve())
    return summary
