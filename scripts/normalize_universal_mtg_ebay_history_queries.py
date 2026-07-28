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
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "normalized_queries"
)

OUTPUT_FIELDS = [
    "batch_id",
    "batch_sequence",
    "batch_label",
    "queue_rank",
    "canonical_product_id",
    "canonical_product_name",
    "product_class",
    "priority_tier",
    "gap_category",
    "original_ebay_query",
    "normalized_search_name",
    "normalized_ebay_query",
    "normalization_actions",
    "normalized_query_length",
    "normalized_query_key",
    "query_review_status",
    "review_reasons",
    "live_collection_allowed",
]

MAX_QUERY_LENGTH = 100


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


def normalize_key(value: object) -> str:
    text = clean(value).casefold()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def normalize_name(name: str) -> tuple[str, list[str]]:
    text = clean(name)
    actions: list[str] = []

    updated = re.sub(r"^Drop:\s*", "", text, flags=re.IGNORECASE)
    if updated != text:
        text = updated
        actions.append("REMOVE_DROP_PREFIX")

    artifact_pattern = re.compile(
        r"FINAL_final_REALLYfinal_v\d+_USETHISONE\(\d+\)_",
        re.IGNORECASE,
    )
    updated = artifact_pattern.sub("", text)
    if updated != text:
        text = updated
        actions.append("REMOVE_FILENAME_VERSION_ARTIFACT")

    suffix_rules = [
        (
            re.compile(r"\s+—\s+Standard Edition$", re.IGNORECASE),
            "",
            "REMOVE_REDUNDANT_STANDARD_SUFFIX",
        ),
        (
            re.compile(
                r"(?i)(Foil Edition)\s+—\s+Foil Edition$"
            ),
            r"\1",
            "COLLAPSE_DUPLICATE_FOIL_SUFFIX",
        ),
        (
            re.compile(
                r"(?i)(Non-?Foil Edition)\s+—\s+Nonfoil Edition$"
            ),
            r"\1",
            "COLLAPSE_DUPLICATE_NONFOIL_SUFFIX",
        ),
    ]
    for pattern, replacement, action in suffix_rules:
        updated = pattern.sub(replacement, text)
        if updated != text:
            text = updated
            actions.append(action)

    updated = re.sub(r"\s+", " ", text).strip(" -—")
    if updated != text:
        text = updated
        actions.append("NORMALIZE_WHITESPACE")

    return text, actions


def build_query(
    name: str,
    product_class: str,
) -> tuple[str, str]:
    if product_class == "PRE_COLLECTOR_BOOSTER_BOX":
        return f'"{name}" sealed booster box', "EXACT_NORMALIZED_SEALED_BOX"
    return f'"{name}" sealed', "EXACT_NORMALIZED_SEALED_SECRET_LAIR"


def normalize_row(row: dict[str, str]) -> dict[str, Any]:
    normalized_name, actions = normalize_name(
        clean(row.get("canonical_product_name"))
    )
    query, _ = build_query(
        normalized_name,
        clean(row.get("product_class")),
    )

    review_reasons: list[str] = []
    if len(query) > MAX_QUERY_LENGTH:
        review_reasons.append("NORMALIZED_QUERY_OVER_100_CHARACTERS")
    if re.search(
        r"\b(final_really|use\s*this\s*one|v\d+)\b",
        query,
        flags=re.IGNORECASE,
    ):
        review_reasons.append("VERSION_ARTIFACT_REMAINS")
    if query.count('"') != 2:
        review_reasons.append("QUOTE_STRUCTURE_REVIEW")
    if "\n" in query or "\r" in query:
        review_reasons.append("LINE_BREAK_PRESENT")

    return {
        "batch_id": clean(row.get("batch_id")),
        "batch_sequence": clean(row.get("batch_sequence")),
        "batch_label": clean(row.get("batch_label")),
        "queue_rank": clean(row.get("queue_rank")),
        "canonical_product_id": clean(row.get("canonical_product_id")),
        "canonical_product_name": clean(
            row.get("canonical_product_name")
        ),
        "product_class": clean(row.get("product_class")),
        "priority_tier": clean(row.get("priority_tier")),
        "gap_category": clean(row.get("gap_category")),
        "original_ebay_query": clean(row.get("ebay_query")),
        "normalized_search_name": normalized_name,
        "normalized_ebay_query": query,
        "normalization_actions": "|".join(actions),
        "normalized_query_length": len(query),
        "normalized_query_key": normalize_key(query),
        "query_review_status": (
            "REVIEW_REQUIRED"
            if review_reasons
            else "APPROVED_FOR_DRY_RUN"
        ),
        "review_reasons": "|".join(review_reasons),
        "live_collection_allowed": "false",
    }


def build_normalized_plan(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalized = [normalize_row(row) for row in rows]

    key_counts = Counter(
        row["normalized_query_key"] for row in normalized
    )
    for row in normalized:
        if key_counts[row["normalized_query_key"]] > 1:
            reasons = [
                reason for reason in row["review_reasons"].split("|")
                if reason
            ]
            if "NORMALIZED_QUERY_COLLISION" not in reasons:
                reasons.append("NORMALIZED_QUERY_COLLISION")
            row["review_reasons"] = "|".join(reasons)
            row["query_review_status"] = "REVIEW_REQUIRED"

    action_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for row in normalized:
        for action in row["normalization_actions"].split("|"):
            if action:
                action_counts[action] += 1
        for reason in row["review_reasons"].split("|"):
            if reason:
                reason_counts[reason] += 1

    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "normalized_queries": len(normalized),
        "approved_for_dry_run": sum(
            row["query_review_status"] == "APPROVED_FOR_DRY_RUN"
            for row in normalized
        ),
        "review_required": sum(
            row["query_review_status"] == "REVIEW_REQUIRED"
            for row in normalized
        ),
        "maximum_normalized_query_length": max(
            (
                int(row["normalized_query_length"])
                for row in normalized
            ),
            default=0,
        ),
        "normalized_query_collisions": sum(
            count > 1 for count in key_counts.values()
        ),
        "normalization_action_counts": dict(sorted(action_counts.items())),
        "review_reason_counts": dict(sorted(reason_counts.items())),
        "live_collection_enabled": False,
        "certification_checks": {
            "normalized_queries_equal_152": len(normalized) == 152,
            "product_ids_unique": len({
                row["canonical_product_id"] for row in normalized
            }) == len(normalized),
            "normalized_queries_present": all(
                clean(row["normalized_ebay_query"])
                for row in normalized
            ),
            "all_queries_classified": all(
                row["query_review_status"] in {
                    "APPROVED_FOR_DRY_RUN",
                    "REVIEW_REQUIRED",
                }
                for row in normalized
            ),
            "live_collection_disabled_for_all": all(
                row["live_collection_allowed"] == "false"
                for row in normalized
            ),
            "normalized_query_collisions_zero": all(
                count == 1 for count in key_counts.values()
            ),
        },
    }
    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"

    normalized.sort(
        key=lambda row: (
            row["query_review_status"] != "REVIEW_REQUIRED",
            -int(row["normalized_query_length"]),
            row["canonical_product_name"].casefold(),
        )
    )
    return normalized, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize governed eBay historical-accumulation queries "
            "without enabling live collection."
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

    normalized, summary = build_normalized_plan(rows)
    output_root = args.output_root.resolve()
    write_csv(
        output_root / "universal_mtg_ebay_normalized_query_plan.csv",
        normalized,
        OUTPUT_FIELDS,
    )
    (
        output_root / "universal_mtg_ebay_normalized_query_summary.json"
    ).write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
