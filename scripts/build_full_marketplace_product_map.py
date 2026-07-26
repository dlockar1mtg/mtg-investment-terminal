from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

BOOSTER_TYPES = {
    "Traditional Booster Display",
    "Collector Booster Display",
    "Draft Booster Display",
    "Masters Booster Display",
}

OUTPUT_FIELDS = (
    "box_name", "tcgplayer_product_id", "tcgcsv_category_id", "tcgcsv_group_id",
    "scryfall_set_code", "source_product_name", "source_url", "verified", "notes",
    "mapping_status", "collection_lane", "investment_product_id", "investment_product_type",
)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _read(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_full_product_map(
    investment_products: Path,
    secret_lair_master: Path,
    secret_lair_review: Path | None,
    output: Path,
    summary_output: Path,
) -> dict[str, Any]:
    registry = _read(investment_products)
    secret_lairs = _read(secret_lair_master)
    review_rows = _read(secret_lair_review) if secret_lair_review and secret_lair_review.is_file() else []

    registry_by_id = {
        _clean(row.get("approved_tcgplayer_product_id")): row
        for row in registry
        if _clean(row.get("approved_tcgplayer_product_id"))
    }

    mapped: list[dict[str, str]] = []
    seen: set[str] = set()
    counts: Counter[str] = Counter()

    for row in registry:
        product_type = _clean(row.get("investment_product_type"))
        if _clean(row.get("approval_status")).lower() != "approved" or product_type not in BOOSTER_TYPES:
            continue
        product_id = _clean(row.get("approved_tcgplayer_product_id"))
        if not product_id or product_id in seen:
            continue
        seen.add(product_id)
        category_id = _clean(row.get("tcgcsv_category_id"))
        group_id = _clean(row.get("tcgcsv_group_id"))
        status = "READY" if category_id and group_id else "INCOMPLETE"
        lane = "EBAY_AND_TCGCSV" if status == "READY" else "EBAY_ONLY"
        mapped.append({
            "box_name": _clean(row.get("box_name")) or _clean(row.get("approved_product_name")),
            "tcgplayer_product_id": product_id,
            "tcgcsv_category_id": category_id,
            "tcgcsv_group_id": group_id,
            "scryfall_set_code": "",
            "source_product_name": _clean(row.get("approved_product_name")),
            "source_url": investment_products.name,
            "verified": "yes",
            "notes": _clean(row.get("notes")),
            "mapping_status": status,
            "collection_lane": lane,
            "investment_product_id": _clean(row.get("investment_product_id")),
            "investment_product_type": product_type,
        })
        counts["booster_display_count"] += 1
        counts["tcgcsv_ready_count" if lane == "EBAY_AND_TCGCSV" else "ebay_only_count"] += 1

    for row in secret_lairs:
        product_id = _clean(row.get("tcgplayer_product_id"))
        if not product_id or product_id in seen:
            continue
        seen.add(product_id)
        registry_row = registry_by_id.get(product_id, {})
        category_id = _clean(registry_row.get("tcgcsv_category_id"))
        group_id = _clean(registry_row.get("tcgcsv_group_id"))
        lane = "EBAY_AND_TCGCSV" if category_id and group_id else "EBAY_ONLY"
        mapped.append({
            "box_name": _clean(row.get("product_name")),
            "tcgplayer_product_id": product_id,
            "tcgcsv_category_id": category_id,
            "tcgcsv_group_id": group_id,
            "scryfall_set_code": "",
            "source_product_name": _clean(row.get("product_name")),
            "source_url": secret_lair_master.name,
            "verified": "yes",
            "notes": _clean(row.get("notes")),
            "mapping_status": "READY",
            "collection_lane": lane,
            "investment_product_id": _clean(row.get("secret_lair_id")),
            "investment_product_type": "Secret Lair Sealed Product",
        })
        counts["secret_lair_count"] += 1
        counts["tcgcsv_ready_count" if lane == "EBAY_AND_TCGCSV" else "ebay_only_count"] += 1

    mapped.sort(key=lambda item: (item["investment_product_type"], item["box_name"].lower(), item["tcgplayer_product_id"]))
    _write(output, mapped)

    total = len(mapped)
    payload = {
        "status": "PASS" if total else "INCOMPLETE",
        "investment_products_source": str(investment_products.resolve()),
        "secret_lair_source": str(secret_lair_master.resolve()),
        "output": str(output.resolve()),
        "booster_display_count": counts["booster_display_count"],
        "secret_lair_count": counts["secret_lair_count"],
        "total_marketplace_products": total,
        "ebay_ready_count": total,
        "tcgcsv_ready_count": counts["tcgcsv_ready_count"],
        "ebay_only_count": counts["ebay_only_count"],
        "review_excluded_count": len(review_rows),
        "reason_codes": ["GOVERNED_SEALED_MARKETPLACE_UNIVERSE_BUILT"] if total else ["NO_PRODUCTS_AVAILABLE"],
    }
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the governed sealed MTG marketplace universe")
    parser.add_argument("--investment-products", type=Path, required=True)
    parser.add_argument("--secret-lair-master", type=Path, required=True)
    parser.add_argument("--secret-lair-review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_full_product_map(
        args.investment_products,
        args.secret_lair_master,
        args.secret_lair_review,
        args.output,
        args.summary_output,
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
