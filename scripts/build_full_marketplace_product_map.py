from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

OUTPUT_FIELDS = (
    "box_name",
    "tcgplayer_product_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "scryfall_set_code",
    "source_product_name",
    "source_url",
    "verified",
    "notes",
    "mapping_status",
    "investment_product_id",
    "investment_product_type",
)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _first(row: dict[str, str], *fields: str) -> str:
    for field in fields:
        value = _clean(row.get(field))
        if value:
            return value
    return ""


def _read(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_full_product_map(source_input: Path, output: Path, summary_output: Path) -> dict[str, Any]:
    rows = _read(source_input)
    mapped: list[dict[str, str]] = []
    seen: set[str] = set()
    statuses: Counter[str] = Counter()

    for row in rows:
        product_id = _first(row, "approved_tcgplayer_product_id", "tcgplayer_product_id")
        category_id = _first(row, "tcgcsv_category_id_master", "tcgcsv_category_id")
        group_id = _first(row, "tcgcsv_group_id_master", "tcgcsv_group_id")
        name = _first(row, "box_name_master", "box_name", "canonical_product_name", "official_product_name", "approved_product_name")
        source_name = _first(row, "approved_product_name", "canonical_product_name", "official_product_name", "source_product_name", "box_name")
        approval = _first(row, "approval_status", "investment_approval_status").lower()
        product_type = _first(row, "investment_product_type", "canonical_product_type", "candidate_product_type")
        investment_id = _first(row, "investment_product_id", "existing_investment_product_id", "canonical_product_id")

        if not name:
            status = "MISSING_PRODUCT_NAME"
        elif not product_id:
            status = "MISSING_TCGPLAYER_ID"
        elif not category_id:
            status = "MISSING_TCGCSV_CATEGORY"
        elif not group_id:
            status = "MISSING_TCGCSV_GROUP"
        elif approval and approval not in {"approved", "verified", "pass"}:
            status = "NOT_APPROVED"
        else:
            status = "READY"

        identity = product_id or investment_id or name.lower()
        if identity in seen:
            statuses["DUPLICATE_IDENTITY"] += 1
            continue
        seen.add(identity)
        statuses[status] += 1

        mapped.append({
            "box_name": name,
            "tcgplayer_product_id": product_id,
            "tcgcsv_category_id": category_id,
            "tcgcsv_group_id": group_id,
            "scryfall_set_code": "",
            "source_product_name": source_name,
            "source_url": source_input.name,
            "verified": "yes" if status == "READY" else "no",
            "notes": _first(row, "notes", "existing_registry_notes", "identity_review_reason"),
            "mapping_status": status,
            "investment_product_id": investment_id,
            "investment_product_type": product_type,
        })

    mapped.sort(key=lambda item: (item["mapping_status"] != "READY", item["box_name"].lower(), item["tcgplayer_product_id"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(mapped)

    ready_count = sum(1 for row in mapped if row["mapping_status"] == "READY")
    payload = {
        "status": "PASS" if mapped else "INCOMPLETE",
        "source_input": str(source_input.resolve()),
        "output": str(output.resolve()),
        "source_row_count": len(rows),
        "unique_product_count": len(mapped),
        "ready_product_count": ready_count,
        "not_ready_product_count": len(mapped) - ready_count,
        "status_counts": dict(sorted(statuses.items())),
        "reason_codes": ["FULL_MARKETPLACE_PRODUCT_MAP_BUILT"] if mapped else ["NO_PRODUCTS_AVAILABLE"],
    }
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a governed full-universe marketplace product map")
    parser.add_argument("--source-input", "--model-input", dest="source_input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_full_product_map(args.source_input, args.output, args.summary_output)
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
