from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Iterable

from terminal2.market_sources.ebay_matching import (
    CanonicalProduct,
    EbayBrowseClient,
    EbayRateLimitError,
    MatchResult,
    OUTPUT_ROOT,
    _write_csv,
    build_universe,
    match_listing,
)


def _target_ids(product_map: Path) -> list[str]:
    with product_map.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        str(row.get("tcgplayer_product_id") or "").strip()
        for row in rows
        if str(row.get("tcgplayer_product_id") or "").strip()
    ]


def select_target_products(product_map: Path, universe: Iterable[CanonicalProduct] | None = None) -> tuple[list[CanonicalProduct], list[str]]:
    targets = _target_ids(product_map)
    by_tcgplayer = {
        product.tcgplayer_product_id: product
        for product in (list(universe) if universe is not None else build_universe())
        if product.tcgplayer_product_id
    }
    selected = [by_tcgplayer[target] for target in targets if target in by_tcgplayer]
    missing = [target for target in targets if target not in by_tcgplayer]
    return selected, missing


def run_targeted_coverage(product_map: Path, limit_per_product: int = 20) -> dict[str, object]:
    universe, missing_targets = select_target_products(product_map)
    client = EbayBrowseClient()
    observed = datetime.now(timezone.utc).isoformat()
    run_id = datetime.now(timezone.utc).strftime("EBAY%Y%m%dT%H%M%SZ")
    results: list[MatchResult] = []
    coverage_rows: list[dict[str, object]] = []

    for index, product in enumerate(universe, start=1):
        queries_used = 0
        try:
            items, queries_used = client.search_product(product, limit_per_product)
            matches = [match_listing(product, item, run_id, observed) for item in items]
            error = ""
        except EbayRateLimitError as exc:
            matches = []
            error = f"{type(exc).__name__}: {exc}"
            coverage_rows.append({
                **asdict(product),
                "queries_used": queries_used,
                "results_found": 0,
                "accepted_listing_count": 0,
                "review_listing_count": 0,
                "rejected_listing_count": 0,
                "median_accepted_landed_price": "",
                "lowest_accepted_landed_price": "",
                "accepted_seller_count": 0,
                "coverage_state": "SOURCE_ERROR",
                "source_error": error,
            })
            print(f"[{index}/{len(universe)}] {product.canonical_product_name}: SOURCE_ERROR")
            break
        except Exception as exc:
            matches = []
            error = f"{type(exc).__name__}: {exc}"

        results.extend(matches)
        accepted = [row for row in matches if row.match_state == "ACCEPTED"]
        review = [row for row in matches if row.match_state == "REVIEW"]
        rejected = [row for row in matches if row.match_state == "REJECTED"]
        prices = [row.landed_price for row in accepted if row.landed_price is not None]
        sellers = {row.seller_hash for row in accepted if row.seller_hash}
        if error:
            state = "SOURCE_ERROR"
        elif len(accepted) >= 5:
            state = "STRONG_MATCH_COVERAGE"
        elif accepted:
            state = "LIMITED_MATCH_COVERAGE"
        elif review:
            state = "AMBIGUOUS_RESULTS"
        else:
            state = "NO_MATCHES"
        coverage_rows.append({
            **asdict(product),
            "queries_used": queries_used,
            "results_found": len(matches),
            "accepted_listing_count": len(accepted),
            "review_listing_count": len(review),
            "rejected_listing_count": len(rejected),
            "median_accepted_landed_price": round(median(prices), 2) if prices else "",
            "lowest_accepted_landed_price": round(min(prices), 2) if prices else "",
            "accepted_seller_count": len(sellers),
            "coverage_state": state,
            "source_error": error,
        })
        print(
            f"[{index}/{len(universe)}] {product.canonical_product_name}: {state} "
            f"({len(accepted)} accepted, {len(matches)} found, {queries_used} queries)"
        )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).date().isoformat()
    universe_rows = [asdict(row) for row in universe]
    result_rows = [asdict(row) for row in results]
    _write_csv(OUTPUT_ROOT / f"ebay_canonical_match_universe_{date}.csv", universe_rows, CanonicalProduct.__dataclass_fields__.keys())
    _write_csv(OUTPUT_ROOT / f"ebay_listing_match_results_{date}.csv", result_rows, MatchResult.__dataclass_fields__.keys())
    coverage_fields = list(CanonicalProduct.__dataclass_fields__.keys()) + [
        "queries_used", "results_found", "accepted_listing_count", "review_listing_count",
        "rejected_listing_count", "median_accepted_landed_price", "lowest_accepted_landed_price",
        "accepted_seller_count", "coverage_state", "source_error",
    ]
    _write_csv(OUTPUT_ROOT / f"ebay_product_coverage_{date}.csv", coverage_rows, coverage_fields)
    _write_csv(
        OUTPUT_ROOT / f"ebay_manual_review_{date}.csv",
        [row for row in result_rows if row["match_state"] == "REVIEW"],
        MatchResult.__dataclass_fields__.keys(),
    )
    summary = {
        "run_id": run_id,
        "observed_at_utc": observed,
        "selection_mode": "PRODUCT_MAP_TARGETED",
        "requested_tcgplayer_product_ids": _target_ids(product_map),
        "missing_tcgplayer_product_ids": missing_targets,
        "products": len(coverage_rows),
        "expected_products": len(universe),
        "aborted_early": len(coverage_rows) < len(universe),
        "listing_rows": len(results),
        "queries_used": sum(int(row["queries_used"]) for row in coverage_rows),
        "accepted_rows": sum(row.match_state == "ACCEPTED" for row in results),
        "review_rows": sum(row.match_state == "REVIEW" for row in results),
        "rejected_rows": sum(row.match_state == "REJECTED" for row in results),
        "coverage_states": {
            state: sum(row["coverage_state"] == state for row in coverage_rows)
            for state in sorted({str(row["coverage_state"]) for row in coverage_rows})
        },
        "credentials_printed": False,
    }
    (OUTPUT_ROOT / f"ebay_matching_summary_{date}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
