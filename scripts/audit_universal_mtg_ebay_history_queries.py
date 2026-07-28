from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

BATCH_PLAN = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "universal_mtg_ebay_accumulation_batch_plan.csv"
)
OUTPUT = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/query_review"
)

AUDIT_FIELDS = [
    "canonical_product_id",
    "canonical_product_name",
    "batch_id",
    "priority_tier",
    "ebay_query",
    "query_length",
    "normalized_query_key",
    "query_review_status",
    "review_reasons",
    "live_collection_allowed",
]

LONG_QUERY_THRESHOLD = 100
RISK_PATTERNS = {
    "VERSION_FILENAME_LANGUAGE": re.compile(
        r"\b(final|use\s*this\s*one|v\d+)\b",
        re.IGNORECASE,
    ),
    "DUPLICATE_EDITION_LANGUAGE": re.compile(
        r"\b(foil|non-?foil|standard)\s+edition\b.*\b"
        r"(foil|non-?foil|standard)\s+edition\b",
        re.IGNORECASE,
    ),
    "EVERYTHING_BUNDLE": re.compile(
        r"\beverything\s+bundle\b",
        re.IGNORECASE,
    ),
    "PARENTHETICAL_VERSION": re.compile(r"\(\d+\)"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def clean(value: object) -> str:
    return str(value or "").strip()


def normalize_query_key(value: object) -> str:
    text = clean(value).casefold()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def audit_query(row: dict[str, str]) -> dict[str, Any]:
    query = clean(row.get("ebay_query"))
    reasons: list[str] = []

    if len(query) > LONG_QUERY_THRESHOLD:
        reasons.append("QUERY_OVER_100_CHARACTERS")

    for reason, pattern in RISK_PATTERNS.items():
        if pattern.search(query):
            reasons.append(reason)

    if query.count('"') != 2:
        reasons.append("QUOTE_STRUCTURE_REVIEW")

    if "\n" in query or "\r" in query:
        reasons.append("LINE_BREAK_PRESENT")

    status = "APPROVED_FOR_DRY_RUN" if not reasons else "REVIEW_REQUIRED"
    return {
        "canonical_product_id": clean(row.get("canonical_product_id")),
        "canonical_product_name": clean(
            row.get("canonical_product_name")
        ),
        "batch_id": clean(row.get("batch_id")),
        "priority_tier": clean(row.get("priority_tier")),
        "ebay_query": query,
        "query_length": len(query),
        "normalized_query_key": normalize_query_key(query),
        "query_review_status": status,
        "review_reasons": "|".join(reasons),
        "live_collection_allowed": "false",
    }


def build_audit(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    audited = [audit_query(row) for row in rows]

    key_counts = Counter(
        row["normalized_query_key"] for row in audited
    )
    for row in audited:
        if key_counts[row["normalized_query_key"]] > 1:
            reasons = [
                reason for reason in row["review_reasons"].split("|")
                if reason
            ]
            if "NORMALIZED_QUERY_COLLISION" not in reasons:
                reasons.append("NORMALIZED_QUERY_COLLISION")
            row["review_reasons"] = "|".join(reasons)
            row["query_review_status"] = "REVIEW_REQUIRED"

    reason_counts: Counter[str] = Counter()
    for row in audited:
        for reason in row["review_reasons"].split("|"):
            if reason:
                reason_counts[reason] += 1

    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "audited_queries": len(audited),
        "approved_for_dry_run": sum(
            row["query_review_status"] == "APPROVED_FOR_DRY_RUN"
            for row in audited
        ),
        "review_required": sum(
            row["query_review_status"] == "REVIEW_REQUIRED"
            for row in audited
        ),
        "maximum_query_length": max(
            (int(row["query_length"]) for row in audited),
            default=0,
        ),
        "normalized_query_collisions": sum(
            count > 1 for count in key_counts.values()
        ),
        "review_reason_counts": dict(sorted(reason_counts.items())),
        "live_collection_enabled": False,
        "certification_checks": {
            "audited_queries_equal_152": len(audited) == 152,
            "product_ids_unique": len({
                row["canonical_product_id"] for row in audited
            }) == len(audited),
            "all_queries_classified": all(
                row["query_review_status"] in {
                    "APPROVED_FOR_DRY_RUN",
                    "REVIEW_REQUIRED",
                }
                for row in audited
            ),
            "live_collection_disabled_for_all": all(
                row["live_collection_allowed"] == "false"
                for row in audited
            ),
        },
    }

    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"

    audited.sort(
        key=lambda row: (
            row["query_review_status"] != "REVIEW_REQUIRED",
            -int(row["query_length"]),
            row["canonical_product_name"].casefold(),
        )
    )
    return audited, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit governed eBay history queries before any live "
            "collection is enabled."
        )
    )
    parser.add_argument("--batch-plan", type=Path, default=BATCH_PLAN)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    args = parser.parse_args()

    rows = read_csv(args.batch_plan.resolve())
    if len(rows) != 152:
        raise SystemExit(
            f"Expected 152 batch-plan rows; found {len(rows)}."
        )

    audited, summary = build_audit(rows)
    output_root = args.output_root.resolve()
    write_csv(
        output_root / "universal_mtg_ebay_query_review.csv",
        audited,
        AUDIT_FIELDS,
    )
    (
        output_root / "universal_mtg_ebay_query_review_summary.json"
    ).write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
