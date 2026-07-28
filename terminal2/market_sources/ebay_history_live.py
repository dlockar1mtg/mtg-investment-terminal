from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from terminal2.market_sources.ebay_history_pipeline import (
    ClassifiedListing,
    HistoryQuery,
    ReplayListing,
    classify_listing,
)
from terminal2.market_sources.ebay_matching import EbayBrowseClient
from terminal2.market_sources.ebay_resilience import BrowseQuota, get_browse_quota


@dataclass(frozen=True)
class LiveProductResult:
    canonical_product_id: str
    canonical_product_name: str
    query: str
    queries_used: int
    results_found: int
    accepted_listing_count: int
    rejected_listing_count: int
    coverage_state: str
    source_error: str


def credentials_present() -> bool:
    try:
        EbayBrowseClient()
    except RuntimeError:
        return False
    return True


def inspect_quota() -> BrowseQuota:
    return get_browse_quota(EbayBrowseClient())


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def browse_item_to_replay(item: Mapping[str, Any]) -> ReplayListing:
    price = item.get("price") if isinstance(item.get("price"), Mapping) else {}
    return ReplayListing(
        item_id=str(item.get("itemId", "")).strip()
        or hashlib.sha256(str(item.get("title", "")).encode("utf-8")).hexdigest()[:20],
        title=str(item.get("title", "")).strip(),
        price=_float(price.get("value")),
        currency=str(price.get("currency", "")).strip(),
        condition=str(item.get("condition", "")).strip(),
        source_state="OK",
    )


def build_live_query(query: HistoryQuery) -> str:
    return build_live_query_ladder(query)[0]


def build_live_query_ladder(query: HistoryQuery) -> list[str]:
    if query.product_class not in {
        "PRE_COLLECTOR_BOOSTER_BOX",
        "COLLECTOR_BOOSTER_BOX",
    }:
        return [query.query]

    name = query.canonical_product_name.replace(" - Booster Box", "").strip()
    candidates = [
        f'Magic The Gathering "{name}" booster box',
        f'MTG "{name}" booster box',
        f'Magic "{name}" sealed box',
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = " ".join(candidate.split())
        key = normalized.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique


class LiveBrowseHistoryCollector:
    mode = "LIVE_BROWSE"

    def __init__(self, client: EbayBrowseClient | None = None, limit: int = 20):
        self.client = client or EbayBrowseClient()
        self.limit = max(1, min(int(limit), 200))

    def collect(self, query: HistoryQuery) -> Sequence[ReplayListing]:
        collected: dict[str, ReplayListing] = {}
        for live_query in build_live_query_ladder(query):
            if len(collected) >= self.limit:
                break
            remaining = max(1, self.limit - len(collected))
            for item in self.client.search(live_query, remaining):
                replay = browse_item_to_replay(item)
                collected.setdefault(replay.item_id, replay)
                if len(collected) >= self.limit:
                    break
        return list(collected.values())[: self.limit]


def collect_live_product(
    query: HistoryQuery,
    collector: LiveBrowseHistoryCollector,
) -> tuple[list[ClassifiedListing], LiveProductResult]:
    try:
        listings = list(collector.collect(query))
        classified = [classify_listing(query, listing) for listing in listings]
        accepted = sum(row.accepted for row in classified)
        coverage_state = (
            "MATCHED"
            if accepted
            else "NO_ACCEPTED_LISTINGS"
            if classified
            else "NO_RESULTS"
        )
        error = ""
    except Exception as exc:
        classified = []
        accepted = 0
        coverage_state = "SOURCE_ERROR"
        error = f"{type(exc).__name__}: {exc}"

    result = LiveProductResult(
        canonical_product_id=query.canonical_product_id,
        canonical_product_name=query.canonical_product_name,
        query=build_live_query(query),
        queries_used=1,
        results_found=len(classified),
        accepted_listing_count=accepted,
        rejected_listing_count=len(classified) - accepted,
        coverage_state=coverage_state,
        source_error=error,
    )
    return classified, result


def serialize_product_result(result: LiveProductResult) -> dict[str, Any]:
    return asdict(result)
