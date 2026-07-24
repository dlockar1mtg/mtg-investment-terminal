from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/reclassify_ebay_matching_batch.py"
TEST = ROOT / "tests/test_ebay_local_reclassification.py"

SCRIPT_CONTENT = r'''from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_precision import strict_match_listing


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest(batch_root: Path, pattern: str) -> Path:
    paths = sorted(batch_root.glob(pattern), key=lambda value: value.stat().st_mtime, reverse=True)
    if not paths:
        raise FileNotFoundError(f"No file matching {pattern} under {batch_root}")
    return paths[0]


def as_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def product_from_row(row: dict[str, str]) -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id=row["canonical_product_id"],
        canonical_product_name=row["canonical_product_name"],
        canonical_set_name=row.get("canonical_set_name", ""),
        product_class=row.get("product_class", "SEALED_SECRET_LAIR"),
        tcgplayer_product_id=row.get("tcgplayer_product_id", ""),
        release_date=row.get("release_date", ""),
        ebay_query=row.get("ebay_query", ""),
    )


def reclassify_row(row: dict[str, str]) -> dict[str, object]:
    product = product_from_row(row)
    item = {
        "itemId": row.get("ebay_item_id", ""),
        "title": row.get("title", ""),
        "itemWebUrl": row.get("item_url", ""),
        "price": {
            "value": row.get("price", "0") or "0",
            "currency": row.get("currency", "USD") or "USD",
        },
        "condition": row.get("condition", ""),
    }
    replay = strict_match_listing(
        product,
        item,
        row.get("source_run_id", "LOCAL-RECLASSIFICATION"),
        row.get("observed_at_utc", ""),
    )
    updated: dict[str, object] = dict(row)
    updated["match_score"] = replay.match_score
    updated["match_state"] = replay.match_state
    updated["exclusion_reasons"] = replay.exclusion_reasons
    return updated


def coverage_state(accepted: int, review: int) -> str:
    if accepted >= 5:
        return "STRONG_MATCH_COVERAGE"
    if accepted:
        return "LIMITED_MATCH_COVERAGE"
    if review:
        return "AMBIGUOUS_RESULTS"
    return "NO_MATCHES"


def rebuild_coverage(
    original_rows: list[dict[str, str]],
    listing_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in listing_rows:
        grouped.setdefault(str(row["canonical_product_id"]), []).append(row)

    rebuilt: list[dict[str, object]] = []
    for original in original_rows:
        product_rows = grouped.get(original["canonical_product_id"], [])
        accepted = [row for row in product_rows if row["match_state"] == "ACCEPTED"]
        review = [row for row in product_rows if row["match_state"] == "REVIEW"]
        rejected = [row for row in product_rows if row["match_state"] == "REJECTED"]
        prices = [
            value
            for value in (as_float(str(row.get("landed_price", ""))) for row in accepted)
            if value is not None
        ]
        sellers = {str(row.get("seller_hash", "")) for row in accepted if row.get("seller_hash")}
        row: dict[str, object] = dict(original)
        row.update({
            "results_found": len(product_rows),
            "accepted_listing_count": len(accepted),
            "review_listing_count": len(review),
            "rejected_listing_count": len(rejected),
            "median_accepted_landed_price": round(median(prices), 2) if prices else "",
            "lowest_accepted_landed_price": round(min(prices), 2) if prices else "",
            "accepted_seller_count": len(sellers),
            "coverage_state": coverage_state(len(accepted), len(review)),
            "source_error": "",
        })
        rebuilt.append(row)
    return rebuilt


def run(batch_root: Path, expected_products: int) -> Path:
    universe_path = latest(batch_root, "ebay_canonical_match_universe_*.csv")
    listings_path = latest(batch_root, "ebay_listing_match_results_*.csv")
    coverage_path = latest(batch_root, "ebay_product_coverage_*.csv")

    universe_rows = read_csv(universe_path)
    original_listings = read_csv(listings_path)
    original_coverage = read_csv(coverage_path)
    if len(universe_rows) != expected_products or len(original_coverage) != expected_products:
        raise RuntimeError(
            f"Expected {expected_products} products; universe={len(universe_rows)}, coverage={len(original_coverage)}"
        )

    reclassified = [reclassify_row(row) for row in original_listings]
    rebuilt_coverage = rebuild_coverage(original_coverage, reclassified)
    manual = [row for row in reclassified if row["match_state"] == "REVIEW"]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    observed = datetime.now(timezone.utc).isoformat()
    output = batch_root / "reclassified" / f"reclassification_{stamp}"
    output.mkdir(parents=True, exist_ok=False)

    date = datetime.now(timezone.utc).date().isoformat()
    universe_out = output / f"ebay_canonical_match_universe_{date}.csv"
    listings_out = output / f"ebay_listing_match_results_{date}.csv"
    manual_out = output / f"ebay_manual_review_{date}.csv"
    coverage_out = output / f"ebay_product_coverage_{date}.csv"
    summary_out = output / f"ebay_matching_summary_{date}.json"

    shutil.copy2(universe_path, universe_out)
    listing_fields = list(original_listings[0].keys())
    coverage_fields = list(original_coverage[0].keys())
    write_csv(listings_out, reclassified, listing_fields)
    write_csv(manual_out, manual, listing_fields)
    write_csv(coverage_out, rebuilt_coverage, coverage_fields)

    counts = {
        state: sum(row["match_state"] == state for row in reclassified)
        for state in ("ACCEPTED", "REVIEW", "REJECTED")
    }
    coverage_counts = {
        state: sum(row["coverage_state"] == state for row in rebuilt_coverage)
        for state in sorted({str(row["coverage_state"]) for row in rebuilt_coverage})
    }
    changed = sum(
        old.get("match_state") != new.get("match_state")
        or old.get("exclusion_reasons") != new.get("exclusion_reasons")
        or str(old.get("match_score")) != str(new.get("match_score"))
        for old, new in zip(original_listings, reclassified)
    )
    summary = {
        "run_id": f"LOCAL-RECLASSIFICATION-{stamp}",
        "observed_at_utc": observed,
        "products": len(rebuilt_coverage),
        "expected_products": expected_products,
        "aborted_early": False,
        "listing_rows": len(reclassified),
        "queries_used": 0,
        "accepted_rows": counts["ACCEPTED"],
        "review_rows": counts["REVIEW"],
        "rejected_rows": counts["REJECTED"],
        "coverage_states": coverage_counts,
        "credentials_printed": False,
        "reclassification_changed_rows": changed,
    }
    summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    manifest = {
        "status": "PENDING_AUDIT",
        "created_at_utc": observed,
        "batch_root": str(batch_root.resolve()),
        "output_root": str(output.resolve()),
        "expected_products": expected_products,
        "products": len(rebuilt_coverage),
        "unique_product_ids": len({row["canonical_product_id"] for row in rebuilt_coverage}),
        "source_errors": sum(row["coverage_state"] == "SOURCE_ERROR" for row in rebuilt_coverage),
        "listing_rows": len(reclassified),
        "accepted_rows": counts["ACCEPTED"],
        "review_rows": counts["REVIEW"],
        "rejected_rows": counts["REJECTED"],
        "changed_rows": changed,
        "quota_calls": 0,
        "source_files": {
            path.name: {"sha256": sha256(path), "bytes": path.stat().st_size}
            for path in (universe_path, listings_path, coverage_path)
        },
        "output_files": {
            path.name: {"sha256": sha256(path), "bytes": path.stat().st_size}
            for path in (universe_out, listings_out, manual_out, coverage_out, summary_out)
        },
    }
    (output / "reclassification_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print("EBAY LOCAL BATCH RECLASSIFICATION: COMPLETE")
    print(json.dumps(manifest, indent=2))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--expected-products", type=int, required=True)
    args = parser.parse_args()
    run(args.batch_root, args.expected_products)


if __name__ == "__main__":
    main()
'''

TEST_CONTENT = r'''from __future__ import annotations

from scripts.reclassify_ebay_matching_batch import coverage_state


def test_coverage_state_strong():
    assert coverage_state(5, 0) == "STRONG_MATCH_COVERAGE"


def test_coverage_state_limited():
    assert coverage_state(1, 4) == "LIMITED_MATCH_COVERAGE"


def test_coverage_state_ambiguous():
    assert coverage_state(0, 2) == "AMBIGUOUS_RESULTS"


def test_coverage_state_no_matches():
    assert coverage_state(0, 0) == "NO_MATCHES"
'''


def apply() -> None:
    if SCRIPT.exists() or TEST.exists():
        raise RuntimeError("Local reclassification files already exist; refusing to overwrite")
    SCRIPT.write_text(SCRIPT_CONTENT, encoding="utf-8")
    TEST.write_text(TEST_CONTENT, encoding="utf-8")
    print("PHASE 10.6A3.3 LOCAL EBAY RECLASSIFICATION: APPLIED")
    print(f"Created: {SCRIPT.relative_to(ROOT)}")
    print(f"Created: {TEST.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
