from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_UNIVERSE = (
    ROOT
    / "data/validation/phase_10/unified_mtg_registry/"
      "unified_mtg_product_registry.csv"
)
DEFAULT_SECRET_LAIR_ROUTES = (
    ROOT
    / "data/operations/mtg_tcgcsv_price_backfill/"
      "universal_tcgcsv_price_route_status.csv"
)
DEFAULT_CANONICAL_REGISTRY = (
    ROOT
    / "data/staging/phase_10/canonical_registry/"
      "canonical_mtg_product_registry_2026-07-22.csv"
)
DEFAULT_HISTORY_VERIFICATION = (
    ROOT
    / "data/operations/mtg_history_backfill/"
      "universal_mtg_history_source_verification.csv"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data/operations/mtg_universal_history_completion"
)

ROUTE_FIELDS = [
    "universal_mtg_product_id",
    "canonical_product_name",
    "product_class",
    "product_group",
    "finish_group",
    "tcgplayer_product_id",
    "release_date",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "tcgcsv_identity_status",
    "tcgcsv_archive_eligible",
    "ebay_history_eligible",
    "existing_distinct_history_dates",
    "existing_history_status",
    "primary_history_route",
    "secondary_history_route",
    "history_completion_status",
    "history_reason_code",
]

GROUP_FIELDS = [
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "product_count",
    "product_classes",
    "earliest_release_date",
    "latest_release_date",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def clean(value: object) -> str:
    return str(value or "").strip()


def truthy(value: object) -> bool:
    return clean(value).casefold() in {"1", "true", "yes", "y"}


def build_pair_evidence(
    canonical_rows: list[dict[str, str]],
) -> dict[str, set[tuple[str, str]]]:
    evidence: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in canonical_rows:
        product_id = clean(row.get("tcgplayer_product_id"))
        category_id = clean(row.get("tcgcsv_category_id"))
        group_id = clean(row.get("tcgcsv_group_id"))
        if product_id and category_id and group_id:
            evidence[product_id].add((category_id, group_id))
    return evidence


def build_routes(
    universe_rows: list[dict[str, str]],
    secret_lair_rows: list[dict[str, str]],
    canonical_rows: list[dict[str, str]],
    verification_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    sl_by_id = {
        clean(row.get("investment_product_id")): row
        for row in secret_lair_rows
        if clean(row.get("investment_product_id"))
    }
    verification_by_id = {
        clean(row.get("canonical_product_id")): row
        for row in verification_rows
        if clean(row.get("canonical_product_id"))
    }
    pair_evidence = build_pair_evidence(canonical_rows)

    routes: list[dict[str, Any]] = []
    duplicate_ids: list[str] = []
    seen_ids: set[str] = set()

    for row in universe_rows:
        universal_id = clean(row.get("universal_mtg_product_id"))
        source_product_id = clean(row.get("source_product_id"))
        if universal_id in seen_ids:
            duplicate_ids.append(universal_id)
        seen_ids.add(universal_id)

        product_class = clean(row.get("product_class"))
        tcgplayer_id = clean(row.get("tcgplayer_product_id"))
        category_id = ""
        group_id = ""
        identity_status = ""
        reason = ""

        # Phase 11E.7 is governed by investment_product_id. In the
        # universal registry that governed ID is stored in source_product_id.
        sl = sl_by_id.get(source_product_id) or sl_by_id.get(universal_id)
        if sl:
            identity_status = clean(sl.get("discovery_status"))
            category_id = clean(sl.get("tcgcsv_category_id"))
            group_id = clean(sl.get("tcgcsv_group_id"))
            tcgplayer_id = (
                clean(sl.get("tcgplayer_product_id"))
                or tcgplayer_id
            )
            automatic = truthy(sl.get("automatic_collection_allowed"))
            if (
                identity_status == "TCGCSV_ID_CONFIRMED"
                and automatic
                and category_id
                and group_id
            ):
                archive_eligible = True
                reason = "SECRET_LAIR_CONFIRMED_TCGCSV_IDENTITY"
            elif identity_status == "TCGCSV_ID_AMBIGUOUS":
                archive_eligible = False
                reason = "SECRET_LAIR_TCGCSV_IDENTITY_AMBIGUOUS"
            else:
                archive_eligible = False
                reason = "SECRET_LAIR_TCGCSV_IDENTITY_NOT_FOUND"
        else:
            pairs = sorted(pair_evidence.get(tcgplayer_id, set()))
            if len(pairs) == 1:
                category_id, group_id = pairs[0]
                identity_status = "TCGCSV_ID_CONFIRMED_FROM_CANONICAL_EVIDENCE"
                archive_eligible = True
                reason = "NON_SECRET_LAIR_UNIQUE_CATEGORY_GROUP_EVIDENCE"
            elif len(pairs) > 1:
                identity_status = "TCGCSV_ID_AMBIGUOUS_CATEGORY_GROUP"
                archive_eligible = False
                reason = "NON_SECRET_LAIR_MULTIPLE_CATEGORY_GROUP_EVIDENCE"
            elif tcgplayer_id:
                identity_status = "TCGCSV_ID_GROUP_NOT_RESOLVED"
                archive_eligible = False
                reason = "NON_SECRET_LAIR_GROUP_EVIDENCE_NOT_FOUND"
            else:
                identity_status = "TCGCSV_ID_NOT_FOUND"
                archive_eligible = False
                reason = "TCGPLAYER_ID_NOT_AVAILABLE"

        verification = verification_by_id.get(universal_id, {})
        distinct_dates = clean(verification.get("distinct_history_dates")) or "0"
        existing_status = (
            clean(verification.get("history_verification_status"))
            or "HISTORY_NOT_VERIFIED"
        )
        ebay_eligible = (
            clean(verification.get("ebay_identity_status")).upper()
            not in {"", "NOT_AVAILABLE", "MISSING"}
        )
        if not verification:
            ebay_eligible = True

        if archive_eligible:
            primary = "TCGCSV_MONTHLY_ARCHIVE"
            secondary = "EBAY_DAILY_ACCUMULATION"
            completion = "ARCHIVE_BACKFILL_READY"
        elif ebay_eligible:
            primary = "EBAY_DAILY_ACCUMULATION"
            secondary = "IDENTITY_REVIEW"
            completion = "LIVE_ACCUMULATION_REQUIRED"
        else:
            primary = "IDENTITY_REVIEW"
            secondary = "SOURCE_RESEARCH"
            completion = "IDENTITY_UNRESOLVED"

        routes.append({
            "universal_mtg_product_id": universal_id,
            "canonical_product_name": clean(row.get("canonical_product_name")),
            "product_class": product_class,
            "product_group": clean(row.get("product_group")),
            "finish_group": clean(row.get("finish_group")),
            "tcgplayer_product_id": tcgplayer_id,
            "release_date": clean(row.get("release_date")),
            "tcgcsv_category_id": category_id,
            "tcgcsv_group_id": group_id,
            "tcgcsv_identity_status": identity_status,
            "tcgcsv_archive_eligible": str(archive_eligible).lower(),
            "ebay_history_eligible": str(ebay_eligible).lower(),
            "existing_distinct_history_dates": distinct_dates,
            "existing_history_status": existing_status,
            "primary_history_route": primary,
            "secondary_history_route": secondary,
            "history_completion_status": completion,
            "history_reason_code": reason,
        })

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in routes:
        if row["tcgcsv_archive_eligible"] == "true":
            grouped[
                (row["tcgcsv_category_id"], row["tcgcsv_group_id"])
            ].append(row)

    groups: list[dict[str, Any]] = []
    for (category_id, group_id), members in sorted(grouped.items()):
        release_dates = sorted(
            date for date in (clean(row["release_date"]) for row in members) if date
        )
        groups.append({
            "tcgcsv_category_id": category_id,
            "tcgcsv_group_id": group_id,
            "product_count": len(members),
            "product_classes": "|".join(sorted({
                clean(row["product_class"]) for row in members
            })),
            "earliest_release_date": release_dates[0] if release_dates else "",
            "latest_release_date": release_dates[-1] if release_dates else "",
        })

    route_counts = Counter(row["primary_history_route"] for row in routes)
    identity_counts = Counter(row["tcgcsv_identity_status"] for row in routes)
    class_counts = Counter(row["product_class"] for row in routes)

    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "universe_rows": len(universe_rows),
        "routing_rows": len(routes),
        "unique_universal_product_ids": len(seen_ids),
        "duplicate_universal_product_ids": sorted(set(duplicate_ids)),
        "secret_lair_route_rows": len(secret_lair_rows),
        "matched_secret_lair_route_rows": sum(
            row["product_class"] == "SECRET_LAIR"
            and row["history_reason_code"].startswith("SECRET_LAIR_")
            for row in routes
        ),
        "archive_eligible_products": sum(
            row["tcgcsv_archive_eligible"] == "true" for row in routes
        ),
        "archive_group_pairs": len(groups),
        "primary_route_counts": dict(sorted(route_counts.items())),
        "tcgcsv_identity_status_counts": dict(sorted(identity_counts.items())),
        "product_class_counts": dict(sorted(class_counts.items())),
        "certification_checks": {
            "universe_rows_equal_1141": len(universe_rows) == 1141,
            "routing_rows_equal_1141": len(routes) == 1141,
            "universal_ids_unique": len(seen_ids) == 1141 and not duplicate_ids,
            "all_rows_have_primary_route": all(
                clean(row["primary_history_route"]) for row in routes
            ),
            "all_archive_rows_have_category_group": all(
                (
                    row["tcgcsv_category_id"]
                    and row["tcgcsv_group_id"]
                )
                for row in routes
                if row["tcgcsv_archive_eligible"] == "true"
            ),
            "secret_lair_routes_accounted_for": (
                len(secret_lair_rows) == 973
                and sum(
                    row["product_class"] == "SECRET_LAIR"
                    and row["history_reason_code"].startswith("SECRET_LAIR_")
                    for row in routes
                ) == 973
            ),
            "confirmed_secret_lair_routes_preserved": sum(
                row["product_class"] == "SECRET_LAIR"
                and row["tcgcsv_identity_status"] == "TCGCSV_ID_CONFIRMED"
                and row["tcgcsv_archive_eligible"] == "true"
                for row in routes
            ) == 871,
        },
    }
    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"

    return routes, groups, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the governed 1,141-product universal history routing matrix."
    )
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument(
        "--secret-lair-routes",
        type=Path,
        default=DEFAULT_SECRET_LAIR_ROUTES,
    )
    parser.add_argument(
        "--canonical-registry",
        type=Path,
        default=DEFAULT_CANONICAL_REGISTRY,
    )
    parser.add_argument(
        "--history-verification",
        type=Path,
        default=DEFAULT_HISTORY_VERIFICATION,
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    routes, groups, summary = build_routes(
        read_csv(args.universe.resolve()),
        read_csv(args.secret_lair_routes.resolve()),
        read_csv(args.canonical_registry.resolve()),
        read_csv(args.history_verification.resolve()),
    )

    output_root = args.output_root.resolve()
    write_csv(
        output_root / "universal_history_routing_matrix.csv",
        routes,
        ROUTE_FIELDS,
    )
    write_csv(
        output_root / "tcgcsv_archive_group_manifest.csv",
        groups,
        GROUP_FIELDS,
    )
    (output_root / "universal_history_routing_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
