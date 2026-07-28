from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence


@dataclass(frozen=True)
class HistoryQuery:
    canonical_product_id: str
    canonical_product_name: str
    product_class: str
    query: str


@dataclass(frozen=True)
class ReplayListing:
    item_id: str
    title: str
    price: float
    currency: str
    condition: str
    source_state: str = "OK"


@dataclass(frozen=True)
class ClassifiedListing:
    canonical_product_id: str
    item_id: str
    title: str
    price: float
    currency: str
    accepted: bool
    classification: str
    rejection_reason: str


class HistoryCollector(Protocol):
    mode: str

    def collect(self, query: HistoryQuery) -> Sequence[ReplayListing]:
        ...


class OfflineReplayCollector:
    mode = "OFFLINE_REPLAY"

    def __init__(self, fixture_payload: dict[str, list[dict[str, Any]]]):
        self.fixture_payload = fixture_payload

    def collect(self, query: HistoryQuery) -> Sequence[ReplayListing]:
        payload = self.fixture_payload.get(query.canonical_product_id, [])
        return [
            ReplayListing(
                item_id=str(row.get("item_id", "")).strip(),
                title=str(row.get("title", "")).strip(),
                price=float(row.get("price", 0.0)),
                currency=str(row.get("currency", "USD")).strip() or "USD",
                condition=str(row.get("condition", "")).strip(),
                source_state=str(row.get("source_state", "OK")).strip() or "OK",
            )
            for row in payload
        ]


def classify_listing(query: HistoryQuery, listing: ReplayListing) -> ClassifiedListing:
    title = listing.title.casefold()
    reasons: list[str] = []

    if listing.source_state.upper() == "SOURCE_ERROR":
        reasons.append("SOURCE_ERROR")
    if listing.price <= 0:
        reasons.append("NONPOSITIVE_PRICE")
    if listing.currency.upper() != "USD":
        reasons.append("NON_USD_CURRENCY")
    if any(token in title for token in ("opened", "empty box", "wrapper only")):
        reasons.append("OPENED_OR_EMPTY")
    if any(token in title for token in ("single pack", "1 pack", "one pack")):
        reasons.append("SINGLE_PACK")
    if any(token in title for token in ("lot of 2", "2 boxes", "case of")):
        reasons.append("MULTI_PRODUCT_LOT")
    if "proxy" in title or "reproduction" in title:
        reasons.append("PROXY_OR_REPRODUCTION")
    if "damaged" in title or "water damage" in title:
        reasons.append("DAMAGED")
    if query.product_class == "PRE_COLLECTOR_BOOSTER_BOX" and "booster box" not in title:
        reasons.append("NOT_BOOSTER_BOX")
    if "sealed" not in title:
        reasons.append("SEALED_SIGNAL_MISSING")

    accepted = not reasons
    return ClassifiedListing(
        canonical_product_id=query.canonical_product_id,
        item_id=listing.item_id,
        title=listing.title,
        price=listing.price,
        currency=listing.currency,
        accepted=accepted,
        classification="ACCEPTED_SEALED_PRODUCT" if accepted else "REJECTED",
        rejection_reason="|".join(reasons),
    )


def run_offline_replay(
    queries: Sequence[HistoryQuery],
    collector: HistoryCollector,
) -> tuple[list[ClassifiedListing], dict[str, Any]]:
    rows: list[ClassifiedListing] = []
    product_states: dict[str, str] = {}

    for query in queries:
        listings = list(collector.collect(query))
        classified = [classify_listing(query, listing) for listing in listings]
        rows.extend(classified)

        if any("SOURCE_ERROR" in row.rejection_reason for row in classified):
            state = "SOURCE_ERROR"
        elif any(row.accepted for row in classified):
            state = "MATCHED"
        elif classified:
            state = "NO_ACCEPTED_LISTINGS"
        else:
            state = "NO_RESULTS"
        product_states[query.canonical_product_id] = state

    summary = {
        "collector_mode": collector.mode,
        "products": len(queries),
        "listings": len(rows),
        "accepted_listings": sum(row.accepted for row in rows),
        "rejected_listings": sum(not row.accepted for row in rows),
        "coverage_states": {
            state: sum(value == state for value in product_states.values())
            for state in sorted(set(product_states.values()))
        },
        "product_states": product_states,
        "live_collection_enabled": False,
    }
    return rows, summary


def write_replay_artifacts(
    output_root: Path,
    rows: Sequence[ClassifiedListing],
    summary: dict[str, Any],
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)

    fields = [
        "canonical_product_id",
        "item_id",
        "title",
        "price",
        "currency",
        "accepted",
        "classification",
        "rejection_reason",
    ]
    with (output_root / "classified_listings.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "canonical_product_id": row.canonical_product_id,
                "item_id": row.item_id,
                "title": row.title,
                "price": row.price,
                "currency": row.currency,
                "accepted": str(row.accepted).lower(),
                "classification": row.classification,
                "rejection_reason": row.rejection_reason,
            })

    with (output_root / "product_coverage.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["canonical_product_id", "coverage_state"],
        )
        writer.writeheader()
        for product_id, state in summary["product_states"].items():
            writer.writerow({
                "canonical_product_id": product_id,
                "coverage_state": state,
            })

    (output_root / "replay_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )


def consolidate_observations(
    attempts: Iterable[Sequence[dict[str, str]]],
) -> list[dict[str, str]]:
    latest: dict[tuple[str, str], dict[str, str]] = {}
    for attempt in attempts:
        for row in attempt:
            key = (
                str(row.get("canonical_product_id", "")).strip(),
                str(row.get("observation_date", "")).strip(),
            )
            if not all(key):
                continue
            latest[key] = dict(row)
    return [latest[key] for key in sorted(latest)]
