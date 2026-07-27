from __future__ import annotations

from pathlib import Path
from typing import Any

from terminal2.market_sources import ebay_matching
from terminal2.market_sources import ebay_targeted_collection
from terminal2.market_sources.ebay_precision_v2 import identity_match_listing

MATCHER_VERSION = "precision-v2"


def _with_classifier_metadata(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        **summary,
        "matcher_version": MATCHER_VERSION,
        "matcher_entrypoint": "terminal2.market_sources.ebay_precision_v2.identity_match_listing",
        "matcher_fail_closed": True,
    }


def run_precision_coverage(
    limit_per_product: int = 20,
    max_products: int | None = None,
) -> dict[str, Any]:
    """Run the normal universe collector with the certified precision-v2 matcher.

    The legacy collection module resolves ``match_listing`` from its own module
    namespace. Patch that binding only for the duration of this single-process
    CLI run and restore it in ``finally`` so tests and callers cannot inherit
    accidental global state.
    """

    original = ebay_matching.match_listing
    ebay_matching.match_listing = identity_match_listing
    try:
        summary = ebay_matching.run_coverage(
            limit_per_product=limit_per_product,
            max_products=max_products,
        )
    finally:
        ebay_matching.match_listing = original
    return _with_classifier_metadata(summary)


def run_precision_targeted_coverage(
    product_map: Path,
    limit_per_product: int = 20,
) -> dict[str, Any]:
    """Run targeted collection with the certified precision-v2 matcher."""

    original = ebay_targeted_collection.match_listing
    ebay_targeted_collection.match_listing = identity_match_listing
    try:
        summary = ebay_targeted_collection.run_targeted_coverage(
            product_map=product_map,
            limit_per_product=limit_per_product,
        )
    finally:
        ebay_targeted_collection.match_listing = original
    return _with_classifier_metadata(summary)
