from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

REGISTRY = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "unified_mtg_registry"
    / "unified_mtg_product_registry.csv"
)

LEDGER = (
    ROOT
    / "data"
    / "operations"
    / "mtg_universal_history_ledger"
    / "universal_mtg_historical_observation_ledger.csv"
)

OUTPUT = (
    ROOT
    / "artifacts"
    / "weekend_readiness"
    / "20260730-163101"
    / "historical_purchase_screen"
)

CANONICAL_DAILY = (
    OUTPUT
    / "16_canonical_governed_daily_history.csv"
)


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")

    if not text:
        return None

    try:
        parsed = float(text)
    except ValueError:
        return None

    if not math.isfinite(parsed) or parsed <= 0:
        return None

    return parsed


def normalize_date(value: Any) -> str:
    text = clean(value)

    if len(text) < 10:
        return ""

    candidate = text[:10]

    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return ""

    return candidate


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if fields is None:
        fields = list(rows[0].keys()) if rows else []

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def is_excluded_listing_row(row: dict[str, str]) -> bool:
    combined = "|".join(
        [
            clean(row.get("source_name")),
            clean(row.get("source_file")),
            clean(row.get("price_field")),
        ]
    ).upper()

    return (
        "CURRENT_ASKING" in combined
        or "CURRENT_LISTING" in combined
        or "ASKING_HISTORY" in combined
    )


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    registry_rows = read_csv(REGISTRY)
    ledger_rows = read_csv(LEDGER)

    alias_to_universal: dict[str, str] = {}
    universal_metadata: dict[str, dict[str, str]] = {}
    alias_conflicts: list[dict[str, str]] = []

    for row in registry_rows:
        universal_id = clean(
            row.get("universal_mtg_product_id")
        )

        if not universal_id:
            continue

        universal_metadata[universal_id] = {
            "canonical_product_name": clean(
                row.get("canonical_product_name")
            ),
            "product_class": clean(
                row.get("product_class")
            ),
            "source_product_id": clean(
                row.get("source_product_id")
            ),
            "tcgplayer_product_id": clean(
                row.get("tcgplayer_product_id")
            ),
            "admission_tier": clean(
                row.get("admission_tier")
            ),
            "quality_disposition": clean(
                row.get("quality_disposition")
            ),
        }

        aliases = {
            universal_id,
            clean(row.get("source_product_id")),
        }

        tcgplayer_id = clean(
            row.get("tcgplayer_product_id")
        )

        if tcgplayer_id:
            aliases.add(tcgplayer_id)
            aliases.add(
                f"MTG-CANON-TCGPLAYER-{tcgplayer_id}"
            )

        for alias in aliases:
            if not alias:
                continue

            existing = alias_to_universal.get(alias)

            if existing and existing != universal_id:
                alias_conflicts.append(
                    {
                        "alias": alias,
                        "first_universal_id": existing,
                        "second_universal_id": universal_id,
                    }
                )
                continue

            alias_to_universal[alias] = universal_id

    unmatched_rows: list[dict[str, str]] = []
    excluded_listing_rows: list[dict[str, str]] = []
    invalid_rows: list[dict[str, str]] = []

    grouped: dict[
        tuple[str, str],
        list[dict[str, Any]],
    ] = defaultdict(list)

    alias_usage: Counter[str] = Counter()
    source_usage: Counter[str] = Counter()

    for row in ledger_rows:
        ledger_id = clean(
            row.get("canonical_product_id")
        )

        universal_id = alias_to_universal.get(ledger_id)

        if not universal_id:
            unmatched_rows.append(row)
            continue

        if is_excluded_listing_row(row):
            excluded_listing_rows.append(row)
            continue

        observation_date = normalize_date(
            row.get("observation_date")
        )

        price = (
            number(row.get("market_price"))
            or number(row.get("low_price"))
        )

        if not observation_date or price is None:
            invalid_rows.append(row)
            continue

        grouped[
            (universal_id, observation_date)
        ].append(
            {
                "price": price,
                "source_name": clean(
                    row.get("source_name")
                ),
                "source_file": clean(
                    row.get("source_file")
                ),
                "original_ledger_id": ledger_id,
                "mapping_method": clean(
                    row.get("mapping_method")
                ),
                "listing_count": clean(
                    row.get("listing_count")
                ),
                "seller_count": clean(
                    row.get("seller_count")
                ),
            }
        )

        alias_usage[ledger_id] += 1
        source_usage[
            clean(row.get("source_name"))
        ] += 1

    canonical_rows: list[dict[str, Any]] = []

    for (
        universal_id,
        observation_date,
    ), observations in grouped.items():
        metadata = universal_metadata[universal_id]

        prices = [
            float(item["price"])
            for item in observations
        ]

        sources = sorted(
            {
                clean(item["source_name"])
                for item in observations
                if clean(item["source_name"])
            }
        )

        source_files = sorted(
            {
                clean(item["source_file"])
                for item in observations
                if clean(item["source_file"])
            }
        )

        original_ids = sorted(
            {
                clean(item["original_ledger_id"])
                for item in observations
                if clean(item["original_ledger_id"])
            }
        )

        mapping_methods = sorted(
            {
                clean(item["mapping_method"])
                for item in observations
                if clean(item["mapping_method"])
            }
        )

        canonical_rows.append(
            {
                "canonical_product_id": universal_id,
                "canonical_product_name": metadata[
                    "canonical_product_name"
                ],
                "product_class": metadata[
                    "product_class"
                ],
                "source_product_id": metadata[
                    "source_product_id"
                ],
                "tcgplayer_product_id": metadata[
                    "tcgplayer_product_id"
                ],
                "observation_date": observation_date,
                "consolidated_market_price": round(
                    median(prices),
                    4,
                ),
                "minimum_observed_price": round(
                    min(prices),
                    4,
                ),
                "maximum_observed_price": round(
                    max(prices),
                    4,
                ),
                "raw_observation_count": len(
                    observations
                ),
                "source_count": len(sources),
                "source_names": "|".join(sources),
                "source_file_count": len(
                    source_files
                ),
                "original_identity_count": len(
                    original_ids
                ),
                "original_ledger_ids": "|".join(
                    original_ids
                ),
                "mapping_methods": "|".join(
                    mapping_methods
                ),
                "admission_tier": metadata[
                    "admission_tier"
                ],
                "quality_disposition": metadata[
                    "quality_disposition"
                ],
            }
        )

    canonical_rows.sort(
        key=lambda row: (
            row["canonical_product_id"],
            row["observation_date"],
        )
    )

    write_csv(
        CANONICAL_DAILY,
        canonical_rows,
    )

    product_series: dict[
        str,
        list[tuple[str, float]],
    ] = defaultdict(list)

    product_names: dict[str, str] = {}
    product_classes: dict[str, str] = {}

    for row in canonical_rows:
        product_id = clean(
            row["canonical_product_id"]
        )

        product_series[product_id].append(
            (
                clean(row["observation_date"]),
                float(
                    row["consolidated_market_price"]
                ),
            )
        )

        product_names[product_id] = clean(
            row["canonical_product_name"]
        )
        product_classes[product_id] = clean(
            row["product_class"]
        )

    path_profiles: list[dict[str, Any]] = []

    for product_id, series in product_series.items():
        series.sort(key=lambda item: item[0])

        path_text = ";".join(
            f"{date_value}={price:.4f}"
            for date_value, price in series
        )

        path_hash = hashlib.sha256(
            path_text.encode("utf-8")
        ).hexdigest()

        path_profiles.append(
            {
                "canonical_product_id": product_id,
                "canonical_product_name": product_names[
                    product_id
                ],
                "product_class": product_classes[
                    product_id
                ],
                "distinct_dates": len(series),
                "first_date": (
                    series[0][0]
                    if series
                    else ""
                ),
                "latest_date": (
                    series[-1][0]
                    if series
                    else ""
                ),
                "price_path_hash": path_hash,
            }
        )

    write_csv(
        OUTPUT / "17_canonical_price_path_profiles.csv",
        path_profiles,
    )

    profiles_by_hash: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for profile in path_profiles:
        profiles_by_hash[
            clean(profile["price_path_hash"])
        ].append(profile)

    repeated_paths: list[dict[str, Any]] = []

    for path_hash, profiles in profiles_by_hash.items():
        if len(profiles) <= 1:
            continue

        if int(profiles[0]["distinct_dates"]) < 8:
            continue

        repeated_paths.append(
            {
                "product_count": len(profiles),
                "distinct_dates": profiles[0][
                    "distinct_dates"
                ],
                "first_date": profiles[0][
                    "first_date"
                ],
                "latest_date": profiles[0][
                    "latest_date"
                ],
                "product_classes": "|".join(
                    sorted(
                        {
                            clean(
                                item["product_class"]
                            )
                            for item in profiles
                        }
                    )
                ),
                "product_names": " || ".join(
                    sorted(
                        clean(
                            item[
                                "canonical_product_name"
                            ]
                        )
                        for item in profiles
                    )
                ),
                "canonical_product_ids": "|".join(
                    sorted(
                        clean(
                            item[
                                "canonical_product_id"
                            ]
                        )
                        for item in profiles
                    )
                ),
                "price_path_hash": path_hash,
            }
        )

    repeated_paths.sort(
        key=lambda row: (
            -int(row["product_count"]),
            -int(row["distinct_dates"]),
        )
    )

    write_csv(
        OUTPUT / "18_repeated_canonical_price_paths.csv",
        repeated_paths,
        [
            "product_count",
            "distinct_dates",
            "first_date",
            "latest_date",
            "product_classes",
            "product_names",
            "canonical_product_ids",
            "price_path_hash",
        ],
    )

    product_date_counts = Counter(
        row["canonical_product_id"]
        for row in canonical_rows
    )

    history_distribution = Counter()

    for count in product_date_counts.values():
        if count >= 30:
            history_distribution["30_PLUS"] += 1
        elif count >= 2:
            history_distribution["2_TO_29"] += 1
        else:
            history_distribution["ONE_DATE"] += 1

    source_profile = [
        {
            "source_name": source,
            "ledger_rows": count,
        }
        for source, count in source_usage.most_common()
    ]

    write_csv(
        OUTPUT / "19_canonical_source_profile.csv",
        source_profile,
        ["source_name", "ledger_rows"],
    )

    summary = {
        "generated_at": datetime.now().isoformat(),
        "registry_products": len(
            universal_metadata
        ),
        "registry_aliases": len(
            alias_to_universal
        ),
        "alias_conflicts": len(
            alias_conflicts
        ),
        "ledger_input_rows": len(
            ledger_rows
        ),
        "unmatched_ledger_rows": len(
            unmatched_rows
        ),
        "excluded_current_listing_rows": len(
            excluded_listing_rows
        ),
        "invalid_ledger_rows": len(
            invalid_rows
        ),
        "canonical_daily_rows": len(
            canonical_rows
        ),
        "canonical_products_with_history": len(
            product_series
        ),
        "registry_products_without_history": (
            len(universal_metadata)
            - len(product_series)
        ),
        "repeated_multi_date_price_paths": len(
            repeated_paths
        ),
        "history_date_distribution": dict(
            sorted(history_distribution.items())
        ),
        "canonical_history_file": str(
            CANONICAL_DAILY.relative_to(ROOT)
        ),
    }

    write_csv(
        OUTPUT / "20_alias_conflicts.csv",
        alias_conflicts,
        [
            "alias",
            "first_universal_id",
            "second_universal_id",
        ],
    )

    write_csv(
        OUTPUT / "21_unmatched_ledger_rows.csv",
        unmatched_rows,
    )

    (
        OUTPUT
        / "22_canonical_history_summary.json"
    ).write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
